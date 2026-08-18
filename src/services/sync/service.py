import asyncio
import aiohttp
import contextlib
import json
import logging
import re

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_CEILING
from html import escape
from typing import Any, Callable
from zoneinfo import ZoneInfo

from aiogram import Bot

from src.config import settings
from src.config.financial import CARD_WITHDRAWAL_NET_RATIO
from src.db import async_session_factory
from src.db.models.catalog_account import CatalogAccount, CatalogAccountStatus, GameAccountType
from src.db.repositories import BotSettingsRepository, CatalogAccountRepository
from src.i18n import Language, translate

logger = logging.getLogger(__name__)

LZT_API_BASE_URL = "https://prod-api.lzt.market"
LZT_CATEGORY_PAGE_DELAY_SECONDS = 0.5
LZT_CATEGORY_LIMIT_PER_GAME = 5000
LZT_REQUEST_TIMEOUT_SECONDS = 30
LZT_CHECK_TIMEOUT_SECONDS = 310
LZT_MAX_RETRIES = 3
LZT_FAST_BUY_MAX_RETRIES = 100
LZT_RETRY_DELAY_SECONDS = 2
LZT_PAYOUT_RATIO = CARD_WITHDRAWAL_NET_RATIO
LZT_MIN_NET_MARGIN_RUB = Decimal("10")
LZT_MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")
LZT_WORLD_OF_TANKS_ENDPOINT = "world-of-tanks"
LZT_WOT_BLITZ_ENDPOINT = "wot-blitz"
UNIQUE_TOP_BONUSES: dict[str, int] = json.loads(settings.unique_tops_path.read_text(encoding="utf-8")).get(
    "unique_tops_tanks_wot",
    {},
)


class LztConfigurationError(Exception):
    pass


class LztSyncError(Exception):
    pass


class LztApiResponseError(LztSyncError):
    def __init__(self, *, method: str, url: str, status: int, payload: dict[str, Any]) -> None:
        self.method = method
        self.url = url
        self.status = status
        self.payload = payload
        super().__init__(f"LZT API responded with status {status} for {url}: {payload}")


@dataclass(frozen=True)
class CatalogSyncReport:
    trigger: str
    started_at: datetime
    finished_at: datetime
    total_loaded: int
    skipped_count: int
    mir_tankov_count: int
    tanks_blitz_count: int
    world_of_tanks_count: int
    wot_blitz_count: int


@dataclass(frozen=True)
class CatalogRefreshResult:
    exists: bool
    changed: bool
    deleted: bool
    account_id: int
    local_account_id: int
    change_lines: tuple[str, ...]


@dataclass(frozen=True)
class LztCatalogSource:
    endpoint_slug: str
    country: str
    game_type: GameAccountType
    daybreak_days: int
    top_min: int


LZT_CATALOG_SOURCES: tuple[LztCatalogSource, ...] = (
    LztCatalogSource(
        endpoint_slug=LZT_WORLD_OF_TANKS_ENDPOINT,
        country="ru",
        game_type=GameAccountType.MIR_TANKOV,
        daybreak_days=7,
        top_min=1,
    ),
    LztCatalogSource(
        endpoint_slug=LZT_WOT_BLITZ_ENDPOINT,
        country="ru",
        game_type=GameAccountType.TANKS_BLITZ,
        daybreak_days=7,
        top_min=1,
    ),
    LztCatalogSource(
        endpoint_slug=LZT_WORLD_OF_TANKS_ENDPOINT,
        country="eu",
        game_type=GameAccountType.WORLD_OF_TANKS,
        daybreak_days=7,
        top_min=1,
    ),
    LztCatalogSource(
        endpoint_slug=LZT_WORLD_OF_TANKS_ENDPOINT,
        country="na",
        game_type=GameAccountType.WORLD_OF_TANKS,
        daybreak_days=7,
        top_min=1,
    ),
    LztCatalogSource(
        endpoint_slug=LZT_WORLD_OF_TANKS_ENDPOINT,
        country="asia",
        game_type=GameAccountType.WORLD_OF_TANKS,
        daybreak_days=7,
        top_min=1,
    ),
    LztCatalogSource(
        endpoint_slug=LZT_WOT_BLITZ_ENDPOINT,
        country="eu",
        game_type=GameAccountType.WOT_BLITZ,
        daybreak_days=7,
        top_min=1,
    ),
    LztCatalogSource(
        endpoint_slug=LZT_WOT_BLITZ_ENDPOINT,
        country="na",
        game_type=GameAccountType.WOT_BLITZ,
        daybreak_days=7,
        top_min=1,
    ),
    LztCatalogSource(
        endpoint_slug=LZT_WOT_BLITZ_ENDPOINT,
        country="asia",
        game_type=GameAccountType.WOT_BLITZ,
        daybreak_days=7,
        top_min=1,
    ),
)


class AccountRefreshTaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[None]] = {}

    def register(self, user_id: int, task: asyncio.Task[None]) -> None:
        current_task = self._tasks.get(user_id)
        if current_task is not None and current_task is not task and not current_task.done():
            current_task.cancel()
        self._tasks[user_id] = task

        def _cleanup(completed_task: asyncio.Task[None]) -> None:
            active_task = self._tasks.get(user_id)
            if active_task is completed_task:
                self._tasks.pop(user_id, None)

        task.add_done_callback(_cleanup)

    async def cancel(self, user_id: int) -> bool:
        task = self._tasks.pop(user_id, None)
        if task is None:
            return False
        if task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    def get(self, user_id: int) -> asyncio.Task[None] | None:
        task = self._tasks.get(user_id)
        if task is None or task.done():
            return None
        return task


class LztMarketClient:
    def __init__(self) -> None:
        if not settings.lzt_market_token:
            raise LztConfigurationError("LZT_MARKET_TOKEN is not configured.")

        self._headers = {
            "accept": "application/json",
            "authorization": f"Bearer {settings.lzt_market_token}",
        }
        self._request_timeout = aiohttp.ClientTimeout(total=LZT_REQUEST_TIMEOUT_SECONDS)
        self._check_timeout = aiohttp.ClientTimeout(total=LZT_CHECK_TIMEOUT_SECONDS)

    async def fetch_category_page(self, source: LztCatalogSource, *, page: int) -> dict[str, Any]:
        return await self._request_json(
            "GET",
            f"{LZT_API_BASE_URL}/{source.endpoint_slug}",
            params=_build_catalog_page_params(source=source, page=page),
        )

    async def check_account(self, supplier_item_id: int) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            f"{LZT_API_BASE_URL}/{supplier_item_id}/check-account",
            timeout=self._check_timeout,
            retry_retry_request=True,
        )

    async def confirm_buy(self, supplier_item_id: int, *, price: Decimal) -> dict[str, Any]:
        payload: dict[str, int] = {
            "price": int(price),
            "balance_id": settings.lzt_balance_id,
        }
        return await self._request_json(
            "POST",
            f"{LZT_API_BASE_URL}/{supplier_item_id}/confirm-buy",
            json=payload,
            timeout=self._check_timeout,
        )

    async def get_item(self, supplier_item_id: int) -> dict[str, Any]:
        return await self._request_json(
            "GET",
            f"{LZT_API_BASE_URL}/{supplier_item_id}",
        )

    async def get_managed_item(self, supplier_item_id: int) -> dict[str, Any]:
        return await self.get_item(supplier_item_id)

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: list[tuple[str, str]] | dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        retry_retry_request: bool = False,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        request_timeout = timeout or self._request_timeout

        attempts_limit = max_retries or LZT_MAX_RETRIES
        for attempt in range(1, attempts_limit + 1):
            try:
                logger.info(
                    "LZT request started method=%s url=%s params=%s body=%s attempt=%s/%s",
                    method,
                    url,
                    params,
                    json,
                    attempt,
                    attempts_limit,
                )
                async with aiohttp.ClientSession(headers=self._headers, timeout=request_timeout) as session:
                    async with session.request(method, url, params=params, json=json) as response:
                        payload = await response.json(content_type=None)
                        if 200 <= response.status < 300:
                            logger.info(
                                "LZT request succeeded method=%s url=%s status=%s",
                                method,
                                url,
                                response.status,
                            )
                            return payload
                        raise LztApiResponseError(
                            method=method,
                            url=url,
                            status=response.status,
                            payload=payload if isinstance(payload, dict) else {"payload": payload},
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, LztSyncError) as error:
                last_error = error
                logger.warning(
                    "LZT request failed method=%s url=%s attempt=%s/%s error=%s",
                    method,
                    url,
                    attempt,
                    attempts_limit,
                    error,
                )
                if retry_retry_request:
                    # Fast Buy is repeated only when LZT explicitly requests it.
                    # Retrying a timeout or any other error could duplicate a purchase.
                    if not isinstance(error, LztApiResponseError) or not _is_retry_request_error(error):
                        raise
                elif isinstance(error, LztApiResponseError):
                    raise
                if attempt < attempts_limit:
                    await asyncio.sleep(LZT_RETRY_DELAY_SECONDS)

        raise LztSyncError(f"LZT request failed: {method} {url}") from last_error


class CatalogSyncService:
    def __init__(self) -> None:
        self._sync_lock = asyncio.Lock()
        self._active_sync_task: asyncio.Task[None] | None = None
        self._client_factory: Callable[[], LztMarketClient] = LztMarketClient
        self._sales_temporarily_blocked = False

    def is_configured(self) -> bool:
        return bool(settings.lzt_market_token)

    def create_client(self) -> LztMarketClient:
        return self._client_factory()

    def is_running(self) -> bool:
        return self._active_sync_task is not None and not self._active_sync_task.done()

    def are_sales_temporarily_blocked(self) -> bool:
        return self._sales_temporarily_blocked or self.is_running()

    async def shutdown(self) -> None:
        if self._active_sync_task is None or self._active_sync_task.done():
            return
        self._active_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._active_sync_task
        self._active_sync_task = None

    async def start_background_sync(
        self,
        *,
        bot: Bot,
        chat_id: int,
        language: Language,
        trigger: str,
    ) -> bool:
        if self.is_running():
            return False

        self._active_sync_task = asyncio.create_task(
            self._run_background_sync(bot=bot, chat_id=chat_id, language=language, trigger=trigger)
        )
        return True

    async def run_scheduled_sync(self) -> CatalogSyncReport | None:
        if self.is_running():
            logger.info("Skipping scheduled catalog sync because another sync is already running.")
            return None
        return await self.run_full_sync(trigger="scheduled")

    async def run_full_sync(self, *, trigger: str) -> CatalogSyncReport:
        if not self.is_configured():
            raise LztConfigurationError("LZT token is not configured.")

        async with self._sync_lock:
            previous_sales_enabled = await self._set_sales_blocked_for_sync(True)
            try:
                logger.info("Catalog sync started trigger=%s", trigger)
                started_at = datetime.now(UTC)
                client = self._client_factory()
                parsed_rows: list[dict[str, object]] = []
                loaded_by_game_type = {
                    GameAccountType.MIR_TANKOV: 0,
                    GameAccountType.TANKS_BLITZ: 0,
                    GameAccountType.WORLD_OF_TANKS: 0,
                    GameAccountType.WOT_BLITZ: 0,
                }
                skipped_count = 0

                for source in LZT_CATALOG_SOURCES:
                    logger.info(
                        "Loading LZT source endpoint=%s region=%s game_type=%s",
                        source.endpoint_slug,
                        source.country,
                        source.game_type.value,
                    )
                    page = 1
                    while loaded_by_game_type[source.game_type] < LZT_CATEGORY_LIMIT_PER_GAME:
                        payload = await client.fetch_category_page(source, page=page)
                        items = payload.get("items") or []
                        if not isinstance(items, list):
                            break

                        accepted_on_page = 0
                        for raw_item in items:
                            if not isinstance(raw_item, dict):
                                continue
                            normalized = _normalize_supplier_item(raw_item, category_slug=source.endpoint_slug)
                            if normalized is None:
                                skipped_count += 1
                                continue

                            game_type = GameAccountType(str(normalized["game_type"]))
                            if game_type != source.game_type:
                                skipped_count += 1
                                continue
                            if loaded_by_game_type[game_type] >= LZT_CATEGORY_LIMIT_PER_GAME:
                                continue

                            parsed_rows.append(normalized)
                            loaded_by_game_type[game_type] += 1
                            accepted_on_page += 1

                        logger.info(
                            "LZT page processed endpoint=%s region=%s game_type=%s page=%s items=%s accepted=%s loaded=%s/%s",
                            source.endpoint_slug,
                            source.country,
                            source.game_type.value,
                            page,
                            len(items),
                            accepted_on_page,
                            loaded_by_game_type[source.game_type],
                            LZT_CATEGORY_LIMIT_PER_GAME,
                        )

                        has_next_page = bool(payload.get("hasNextPage"))
                        if not items or not has_next_page:
                            break

                        page += 1
                        await asyncio.sleep(LZT_CATEGORY_PAGE_DELAY_SECONDS)

                finished_at = datetime.now(UTC)
                async with async_session_factory() as session:
                    repository = CatalogAccountRepository(session)
                    await repository.replace_all(parsed_rows)
                    await session.commit()

                report = CatalogSyncReport(
                    trigger=trigger,
                    started_at=started_at,
                    finished_at=finished_at,
                    total_loaded=len(parsed_rows),
                    skipped_count=skipped_count,
                    mir_tankov_count=loaded_by_game_type[GameAccountType.MIR_TANKOV],
                    tanks_blitz_count=loaded_by_game_type[GameAccountType.TANKS_BLITZ],
                    world_of_tanks_count=loaded_by_game_type[GameAccountType.WORLD_OF_TANKS],
                    wot_blitz_count=loaded_by_game_type[GameAccountType.WOT_BLITZ],
                )
                logger.info(
                    "Catalog sync completed trigger=%s total=%s skipped=%s",
                    report.trigger,
                    report.total_loaded,
                    report.skipped_count,
                )
                return report
            finally:
                await self._restore_sales_after_sync(previous_sales_enabled)

    async def refresh_account(self, *, local_account_id: int) -> CatalogRefreshResult:
        if not self.is_configured():
            raise LztConfigurationError("LZT token is not configured.")

        async with async_session_factory() as session:
            repository = CatalogAccountRepository(session)
            account = await repository.get_by_id(local_account_id)
            if account is None:
                await session.rollback()
                raise LztSyncError(f"Local account {local_account_id} not found.")
            supplier_item_id = account.supplier_item_id
            supplier_category_slug = account.supplier_category_slug
            await session.commit()

        logger.info(
            "Refreshing catalog account local_account_id=%s supplier_item_id=%s",
            local_account_id,
            supplier_item_id,
        )
        client = self._client_factory()
        try:
            check_payload = await client.check_account(supplier_item_id)
        except LztApiResponseError as error:
            if _has_supplier_change_notice(error.payload):
                logger.info(
                    "LZT check-account reported changes, refreshing item directly local_account_id=%s supplier_item_id=%s",
                    local_account_id,
                    supplier_item_id,
                )
                check_payload = error.payload
            else:
                raise
        managed_payload = await client.get_item(supplier_item_id)
        raw_item = managed_payload.get("item")
        if not isinstance(raw_item, dict):
            await self._delete_local_account(local_account_id)
            return CatalogRefreshResult(
                exists=False,
                changed=False,
                deleted=True,
                account_id=supplier_item_id,
                local_account_id=local_account_id,
                change_lines=(),
            )

        normalized = _normalize_supplier_item(raw_item, category_slug=supplier_category_slug, preserve_local_id=local_account_id)
        if normalized is None or str(normalized["supplier_item_state"]) != "active":
            await self._delete_local_account(local_account_id)
            return CatalogRefreshResult(
                exists=False,
                changed=False,
                deleted=True,
                account_id=supplier_item_id,
                local_account_id=local_account_id,
                change_lines=(),
            )

        async with async_session_factory() as session:
            repository = CatalogAccountRepository(session)
            current_account = await repository.get_by_id(local_account_id)
            if current_account is None:
                await session.rollback()
                raise LztSyncError(f"Local account {local_account_id} not found during refresh.")

            local_change_lines = _build_local_change_lines(current_account, normalized)
            change_lines = local_change_lines

            _apply_account_mapping(current_account, normalized)
            await session.commit()

        result = CatalogRefreshResult(
            exists=True,
            changed=bool(change_lines),
            deleted=False,
            account_id=supplier_item_id,
            local_account_id=local_account_id,
            change_lines=change_lines,
        )
        logger.info(
            "Catalog account refreshed local_account_id=%s supplier_item_id=%s changed=%s changes=%s",
            local_account_id,
            supplier_item_id,
            result.changed,
            len(result.change_lines),
        )
        return result

    async def _run_background_sync(
        self,
        *,
        bot: Bot,
        chat_id: int,
        language: Language,
        trigger: str,
    ) -> None:
        try:
            report = await self.run_full_sync(trigger=trigger)
        except Exception as error:
            logger.exception("Catalog sync failed trigger=%s", trigger)
            await bot.send_message(
                chat_id=chat_id,
                text=render_catalog_sync_failed_text(language, error),
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=render_catalog_sync_report_text(language, report),
            )
        finally:
            self._active_sync_task = None

    async def _delete_local_account(self, local_account_id: int) -> None:
        async with async_session_factory() as session:
            repository = CatalogAccountRepository(session)
            account = await repository.get_by_id(local_account_id)
            if account is None:
                await session.commit()
                return
            await repository.delete(account)
            await session.commit()

    async def _set_sales_blocked_for_sync(self, blocked: bool) -> bool:
        async with async_session_factory() as session:
            repository = BotSettingsRepository(session)
            bot_settings = await repository.get_or_create()
            previous_sales_enabled = bool(bot_settings.sales_enabled)
            self._sales_temporarily_blocked = blocked
            await session.commit()
        logger.info("Temporary sales block changed blocked=%s previous_sales_enabled=%s", blocked, previous_sales_enabled)
        return previous_sales_enabled

    async def _restore_sales_after_sync(self, previous_sales_enabled: bool) -> None:
        self._sales_temporarily_blocked = False
        logger.info("Temporary sales block cleared previous_sales_enabled=%s", previous_sales_enabled)


class CatalogSyncScheduler:
    def __init__(self, sync_service: CatalogSyncService) -> None:
        self._sync_service = sync_service
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            delay = _seconds_until_next_moscow_midnight()
            logger.info("Next catalog sync is scheduled in %.2f seconds.", delay)
            await asyncio.sleep(delay)
            try:
                await self._sync_service.run_scheduled_sync()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled catalog sync failed.")


def render_catalog_sync_started_text(language: Language) -> str:
    return translate(language, "admin_force_refresh_started")


def render_catalog_sync_running_alert(language: Language) -> str:
    return translate(language, "admin_force_refresh_running")


def render_catalog_sync_report_text(language: Language, report: CatalogSyncReport) -> str:
    duration_seconds = int((report.finished_at - report.started_at).total_seconds())
    return "\n".join(
        (
            translate(language, "admin_force_refresh_finished_title"),
            "",
            translate(language, "admin_force_refresh_total", count=report.total_loaded),
            translate(language, "admin_force_refresh_mir_tankov", count=report.mir_tankov_count),
            translate(language, "admin_force_refresh_tanks_blitz", count=report.tanks_blitz_count),
            translate(language, "admin_force_refresh_world_of_tanks", count=report.world_of_tanks_count),
            translate(language, "admin_force_refresh_wot_blitz", count=report.wot_blitz_count),
            translate(language, "admin_force_refresh_skipped", count=report.skipped_count),
            translate(language, "admin_force_refresh_duration", seconds=duration_seconds),
        )
    )


def render_catalog_sync_failed_text(language: Language, error: Exception) -> str:
    return translate(language, "admin_force_refresh_failed", reason=escape(str(error)))


def render_pricing_formula_text(language: Language) -> str:
    return "\n".join(
        (
            translate(language, "admin_products_markup_title"),
            "",
            translate(
                language,
                "admin_products_markup_formula_1",
                payout=f"{_format_decimal(LZT_PAYOUT_RATIO)}",
            ),
            translate(
                language,
                "admin_products_markup_formula_2",
            ),
            translate(
                language,
                "admin_products_markup_formula_3",
            ),
            translate(
                language,
                "admin_products_markup_formula_4",
            ),
            translate(
                language,
                "admin_products_markup_formula_5",
                payout=f"{_format_decimal(LZT_PAYOUT_RATIO)}",
            ),
            translate(
                language,
                "admin_products_markup_formula_6",
                payout=f"{_format_decimal(LZT_PAYOUT_RATIO)}",
                min_margin=f"{_format_decimal(LZT_MIN_NET_MARGIN_RUB)}",
            ),
        )
    )


def render_catalog_refresh_progress_text(language: Language, account_id: int) -> str:
    return translate(language, "catalog_refresh_in_progress", value=account_id)


def render_catalog_refresh_stopped_text(language: Language, account_id: int) -> str:
    return translate(language, "catalog_refresh_stopped", account_id=account_id)


def render_catalog_refresh_result_text(language: Language, result: CatalogRefreshResult) -> str:
    if result.deleted:
        return translate(language, "catalog_refresh_deleted")
    if not result.changed:
        return translate(language, "catalog_refresh_not_changed", account_id=result.local_account_id)

    return "\n\n".join(
        (
            translate(language, "catalog_refresh_changed", account_id=result.local_account_id),
            "<blockquote>"
            + "\n\n".join(escape(line) for line in result.change_lines)
            + "</blockquote>",
        )
    )


def render_catalog_refresh_failed_text(language: Language, account_id: int) -> str:
    return translate(language, "catalog_refresh_failed", account_id=account_id)


def render_catalog_refresh_not_configured_text(language: Language) -> str:
    return translate(language, "catalog_refresh_not_configured")


def calculate_feature_based_sale_price(raw_item: dict[str, Any], *, game_type: GameAccountType) -> Decimal:
    top_cnt = int(_item_value(raw_item, "wot_top_tanks") or 0)
    prem_cnt = int(_item_value(raw_item, "wot_premium_tanks") or 0)
    top_prem_cnt = _resolve_top_premium_count(raw_item)

    is_blitz = game_type in {GameAccountType.TANKS_BLITZ, GameAccountType.WOT_BLITZ}
    top_price = Decimal("14") if is_blitz else Decimal("15")
    premium_bucket_price = Decimal("14") if is_blitz else Decimal("15")
    top_premium_price = Decimal("4") if is_blitz else Decimal("5")

    score = Decimal(top_cnt) * top_price
    score += Decimal(_ceil_div(prem_cnt, 10)) * premium_bucket_price
    score += Decimal(top_prem_cnt) * top_premium_price

    top_names = _collect_unique_top_names(raw_item)
    for unique_name, bonus in UNIQUE_TOP_BONUSES.items():
        if unique_name in top_names:
            score += Decimal(bonus) - top_premium_price

    idle_days = _days_since_timestamp(_item_value(raw_item, "wot_last_activity", "account_last_activity"))
    if idle_days >= 530:
        score *= Decimal("3")
    elif idle_days >= 330:
        score *= Decimal("2.5")
    elif idle_days >= 230:
        score *= Decimal("2")
    elif idle_days >= 130:
        score *= Decimal("1.5")

    base_sale_price = score.quantize(Decimal("1"), rounding=ROUND_CEILING)
    if base_sale_price <= 0:
        return Decimal("0.00")
    return (base_sale_price / LZT_PAYOUT_RATIO).quantize(Decimal("1"), rounding=ROUND_CEILING).quantize(Decimal("0.01"))


def _build_catalog_page_params(source: LztCatalogSource, *, page: int) -> list[tuple[str, str]]:
    return [
        ("page", str(page)),
        ("pmin", "5"),
        ("pmax", "2000"),
        ("show", "active"),
        ("daybreak", str(source.daybreak_days)),
        ("top_min", str(source.top_min)),
        ("region[]", source.country),
        ("order_by", "pdate_to_down_upload"),
        ("email_type[]", "no"),
    ]


def _normalize_supplier_item(
    raw_item: dict[str, Any],
    *,
    category_slug: str,
    preserve_local_id: int | None = None,
) -> dict[str, object] | None:
    region = str(_item_value(raw_item, "wot_region") or "").strip().lower()
    if not region:
        return None

    game_type = _resolve_game_type(category_slug=category_slug, region=region)
    if game_type is None:
        return None

    supplier_item_id = _item_value(raw_item, "item_id", "wot_item_id")
    if supplier_item_id is None:
        return None

    supplier_price = _to_decimal(_item_value(raw_item, "rub_price", "price") or 0)
    if supplier_price <= 0:
        return None

    tanks_payload = _normalize_tanks_payload(raw_item)
    total_tanks = int(_item_value(raw_item, "wot_tanks_count") or len(tanks_payload))
    has_tier_11 = any(int(tank.get("tier") or 0) == 11 for tank in tanks_payload)
    supplier_item_state = str(_item_value(raw_item, "item_state") or "active")

    sale_price = calculate_feature_based_sale_price(raw_item, game_type=game_type)
    if sale_price * LZT_PAYOUT_RATIO - supplier_price < LZT_MIN_NET_MARGIN_RUB:
        return None

    row: dict[str, object] = {
        "supplier_item_id": int(supplier_item_id),
        "supplier_category_slug": category_slug,
        "supplier_item_state": supplier_item_state,
        "game_type": game_type.value,
        "status": _map_catalog_status(supplier_item_state).value,
        "top_tank_count": int(_item_value(raw_item, "wot_top_tanks") or 0),
        "premium_tank_count": int(_item_value(raw_item, "wot_premium_tanks") or 0),
        "total_tank_count": total_tanks,
        "silver_amount": int(_item_value(raw_item, "wot_credits") or 0),
        "gold_amount": int(_item_value(raw_item, "wot_gold") or 0),
        "battles_count": int(_item_value(raw_item, "wot_battle_count") or 0),
        "wins_count": int(_item_value(raw_item, "wot_win_count") or 0),
        "win_rate_percent": _to_decimal(_item_value(raw_item, "wot_win_count_percents") or 0),
        "last_active_at": _parse_datetime(_item_value(raw_item, "wot_last_activity", "account_last_activity")),
        "has_tier_11": has_tier_11,
        "supplier_price": supplier_price,
        "sale_price": sale_price,
        "registered_at": _parse_datetime(_item_value(raw_item, "wot_register_date")),
        "is_phone_bound": bool(int(_item_value(raw_item, "wot_mobile") or 0)),
        "is_in_clan": bool(_item_value(raw_item, "wot_clan")),
        "tanks_text": _build_tanks_text(tanks_payload),
        "region": region,
        "tanks_payload": tanks_payload,
        "supplier_loaded_at": _parse_datetime(
            _item_value(raw_item, "published_date", "refreshed_date", "supplier_loaded_at")
        ),
    }
    if preserve_local_id is not None:
        row["id"] = preserve_local_id
    return row


def _item_value(raw_item: dict[str, Any], *keys: str) -> Any:
    wot_data = raw_item.get("wotData")
    category = raw_item.get("category")

    for key in keys:
        if key in raw_item and raw_item[key] not in (None, ""):
            return raw_item[key]
        if isinstance(wot_data, dict) and key in wot_data and wot_data[key] not in (None, ""):
            return wot_data[key]
        if isinstance(category, dict) and key in category and category[key] not in (None, ""):
            return category[key]
    return None


def _resolve_top_premium_count(raw_item: dict[str, Any]) -> int:
    raw_count = _item_value(raw_item, "wot_top_premium_tanks")
    if raw_count not in (None, ""):
        return int(raw_count)

    top_premium_tanks = _item_value(raw_item, "wotTopPremiumTanks")
    if isinstance(top_premium_tanks, dict):
        return len(top_premium_tanks)
    if isinstance(top_premium_tanks, list):
        return len(top_premium_tanks)
    return 0


def _collect_unique_top_names(raw_item: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("wotTopTanks", "wotTopPremiumTanks"):
        raw_tanks = _item_value(raw_item, key)
        if isinstance(raw_tanks, dict):
            items = raw_tanks.values()
        elif isinstance(raw_tanks, list):
            items = raw_tanks
        else:
            items = []

        for raw_tank in items:
            if not isinstance(raw_tank, dict):
                continue
            short_name = str(raw_tank.get("short_name") or raw_tank.get("name") or "").strip()
            if short_name:
                names.add(short_name)
    return names


def _normalize_tanks_payload(raw_item: dict[str, Any]) -> list[dict[str, object]]:
    raw_tanks = _item_value(raw_item, "wotTanks")
    if isinstance(raw_tanks, dict):
        items = raw_tanks.values()
    elif isinstance(raw_tanks, list):
        items = raw_tanks
    else:
        items = []

    normalized: list[dict[str, object]] = []
    for raw_tank in items:
        if not isinstance(raw_tank, dict):
            continue
        short_name = str(raw_tank.get("short_name") or raw_tank.get("name") or "").strip()
        if not short_name:
            continue
        name = str(raw_tank.get("name") or short_name).strip()
        normalized.append(
            {
                "tank_id": int(raw_tank.get("tank_id") or 0) or None,
                "name": name,
                "short_name": short_name,
                "name_en": _to_optional_string(raw_tank.get("name_en")),
                "short_name_en": _to_optional_string(raw_tank.get("short_name_en")),
                "tier": int(raw_tank.get("tier") or 0),
                "is_premium": bool(raw_tank.get("is_premium")),
                "region": _to_optional_string(raw_tank.get("region")),
                "image_url": _normalize_image_url(raw_tank.get("image_url")),
                "alt_image_url": _normalize_image_url(raw_tank.get("alt_image_url")),
            }
        )

    normalized.sort(
        key=lambda item: (
            -int(item["tier"]),
            -int(bool(item["is_premium"])),
            str(item["short_name"]),
        )
    )
    return normalized


def _build_tanks_text(tanks_payload: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for tank in tanks_payload:
        tier = int(tank.get("tier") or 0)
        if tier == 1:
            continue
        name = str(tank.get("short_name") or "")
        if not name:
            continue
        if bool(tank.get("is_premium")):
            name = f"{name} (Премиум)"
        lines.append(f"({tier}) -> {name}")
    return "\n".join(lines)


def _normalize_image_url(value: Any) -> str | None:
    normalized = _to_optional_string(value)
    if normalized is None:
        return None
    if normalized.startswith("//"):
        return f"https:{normalized}"
    return normalized


def _resolve_game_type(*, category_slug: str, region: str) -> GameAccountType | None:
    is_ru = region == "ru"
    if category_slug in {"wot-1", LZT_WORLD_OF_TANKS_ENDPOINT}:
        return GameAccountType.MIR_TANKOV if is_ru else GameAccountType.WORLD_OF_TANKS
    if category_slug in {"wotblitz-1", LZT_WOT_BLITZ_ENDPOINT}:
        return GameAccountType.TANKS_BLITZ if is_ru else GameAccountType.WOT_BLITZ
    return None


def _map_catalog_status(supplier_item_state: str) -> CatalogAccountStatus:
    normalized_state = supplier_item_state.lower()
    if normalized_state == "active":
        return CatalogAccountStatus.AVAILABLE
    if normalized_state in {"reserved", "hold"}:
        return CatalogAccountStatus.RESERVED
    if normalized_state in {"sold", "closed"}:
        return CatalogAccountStatus.SOLD
    return CatalogAccountStatus.ARCHIVED


def _parse_datetime(raw_value: Any) -> datetime | None:
    if raw_value in (None, "", 0, "0"):
        return None
    if isinstance(raw_value, datetime):
        return raw_value.astimezone(UTC) if raw_value.tzinfo else raw_value.replace(tzinfo=UTC)
    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(int(raw_value), tz=UTC)
    if isinstance(raw_value, str):
        stripped_value = raw_value.strip()
        if stripped_value.isdigit():
            return datetime.fromtimestamp(int(stripped_value), tz=UTC)
        iso_value = stripped_value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(iso_value)
        except ValueError:
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _days_since_timestamp(raw_value: Any) -> int:
    parsed = _parse_datetime(raw_value)
    if parsed is None:
        return 0
    return max((datetime.now(tz=UTC) - parsed).days, 0)


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _ceil_div(value: int, divisor: int) -> int:
    if value <= 0:
        return 0
    return (value + divisor - 1) // divisor


def _to_optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip()
    return normalized or None


def _extract_change_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    raw_errors = payload.get("errors")
    if not isinstance(raw_errors, list):
        return ()

    lines: list[str] = []
    for entry in raw_errors:
        if not isinstance(entry, str):
            continue
        for match in re.findall(r"(Изменил(?:ась|ось|ся).+?(?:\.)?(?=\n|$))", entry):
            cleaned = match.strip().rstrip(".")
            if cleaned:
                lines.append(cleaned)

    return tuple(dict.fromkeys(lines))


def _is_retry_request_error(error: LztApiResponseError) -> bool:
    return any("retry_request" in entry.lower() for entry in _iter_error_messages(error.payload))


def _has_supplier_change_notice(payload: dict[str, Any]) -> bool:
    for entry in _iter_error_messages(payload):
        normalized = entry.lower()
        if "серьезные изменения" in normalized or "обновите страницу" in normalized:
            return True
    return bool(_extract_change_lines(payload))


def _iter_error_messages(payload: dict[str, Any]) -> tuple[str, ...]:
    raw_errors = payload.get("errors")
    if not isinstance(raw_errors, list):
        return ()
    return tuple(entry for entry in raw_errors if isinstance(entry, str))


def _build_local_change_lines(account: CatalogAccount, normalized: dict[str, object]) -> tuple[str, ...]:
    fields: tuple[tuple[str, str, Callable[[Any], str]], ...] = (
        ("top_tank_count", "Количество топов", lambda value: str(value)),
        ("premium_tank_count", "Количество премиум-танков", lambda value: str(value)),
        ("total_tank_count", "Количество танков", lambda value: str(value)),
        ("gold_amount", "Количество золота", lambda value: str(value)),
        ("silver_amount", "Количество серебра", lambda value: str(value)),
        ("battles_count", "Количество боев", lambda value: str(value)),
        ("wins_count", "Количество побед", lambda value: str(value)),
        ("win_rate_percent", "Процент побед", _format_decimal),
        ("last_active_at", "Последняя активность", _format_datetime_value),
        ("registered_at", "Дата регистрации", _format_datetime_value),
        ("sale_price", "Цена продажи", _format_decimal),
    )

    lines: list[str] = []
    for field_name, label, formatter in fields:
        current_value = getattr(account, field_name)
        new_value = normalized.get(field_name)
        if field_name in {"sale_price", "win_rate_percent"}:
            current_value = _to_decimal(current_value)
            new_value = _to_decimal(new_value)
        if current_value == new_value:
            continue
        lines.append(f"Изменилось поле «{label}» ({formatter(current_value)} -> {formatter(new_value)})")

    return tuple(lines)


def _apply_account_mapping(account: CatalogAccount, data: dict[str, object]) -> None:
    for field_name, value in data.items():
        if field_name == "id":
            continue
        setattr(account, field_name, value)


def _seconds_until_next_moscow_midnight() -> float:
    now = datetime.now(tz=LZT_MOSCOW_TIMEZONE)
    tomorrow = now.date() + timedelta(days=1)
    next_midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=LZT_MOSCOW_TIMEZONE)
    return max((next_midnight - now).total_seconds(), 1.0)


def _format_decimal(value: Any) -> str:
    decimal_value = _to_decimal(value).quantize(Decimal("0.01"))
    if decimal_value == decimal_value.to_integral():
        return str(int(decimal_value))
    return f"{decimal_value:.2f}"


def _format_datetime_value(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")

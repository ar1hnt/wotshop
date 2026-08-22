import logging

from datetime import UTC, datetime, time
from decimal import Decimal
from html import escape

from aiogram.types import User as TelegramUser
from pydantic import ValidationError

from src.config import settings
from src.db import async_session_factory
from src.db.models.catalog_account import CatalogSortField, GameAccountType, SortDirection
from src.db.repositories import (
    CatalogAccountRepository,
    FavoriteRepository,
    UserCatalogFilterRepository,
    UserRepository,
)
from src.i18n import Language, translate
from src.schemas.catalog import (
    CATALOG_PAGE_SIZE,
    FILTER_PAGES_COUNT,
    CatalogAccountDetailSchema,
    CatalogAccountSummarySchema,
    CatalogTankSchema,
    CatalogBooleanChoice,
    CatalogDateRangeInputSchema,
    CatalogDecimalRangeInputSchema,
    CatalogFilterField,
    CatalogFilterSchema,
    CatalogFilterViewSchema,
    CatalogIntegerRangeInputSchema,
    CatalogLastActivityDateInputSchema,
    CatalogResultsPageSchema,
)
from src.schemas.favorites import FavoritesPageSchema

logger = logging.getLogger(__name__)

CATALOG_FAVORITE_PREFIX = "catalog_supplier:"
CATALOG_INACTIVITY_MARK_DAYS = 60

FILTER_FIELD_META: dict[CatalogFilterField, dict[str, str]] = {
    CatalogFilterField.PRICE: {"kind": "decimal", "min": "sale_price_min", "max": "sale_price_max"},
    CatalogFilterField.TOP_TANK_COUNT: {"kind": "int", "min": "top_tank_count_min", "max": "top_tank_count_max"},
    CatalogFilterField.PREMIUM_TANK_COUNT: {"kind": "int", "min": "premium_tank_count_min", "max": "premium_tank_count_max"},
    CatalogFilterField.TOTAL_TANK_COUNT: {"kind": "int", "min": "total_tank_count_min", "max": "total_tank_count_max"},
    CatalogFilterField.SILVER_AMOUNT: {"kind": "int", "min": "silver_amount_min", "max": "silver_amount_max"},
    CatalogFilterField.GOLD_AMOUNT: {"kind": "int", "min": "gold_amount_min", "max": "gold_amount_max"},
    CatalogFilterField.BATTLES_COUNT: {"kind": "int", "min": "battles_count_min", "max": "battles_count_max"},
    CatalogFilterField.WINS_COUNT: {"kind": "int", "min": "wins_count_min", "max": "wins_count_max"},
    CatalogFilterField.WIN_RATE_PERCENT: {"kind": "decimal", "min": "win_rate_percent_min", "max": "win_rate_percent_max"},
    CatalogFilterField.LAST_ACTIVE: {"kind": "date", "min": "last_active_from", "max": "last_active_to"},
    CatalogFilterField.HAS_TIER_11: {"kind": "bool", "field": "has_tier_11"},
    CatalogFilterField.REGISTERED_AT: {"kind": "date", "min": "registered_from", "max": "registered_to"},
    CatalogFilterField.IS_PHONE_BOUND: {"kind": "bool", "field": "is_phone_bound"},
    CatalogFilterField.IS_IN_CLAN: {"kind": "bool", "field": "is_in_clan"},
    CatalogFilterField.TANK_QUERY: {"kind": "text", "field": "tank_query"},
    CatalogFilterField.REGION: {"kind": "text", "field": "region"},
    CatalogFilterField.SUPPLIER_LOADED_AT: {"kind": "date", "min": "supplier_loaded_from", "max": "supplier_loaded_to"},
}

FILTER_PAGE_FIELDS: dict[int, tuple[CatalogFilterField, ...]] = {
    1: (
        CatalogFilterField.PRICE,
        CatalogFilterField.TOP_TANK_COUNT,
        CatalogFilterField.PREMIUM_TANK_COUNT,
        CatalogFilterField.TOTAL_TANK_COUNT,
        CatalogFilterField.SILVER_AMOUNT,
        CatalogFilterField.GOLD_AMOUNT,
        CatalogFilterField.BATTLES_COUNT,
        CatalogFilterField.WINS_COUNT,
        CatalogFilterField.WIN_RATE_PERCENT,
        CatalogFilterField.LAST_ACTIVE,
        CatalogFilterField.HAS_TIER_11,
        CatalogFilterField.REGISTERED_AT,
        CatalogFilterField.IS_PHONE_BOUND,
        CatalogFilterField.IS_IN_CLAN,
        CatalogFilterField.TANK_QUERY,
        CatalogFilterField.REGION,
        CatalogFilterField.SUPPLIER_LOADED_AT,
    ),
}


class CatalogFilterValidationError(Exception):
    pass


class CatalogAccountNotFoundError(Exception):
    pass


class CatalogService:
    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await session.commit()

        return Language(user.language)

    async def get_filter_view(
        self,
        telegram_user: TelegramUser,
        *,
        game_type: GameAccountType,
        page: int = 1,
        flash_message: str | None = None,
    ) -> CatalogFilterViewSchema:
        safe_page = min(max(page, 1), FILTER_PAGES_COUNT)

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            filter_repository = UserCatalogFilterRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            catalog_filter = await filter_repository.get_or_create(user_id=user.id, game_type=game_type)
            await session.commit()

        filter_schema = _to_filter_schema(catalog_filter)
        return CatalogFilterViewSchema(
            language=Language(user.language),
            game_type=game_type,
            page=safe_page,
            total_pages=FILTER_PAGES_COUNT,
            active_filters_count=_count_active_filters(filter_schema),
            catalog_filter=filter_schema,
            flash_message=flash_message,
        )

    async def update_filter_from_text(
        self,
        telegram_user: TelegramUser,
        *,
        game_type: GameAccountType,
        field: CatalogFilterField,
        raw_value: str,
    ) -> CatalogFilterViewSchema:
        meta = FILTER_FIELD_META[field]
        stripped_value = raw_value.strip()

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            filter_repository = UserCatalogFilterRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            catalog_filter = await filter_repository.get_or_create(user_id=user.id, game_type=game_type)

            try:
                if meta["kind"] == "int":
                    parsed = CatalogIntegerRangeInputSchema.from_raw(stripped_value)
                    await filter_repository.set_range(
                        catalog_filter,
                        min_field=meta["min"],
                        max_field=meta["max"],
                        min_value=parsed.min_value,
                        max_value=parsed.max_value,
                    )
                elif meta["kind"] == "decimal":
                    parsed = CatalogDecimalRangeInputSchema.from_raw(stripped_value)
                    await filter_repository.set_range(
                        catalog_filter,
                        min_field=meta["min"],
                        max_field=meta["max"],
                        min_value=parsed.min_value,
                        max_value=parsed.max_value,
                    )
                elif meta["kind"] == "date":
                    if field == CatalogFilterField.LAST_ACTIVE:
                        parsed = CatalogLastActivityDateInputSchema.from_raw(stripped_value)
                    else:
                        parsed = CatalogDateRangeInputSchema.from_raw(stripped_value)
                    await filter_repository.set_datetime_range(
                        catalog_filter,
                        from_field=meta["min"],
                        to_field=meta["max"],
                        from_value=_local_day_start_to_utc(parsed.date_from) if parsed.date_from else None,
                        to_value=_local_day_end_to_utc(parsed.date_to) if parsed.date_to else None,
                    )
                else:
                    normalized_text = stripped_value if stripped_value else None
                    await filter_repository.set_text(
                        catalog_filter,
                        field_name=meta["field"],
                        value=normalized_text,
                    )
            except (ValidationError, ValueError) as error:
                await session.rollback()
                raise CatalogFilterValidationError from error

            await session.commit()

        logger.info("Updated catalog filter telegram_id=%s game_type=%s field=%s, raw_value=%s", telegram_user.id, game_type.value, field.value, raw_value)
        return await self.get_filter_view(
            telegram_user,
            game_type=game_type,
            page=_resolve_filter_page(field),
        )

    async def update_boolean_filter(
        self,
        telegram_user: TelegramUser,
        *,
        game_type: GameAccountType,
        field: CatalogFilterField,
        choice: CatalogBooleanChoice,
    ) -> CatalogFilterViewSchema:
        meta = FILTER_FIELD_META[field]
        bool_value = None if choice == CatalogBooleanChoice.ANY else choice == CatalogBooleanChoice.YES

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            filter_repository = UserCatalogFilterRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            catalog_filter = await filter_repository.get_or_create(user_id=user.id, game_type=game_type)
            await filter_repository.set_boolean(catalog_filter, field_name=meta["field"], value=bool_value)
            await session.commit()

        return await self.get_filter_view(
            telegram_user,
            game_type=game_type,
            page=_resolve_filter_page(field),
        )

    async def reset_filter(self, telegram_user: TelegramUser, *, game_type: GameAccountType) -> CatalogFilterViewSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            filter_repository = UserCatalogFilterRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            catalog_filter = await filter_repository.get_or_create(user_id=user.id, game_type=game_type)
            await filter_repository.reset(catalog_filter)
            await session.commit()

        return await self.get_filter_view(
            telegram_user,
            game_type=game_type,
            page=1,
        )

    async def clear_filter_field(
        self,
        telegram_user: TelegramUser,
        *,
        game_type: GameAccountType,
        field: CatalogFilterField,
    ) -> CatalogFilterViewSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            filter_repository = UserCatalogFilterRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            catalog_filter = await filter_repository.get_or_create(user_id=user.id, game_type=game_type)
            await self._clear_single_filter(filter_repository, catalog_filter, field)
            await session.commit()

        return await self.get_filter_view(
            telegram_user,
            game_type=game_type,
            page=_resolve_filter_page(field),
        )

    async def get_search_results(
        self,
        telegram_user: TelegramUser,
        *,
        game_type: GameAccountType,
        page: int = 1,
    ) -> CatalogResultsPageSchema:
        safe_page = max(page, 1)

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            filter_repository = UserCatalogFilterRepository(session)
            account_repository = CatalogAccountRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            catalog_filter = await filter_repository.get_or_create(user_id=user.id, game_type=game_type)
            total_count, items = await account_repository.search_page(
                catalog_filter,
                page=safe_page,
                page_size=CATALOG_PAGE_SIZE,
            )
            await session.commit()

        total_pages = max(1, (total_count + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE)
        if safe_page > total_pages:
            return await self.get_search_results(telegram_user, game_type=game_type, page=total_pages)

        return CatalogResultsPageSchema(
            language=Language(user.language),
            game_type=game_type,
            page=safe_page,
            total_pages=total_pages,
            total_count=total_count,
            active_sort_field=CatalogSortField(catalog_filter.active_sort_field),
            price_sort_direction=SortDirection(catalog_filter.price_sort_direction),
            last_activity_sort_direction=SortDirection(catalog_filter.last_activity_sort_direction),
            newest_sort_direction=SortDirection(catalog_filter.newest_sort_direction),
            items=tuple(_to_summary_schema(item) for item in items),
        )

    async def toggle_sort(
        self,
        telegram_user: TelegramUser,
        *,
        game_type: GameAccountType,
        field: CatalogSortField,
    ) -> CatalogResultsPageSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            filter_repository = UserCatalogFilterRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            catalog_filter = await filter_repository.get_or_create(user_id=user.id, game_type=game_type)
            field_name_map = {
                CatalogSortField.PRICE: "price_sort_direction",
                CatalogSortField.LAST_ACTIVITY: "last_activity_sort_direction",
                CatalogSortField.NEWEST: "newest_sort_direction",
            }
            current_active_field = CatalogSortField(catalog_filter.active_sort_field)
            current_direction = SortDirection(getattr(catalog_filter, field_name_map[field]))
            if current_active_field == field:
                next_direction = SortDirection.ASC if current_direction == SortDirection.DESC else SortDirection.DESC
            else:
                next_direction = current_direction

            await filter_repository.set_sort(catalog_filter, field=field, direction=next_direction)
            await session.commit()

        return await self.get_search_results(telegram_user, game_type=game_type, page=1)

    async def get_account_detail(
        self,
        telegram_user: TelegramUser,
        *,
        account_id: int,
        detail_page: int = 1,
    ) -> CatalogAccountDetailSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            favorite_repository = FavoriteRepository(session)
            account_repository = CatalogAccountRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            account = await account_repository.get_by_id(account_id)
            if account is None:
                await session.rollback()
                raise CatalogAccountNotFoundError

            is_favorite = await favorite_repository.exists(
                user_id=user.id,
                product_code=_favorite_code(account.supplier_item_id),
            )
            await session.commit()

        detail = CatalogAccountDetailSchema(
            language=Language(user.language),
            id=account.id,
            game_type=GameAccountType(account.game_type),
            top_tank_count=account.top_tank_count,
            premium_tank_count=account.premium_tank_count,
            total_tank_count=account.total_tank_count,
            silver_amount=account.silver_amount,
            gold_amount=account.gold_amount,
            battles_count=account.battles_count,
            wins_count=account.wins_count,
            win_rate_percent=_to_decimal(account.win_rate_percent),
            last_active_at=account.last_active_at,
            has_tier_11=account.has_tier_11,
            sale_price=_to_decimal(account.sale_price),
            registered_at=account.registered_at,
            is_phone_bound=account.is_phone_bound,
            is_in_clan=account.is_in_clan,
            tanks_text=account.tanks_text,
            tanks_payload=_parse_tanks_payload(account.tanks_payload, fallback_text=account.tanks_text),
            region=account.region,
            supplier_loaded_at=account.supplier_loaded_at,
            is_favorite=is_favorite,
        )
        total_detail_pages = len(_build_catalog_detail_pages(detail))
        safe_detail_page = min(max(detail_page, 1), total_detail_pages)
        return detail.model_copy(update={"detail_page": safe_detail_page, "total_detail_pages": total_detail_pages})

    async def toggle_favorite(
        self,
        telegram_user: TelegramUser,
        *,
        account_id: int,
    ) -> tuple[CatalogAccountDetailSchema, bool]:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            favorite_repository = FavoriteRepository(session)
            account_repository = CatalogAccountRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            account = await account_repository.get_by_id(account_id)
            if account is None:
                await session.rollback()
                raise CatalogAccountNotFoundError

            favorite = await favorite_repository.get_by_user_and_code(
                user_id=user.id,
                product_code=_favorite_code(account.supplier_item_id),
            )
            is_added = favorite is None
            if favorite is None:
                await favorite_repository.add(user_id=user.id, product_code=_favorite_code(account.supplier_item_id))
            else:
                await favorite_repository.remove(favorite)
            await session.commit()

        return await self.get_account_detail(telegram_user, account_id=account_id), is_added

    async def get_favorites_page(
        self,
        telegram_user: TelegramUser,
        *,
        page: int = 1,
    ) -> FavoritesPageSchema:
        safe_page = max(page, 1)

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            favorite_repository = FavoriteRepository(session)
            account_repository = CatalogAccountRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            favorites = await favorite_repository.list_by_user_and_prefix(
                user_id=user.id,
                prefix=CATALOG_FAVORITE_PREFIX,
            )

            favorite_supplier_ids = []
            for favorite in favorites:
                raw_supplier_item_id = favorite.product_code.removeprefix(CATALOG_FAVORITE_PREFIX)
                if raw_supplier_item_id.isdigit():
                    favorite_supplier_ids.append((favorite, int(raw_supplier_item_id)))

            supplier_item_ids = [supplier_item_id for _, supplier_item_id in favorite_supplier_ids]
            accounts_by_supplier_id = {
                account.supplier_item_id: account
                for account in await account_repository.list_by_supplier_item_ids(supplier_item_ids)
            }
            accounts = []
            missing_favorite_ids: list[int] = []
            for favorite, supplier_item_id in favorite_supplier_ids:
                account = accounts_by_supplier_id.get(supplier_item_id)
                if account is None:
                    missing_favorite_ids.append(favorite.id)
                    continue
                accounts.append(account)
            removed_count = await favorite_repository.remove_by_ids(missing_favorite_ids)
            if removed_count:
                logger.info("Removed %s unavailable catalog favorites user_id=%s", removed_count, user.id)
            await session.commit()

        total_count = len(accounts)
        total_pages = max(1, (total_count + CATALOG_PAGE_SIZE - 1) // CATALOG_PAGE_SIZE)
        safe_page = min(safe_page, total_pages)
        page_items = accounts[(safe_page - 1) * CATALOG_PAGE_SIZE:safe_page * CATALOG_PAGE_SIZE]

        return FavoritesPageSchema(
            language=Language(user.language),
            page=safe_page,
            total_pages=total_pages,
            total_count=total_count,
            items=tuple(_to_summary_schema(item) for item in page_items),
        )

    async def _clear_single_filter(
        self,
        filter_repository: UserCatalogFilterRepository,
        catalog_filter,
        field: CatalogFilterField,
    ) -> None:
        meta = FILTER_FIELD_META[field]
        if meta["kind"] in {"int", "decimal"}:
            await filter_repository.set_range(
                catalog_filter,
                min_field=meta["min"],
                max_field=meta["max"],
                min_value=None,
                max_value=None,
            )
            return
        if meta["kind"] == "date":
            await filter_repository.set_datetime_range(
                catalog_filter,
                from_field=meta["min"],
                to_field=meta["max"],
                from_value=None,
                to_value=None,
            )
            return
        if meta["kind"] == "bool":
            await filter_repository.set_boolean(catalog_filter, field_name=meta["field"], value=None)
            return
        await filter_repository.set_text(catalog_filter, field_name=meta["field"], value=None)


def render_catalog_game_type_text(language: Language) -> str:
    return translate(language, "catalog_game_type_title")


def render_catalog_filter_text(view: CatalogFilterViewSchema) -> str:
    lines = [
        translate(view.language, "catalog_filter_title", game_type=_game_type_label(view.language, view.game_type)),
        "",
        translate(view.language, "catalog_filter_active_count", count=view.active_filters_count),
    ]
    return "\n".join(lines)


def render_catalog_filter_input_prompt(
    language: Language,
    field: CatalogFilterField,
    *,
    current_value: str,
) -> str:
    kind = FILTER_FIELD_META[field]["kind"]
    title = translate(language, "catalog_filter_input_title", field=_filter_field_label(language, field))
    if kind == "int":
        body = translate(language, "catalog_filter_input_integer_hint")
    elif kind == "decimal":
        body = translate(language, "catalog_filter_input_decimal_hint")
    elif kind == "date":
        if field == CatalogFilterField.LAST_ACTIVE:
            body = translate(language, "catalog_filter_input_last_active_hint")
        else:
            body = translate(language, "catalog_filter_input_date_hint")
    else:
        if field == CatalogFilterField.TANK_QUERY:
            body = translate(language, "catalog_filter_input_tank_query_hint")
        else:
            body = translate(language, "catalog_filter_input_text_hint")
    current_value_text = translate(language, "catalog_filter_input_current_value", value=current_value)
    return "\n".join((title, "", current_value_text, "", body))


def render_catalog_boolean_prompt(language: Language, field: CatalogFilterField, *, current_value: str) -> str:
    return translate(
        language,
        "catalog_filter_boolean_prompt",
        field=_filter_field_label(language, field),
        value=current_value,
    )


def render_catalog_results_text(results: CatalogResultsPageSchema) -> str:
    lines = [
        translate(results.language, "catalog_results_title", game_type=_game_type_label(results.language, results.game_type)),
        "",
        translate(results.language, "catalog_results_found", count=results.total_count),
        translate(results.language, "catalog_results_page_meta", page=results.page, total_pages=results.total_pages),
        "",
    ]
    lines.append(
        translate(results.language, "catalog_results_empty")
        if results.total_count == 0
        else translate(results.language, "catalog_results_hint")
    )
    return "\n".join(lines)


def render_catalog_detail_text(detail: CatalogAccountDetailSchema) -> str:
    pages = _build_catalog_detail_pages(detail)
    body = pages[detail.detail_page - 1]
    return "\n\n".join(
        (
            translate(detail.language, "catalog_detail_title", account_id=detail.id),
            translate(
                detail.language,
                "catalog_detail_page_meta",
                page=detail.detail_page,
                total_pages=detail.total_detail_pages,
            ),
            body,
        )
    )


def build_catalog_account_button_text(item: CatalogAccountSummarySchema) -> str:
    preview = ", ".join(item.top_tanks_preview) if item.top_tanks_preview else "..."
    prefixes: list[str] = []
    if _is_new_today(item.supplier_loaded_at):
        prefixes.append("🆕 NEW")
    if _has_long_inactivity(item.last_active_at):
        prefixes.append("🕸")
    prefix = f"{' | '.join(prefixes)} | " if prefixes else ""
    return f"{prefix}{_format_money(item.sale_price)} RUB | {preview}"


def render_catalog_favorite_alert(language: Language, *, added: bool) -> str:
    key = "catalog_favorite_added" if added else "catalog_favorite_removed"
    return translate(language, key)


def render_catalog_buy_placeholder(language: Language) -> str:
    return translate(language, "catalog_buy_placeholder")


def render_catalog_refresh_placeholder(language: Language) -> str:
    return translate(language, "catalog_refresh_placeholder")


def render_favorites_text(page: FavoritesPageSchema) -> str:
    lines = [
        translate(page.language, "favorites_title"),
        "",
        translate(page.language, "favorites_found", count=page.total_count),
        translate(page.language, "favorites_page_meta", page=page.page, total_pages=page.total_pages),
        "",
    ]
    lines.append(
        translate(page.language, "favorites_empty")
        if page.total_count == 0
        else translate(page.language, "favorites_hint")
    )
    return "\n".join(lines)


def _filter_value_label(language: Language, catalog_filter: CatalogFilterSchema, field: CatalogFilterField) -> str:
    meta = FILTER_FIELD_META[field]
    if meta["kind"] in {"int", "decimal"}:
        min_value = getattr(catalog_filter, meta["min"])
        max_value = getattr(catalog_filter, meta["max"])
        if min_value is None and max_value is None:
            return translate(language, "catalog_filter_not_set")
        if min_value is not None and max_value is not None and min_value == max_value:
            return _format_filter_number(min_value)
        if min_value is not None and max_value is None:
            return f"{_format_filter_number(min_value)}+"
        return f"{_format_filter_number(min_value)}-{_format_filter_number(max_value)}"

    if meta["kind"] == "date":
        start_at = getattr(catalog_filter, meta["min"])
        end_at = getattr(catalog_filter, meta["max"])
        if start_at is None and end_at is None:
            return translate(language, "catalog_filter_not_set")
        if start_at is not None and end_at is not None and start_at.date() == end_at.date():
            return start_at.astimezone(settings.default_timezone).strftime("%d.%m.%Y")
        if field == CatalogFilterField.LAST_ACTIVE and start_at is None and end_at is not None:
            return f"-{end_at.astimezone(settings.default_timezone).strftime('%d.%m.%Y')}"
        if start_at is not None and end_at is None:
            return f"{start_at.astimezone(settings.default_timezone).strftime('%d.%m.%Y')}+"
        start_text = start_at.astimezone(settings.default_timezone).strftime("%d.%m.%Y") if start_at else "?"
        end_text = end_at.astimezone(settings.default_timezone).strftime("%d.%m.%Y") if end_at else "?"
        return f"{start_text}-{end_text}"

    if meta["kind"] == "bool":
        value = getattr(catalog_filter, meta["field"])
        if value is None:
            return translate(language, "catalog_filter_not_set")
        return _bool_label(language, value)

    value = getattr(catalog_filter, meta["field"])
    if not value:
        return translate(language, "catalog_filter_not_set")
    return escape(str(value))


def get_catalog_filter_value_label(language: Language, catalog_filter: CatalogFilterSchema, field: CatalogFilterField) -> str:
    return _filter_value_label(language, catalog_filter, field)


def _count_active_filters(catalog_filter: CatalogFilterSchema) -> int:
    count = 0
    visible_fields = set(_filter_page_fields(catalog_filter.game_type, 1))
    for field, meta in FILTER_FIELD_META.items():
        if field not in visible_fields:
            continue
        if meta["kind"] in {"int", "decimal", "date"}:
            if getattr(catalog_filter, meta["min"]) is not None or getattr(catalog_filter, meta["max"]) is not None:
                count += 1
        else:
            if getattr(catalog_filter, meta["field"]) not in (None, ""):
                count += 1
    return count


def _to_filter_schema(catalog_filter) -> CatalogFilterSchema:
    return CatalogFilterSchema(
        game_type=GameAccountType(catalog_filter.game_type),
        sale_price_min=_to_optional_decimal(catalog_filter.sale_price_min),
        sale_price_max=_to_optional_decimal(catalog_filter.sale_price_max),
        top_tank_count_min=catalog_filter.top_tank_count_min,
        top_tank_count_max=catalog_filter.top_tank_count_max,
        premium_tank_count_min=catalog_filter.premium_tank_count_min,
        premium_tank_count_max=catalog_filter.premium_tank_count_max,
        total_tank_count_min=catalog_filter.total_tank_count_min,
        total_tank_count_max=catalog_filter.total_tank_count_max,
        silver_amount_min=catalog_filter.silver_amount_min,
        silver_amount_max=catalog_filter.silver_amount_max,
        gold_amount_min=catalog_filter.gold_amount_min,
        gold_amount_max=catalog_filter.gold_amount_max,
        battles_count_min=catalog_filter.battles_count_min,
        battles_count_max=catalog_filter.battles_count_max,
        wins_count_min=catalog_filter.wins_count_min,
        wins_count_max=catalog_filter.wins_count_max,
        win_rate_percent_min=_to_optional_decimal(catalog_filter.win_rate_percent_min),
        win_rate_percent_max=_to_optional_decimal(catalog_filter.win_rate_percent_max),
        last_active_from=catalog_filter.last_active_from,
        last_active_to=catalog_filter.last_active_to,
        has_tier_11=catalog_filter.has_tier_11,
        registered_from=catalog_filter.registered_from,
        registered_to=catalog_filter.registered_to,
        is_phone_bound=catalog_filter.is_phone_bound,
        is_in_clan=catalog_filter.is_in_clan,
        tank_query=catalog_filter.tank_query,
        region=catalog_filter.region,
        supplier_loaded_from=catalog_filter.supplier_loaded_from,
        supplier_loaded_to=catalog_filter.supplier_loaded_to,
        active_sort_field=CatalogSortField(catalog_filter.active_sort_field),
        price_sort_direction=SortDirection(catalog_filter.price_sort_direction),
        last_activity_sort_direction=SortDirection(catalog_filter.last_activity_sort_direction),
        newest_sort_direction=SortDirection(catalog_filter.newest_sort_direction),
    )


def _to_summary_schema(account) -> CatalogAccountSummarySchema:
    return CatalogAccountSummarySchema(
        id=account.id,
        game_type=GameAccountType(account.game_type),
        sale_price=_to_decimal(account.sale_price),
        top_tanks_preview=tuple(_extract_top_tanks_preview(account.tanks_payload, account.tanks_text)),
        last_active_at=account.last_active_at,
        supplier_loaded_at=account.supplier_loaded_at,
    )


def _build_catalog_detail_pages(detail: CatalogAccountDetailSchema) -> tuple[str, ...]:
    max_page_length = 760
    blocks = [
        translate(detail.language, "catalog_detail_sale_price", value=_format_money(detail.sale_price)),
        "",
        translate(detail.language, "catalog_detail_game_type", value=_game_type_label(detail.language, detail.game_type)),
        translate(detail.language, "catalog_detail_region", value=escape(detail.region or "-")),
        "",
        translate(detail.language, "catalog_detail_top_count", value=detail.top_tank_count),
        translate(detail.language, "catalog_detail_premium_count", value=detail.premium_tank_count),
        translate(detail.language, "catalog_detail_total_tanks", value=detail.total_tank_count),
        translate(detail.language, "catalog_detail_silver", value=f"{detail.silver_amount:,}".replace(",", " ")),
        translate(detail.language, "catalog_detail_gold", value=f"{detail.gold_amount:,}".replace(",", " ")),
        translate(detail.language, "catalog_detail_battles", value=detail.battles_count),
        translate(detail.language, "catalog_detail_wins", value=detail.wins_count),
        translate(detail.language, "catalog_detail_win_rate", value=_format_money(detail.win_rate_percent)),
        # translate(detail.language, "catalog_detail_has_tier_11", value=_bool_label(detail.language, detail.has_tier_11)),
        translate(detail.language, "catalog_detail_phone_bound", value=_bool_label(detail.language, detail.is_phone_bound)),
        translate(detail.language, "catalog_detail_in_clan", value=_bool_label(detail.language, detail.is_in_clan)),
        "",
        translate(
            detail.language,
            "catalog_detail_last_active",
            value=_format_last_activity(detail.language, detail.last_active_at),
        ),
        "",
        translate(detail.language, "catalog_detail_registered_at", value=_format_datetime(detail.registered_at)),
        ""
    ]
    first_page = "\n".join(blocks) or "-"
    tank_lines = _build_tank_lines(detail.tanks_payload, fallback_text=detail.tanks_text)
    tank_pages = _build_tank_pages(
        tank_lines=tank_lines,
        language=detail.language,
        max_page_length=max_page_length,
    )
    return (first_page, *tank_pages)

def _build_tank_pages(
    *,
    tank_lines: list[str],
    language: Language,
    max_page_length: int,
) -> tuple[str, ...]:
    if not tank_lines:
        empty_block = f"{translate(language, 'catalog_detail_tanks')}\n<blockquote>-</blockquote>"
        return (empty_block,)

    rendered_pages: list[str] = []
    remaining_lines = list(tank_lines)
    is_first_block = True

    while remaining_lines:
        heading = (
            translate(language, "catalog_detail_tanks")
            if is_first_block
            else translate(language, "catalog_detail_tanks_continued")
        )
        available_length = max_page_length

        chunk: list[str] = []
        for line in remaining_lines:
            candidate = chunk + [line]
            block = _render_tank_block(heading, candidate)
            if len(block) <= available_length:
                chunk = candidate
                continue
            break

        if not chunk:
            chunk = [remaining_lines[0]]

        block = _render_tank_block(heading, chunk)
        rendered_pages.append(block)
        remaining_lines = remaining_lines[len(chunk):]
        is_first_block = False

    return tuple(page for page in rendered_pages if page) or ("-",)


def _render_tank_block(heading: str, lines: list[str]) -> str:
    return f"{heading}\n<blockquote>{'\n'.join(lines)}</blockquote>"


def _paginate_catalog_detail_blocks(blocks: list[str], *, max_page_length: int) -> tuple[str, ...]:
    pages: list[str] = []
    current_blocks: list[str] = []
    current_length = 0

    for block in blocks:
        separator_length = 2 if current_blocks else 0
        next_length = current_length + separator_length + len(block)
        if current_blocks and next_length > max_page_length:
            pages.append("\n".join(current_blocks))
            current_blocks = [block]
            current_length = len(block)
            continue
        current_blocks.append(block)
        current_length = next_length

    if current_blocks:
        pages.append("\n".join(current_blocks))

    return tuple(pages or ["-"])


def _extract_top_tanks_preview(tanks_payload: list[dict[str, object]] | None, tanks_text: str) -> list[str]:
    tanks = _parse_tanks_payload(tanks_payload, fallback_text=tanks_text)
    if not tanks:
        return []

    preferred: list[str] = []
    fallback: list[str] = []
    seen: set[str] = set()

    for tank in tanks:
        label = _tank_short_label(tank)
        if not label or label in seen:
            continue
        seen.add(label)

        if tank.tier >= 10:
            preferred.append(label)
        elif tank.is_premium or tank.tier >= 8:
            fallback.append(label)
        else:
            fallback.append(label)

    return (preferred + fallback)[:3]


def _build_tank_lines(
    tanks_payload: tuple[CatalogTankSchema, ...],
    *,
    fallback_text: str,
) -> list[str]:
    if tanks_payload:
        return [escape(_tank_detail_label(tank)) for tank in tanks_payload if _tank_detail_label(tank)]

    return [escape(line) for line in fallback_text.splitlines() if line.strip()]


def _parse_tanks_payload(
    raw_payload: list[dict[str, object]] | tuple[dict[str, object], ...] | None,
    *,
    fallback_text: str,
) -> tuple[CatalogTankSchema, ...]:
    parsed: list[CatalogTankSchema] = []

    if raw_payload:
        for raw_tank in raw_payload:
            if not isinstance(raw_tank, dict):
                continue
            short_name = str(raw_tank.get("short_name") or raw_tank.get("name") or "").strip()
            if not short_name:
                continue
            name = str(raw_tank.get("name") or short_name).strip()
            parsed.append(
                CatalogTankSchema(
                    tank_id=_to_optional_int(raw_tank.get("tank_id")),
                    name=name,
                    short_name=short_name,
                    name_en=_to_optional_str(raw_tank.get("name_en")),
                    short_name_en=_to_optional_str(raw_tank.get("short_name_en")),
                    tier=_to_optional_int(raw_tank.get("tier")) or 0,
                    is_premium=bool(raw_tank.get("is_premium")),
                    region=_to_optional_str(raw_tank.get("region")),
                    image_url=_to_optional_str(raw_tank.get("image_url")),
                    alt_image_url=_to_optional_str(raw_tank.get("alt_image_url")),
                )
            )

    if parsed:
        return tuple(parsed)

    fallback_lines = [line.strip() for line in fallback_text.splitlines() if line.strip()]
    return tuple(
        CatalogTankSchema(
            name=line,
            short_name=line,
        )
        for line in fallback_lines
    )


def _tank_short_label(tank: CatalogTankSchema) -> str:
    return tank.short_name.strip() or tank.name.strip()


def _tank_detail_label(tank: CatalogTankSchema) -> str:
    label = _tank_short_label(tank)
    if not label:
        return ""
    suffix = " (Премиум)" if tank.is_premium else ""
    if tank.tier > 0:
        return f"({tank.tier}) -> {label}{suffix}"
    return f"{label}{suffix}"


def _to_optional_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _favorite_code(supplier_item_id: int) -> str:
    return f"{CATALOG_FAVORITE_PREFIX}{supplier_item_id}"


def _game_type_label(language: Language, game_type: GameAccountType) -> str:
    key_by_type = {
        GameAccountType.MIR_TANKOV: "catalog_game_type_mir_tankov",
        GameAccountType.TANKS_BLITZ: "catalog_game_type_tanks_blitz",
        GameAccountType.WORLD_OF_TANKS: "catalog_game_type_world_of_tanks",
        GameAccountType.WOT_BLITZ: "catalog_game_type_wot_blitz",
    }
    return translate(language, key_by_type[game_type])


def _filter_field_label(language: Language, field: CatalogFilterField) -> str:
    key_by_field = {
        CatalogFilterField.PRICE: "catalog_filter_field_price",
        CatalogFilterField.TOP_TANK_COUNT: "catalog_filter_field_top_tanks",
        CatalogFilterField.PREMIUM_TANK_COUNT: "catalog_filter_field_premium_tanks",
        CatalogFilterField.TOTAL_TANK_COUNT: "catalog_filter_field_total_tanks",
        CatalogFilterField.SILVER_AMOUNT: "catalog_filter_field_silver",
        CatalogFilterField.GOLD_AMOUNT: "catalog_filter_field_gold",
        CatalogFilterField.BATTLES_COUNT: "catalog_filter_field_battles",
        CatalogFilterField.WINS_COUNT: "catalog_filter_field_wins",
        CatalogFilterField.WIN_RATE_PERCENT: "catalog_filter_field_win_rate",
        CatalogFilterField.LAST_ACTIVE: "catalog_filter_field_last_active",
        CatalogFilterField.HAS_TIER_11: "catalog_filter_field_has_tier_11",
        CatalogFilterField.REGISTERED_AT: "catalog_filter_field_registered_at",
        CatalogFilterField.IS_PHONE_BOUND: "catalog_filter_field_phone_bound",
        CatalogFilterField.IS_IN_CLAN: "catalog_filter_field_in_clan",
        CatalogFilterField.TANK_QUERY: "catalog_filter_field_tank_query",
        CatalogFilterField.REGION: "catalog_filter_field_region",
        CatalogFilterField.SUPPLIER_LOADED_AT: "catalog_filter_field_supplier_loaded_at",
    }
    return translate(language, key_by_field[field])


def _bool_label(language: Language, value: bool) -> str:
    return translate(language, "yes") if value else translate(language, "no")


def _format_money(amount: Decimal) -> str:
    normalized = amount.quantize(Decimal("0.01"))
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{normalized:.2f}"


def _format_filter_number(value: int | Decimal | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        return _format_money(value)
    return f"{value:,}".replace(",", " ")


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")


def _format_last_activity(language: Language, value: datetime | None) -> str:
    formatted_value = _format_datetime(value)
    if value is None:
        return formatted_value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    days_ago = max((datetime.now(UTC) - value.astimezone(UTC)).days, 0)
    return translate(language, "catalog_detail_days_ago", value=formatted_value, days=days_ago)


def _is_new_today(value: datetime | None) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(settings.default_timezone).date() == datetime.now(settings.default_timezone).date()


def _has_long_inactivity(value: datetime | None) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (datetime.now(UTC) - value.astimezone(UTC)).days >= CATALOG_INACTIVITY_MARK_DAYS


def _local_day_start_to_utc(value: datetime) -> datetime:
    localized = datetime.combine(value.date(), time.min, tzinfo=settings.default_timezone)
    return localized.astimezone(UTC)


def _local_day_end_to_utc(value: datetime) -> datetime:
    localized = datetime.combine(value.date(), time.max, tzinfo=settings.default_timezone)
    return localized.astimezone(UTC)


def _resolve_filter_page(field: CatalogFilterField) -> int:
    for page, fields in FILTER_PAGE_FIELDS.items():
        if field in fields:
            return page
    return 1


def _filter_page_fields(game_type: GameAccountType, page: int) -> tuple[CatalogFilterField, ...]:
    fields = FILTER_PAGE_FIELDS[page]
    if game_type in {GameAccountType.MIR_TANKOV, GameAccountType.TANKS_BLITZ}:
        return tuple(field for field in fields if field != CatalogFilterField.REGION)
    return fields


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3].rstrip()}..."


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_optional_decimal(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return _to_decimal(value)

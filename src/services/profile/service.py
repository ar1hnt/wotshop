import logging

from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from math import ceil

from aiogram.types import User as TelegramUser

from src.config import settings
from src.db import async_session_factory
from src.db.repositories import OrderRepository, UserRepository
from src.i18n import Language, translate
from src.schemas.profile import OrderHistoryEntrySchema, OrderHistoryPageSchema, ProfileSummarySchema


logger = logging.getLogger(__name__)
ORDER_HISTORY_PAGE_SIZE = 10


class ProfileService:
    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await session.commit()

        return Language(user.language)

    async def get_profile_summary(self, telegram_user: TelegramUser) -> ProfileSummarySchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            order_repository = OrderRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            purchases_count, total_spent = await order_repository.get_user_stats(user.id)
            await session.commit()

        return ProfileSummarySchema(
            language=Language(user.language),
            username=self._resolve_username(telegram_user, Language(user.language)),
            user_id=user.id,
            telegram_id=telegram_user.id,
            balance=self._to_decimal(user.balance),
            purchases_count=purchases_count,
            total_spent=self._to_decimal(total_spent),
        )

    async def set_language(
        self,
        telegram_user: TelegramUser,
        language: Language,
    ) -> ProfileSummarySchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            order_repository = OrderRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await user_repository.update_language(user, language)
            purchases_count, total_spent = await order_repository.get_user_stats(user.id)
            await session.commit()

        logger.info("Updated user language telegram_id=%s language=%s", telegram_user.id, language.value)

        return ProfileSummarySchema(
            language=language,
            username=self._resolve_username(telegram_user, language),
            user_id=user.id,
            telegram_id=telegram_user.id,
            balance=self._to_decimal(user.balance),
            purchases_count=purchases_count,
            total_spent=self._to_decimal(total_spent),
        )

    async def get_order_history_page(
        self,
        telegram_user: TelegramUser,
        *,
        page: int = 1,
        page_size: int = ORDER_HISTORY_PAGE_SIZE,
    ) -> OrderHistoryPageSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            order_repository = OrderRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            total_count = await order_repository.count_by_user(user.id)
            total_pages = max(1, ceil(total_count / page_size))
            safe_page = min(max(page, 1), total_pages)
            orders = await order_repository.get_page_by_user(
                user.id,
                page=safe_page,
                page_size=page_size,
            )
            await session.commit()

        history = [
            OrderHistoryEntrySchema(
                order_id=order.id,
                amount=self._to_decimal(order.sale_amount),
                currency=order.currency,
                created_at=order.created_at,
                delivery_data=order.delivery_data,
                fulfillment_payload=order.fulfillment_payload,
            )
            for order in orders
        ]
        return OrderHistoryPageSchema(
            language=Language(user.language),
            items=history,
            page=safe_page,
            total_pages=total_pages,
            total_count=total_count,
            has_previous=safe_page > 1,
            has_next=safe_page < total_pages,
        )

    @staticmethod
    def _resolve_username(telegram_user: TelegramUser, language: Language) -> str:
        if telegram_user.username:
            return f"@{telegram_user.username}"

        full_name = " ".join(part for part in (telegram_user.first_name, telegram_user.last_name) if part)
        return full_name or translate(language, "unknown_username")

    @staticmethod
    def _to_decimal(value: Decimal | int | float | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))


def render_profile_text(summary: ProfileSummarySchema) -> str:
    username = escape(summary.username)
    language = summary.language

    return "\n".join(
        (
            translate(language, "profile_title"),
            translate(language, "profile_username", username=username),
            translate(language, "profile_tg_id", telegram_id=summary.telegram_id),
            translate(language, "profile_id", bot_user_id=summary.user_id),
            "",
            translate(language, "profile_balance", balance=_format_money(summary.balance)),
            translate(language, "profile_orders_count", count=summary.purchases_count),
            translate(language, "profile_total_spent", amount=_format_money(summary.total_spent)),
        )
    )


def render_language_text(language: Language) -> str:
    return translate(
        language,
        "language_title",
        current_language=_language_label(language, language),
    )


def render_order_history_text(history_page: OrderHistoryPageSchema) -> str:
    language = history_page.language
    lines = [translate(language, "history_title"), ""]

    if history_page.total_count > 0:
        lines.append(
            translate(
                language,
                "history_page_meta",
                page=history_page.page,
                total_pages=history_page.total_pages,
            )
        )
        lines.append("")

    if not history_page.items:
        lines.append(translate(language, "history_empty"))
        return "\n".join(lines)

    lines.extend(
        "<blockquote>{entry}</blockquote>".format(
            entry=translate(
                language,
                "history_entry",
                order_id=order.order_id,
                amount=_format_money(order.amount),
                currency=escape(order.currency),
                created_at=_format_datetime(order.created_at),
                credentials=_format_order_credentials(order.delivery_data, order.fulfillment_payload),
            )
        )
        for order in history_page.items
    )
    return "\n".join(lines)


def _language_label(interface_language: Language, target_language: Language) -> str:
    key = "language_russian" if target_language == Language.RU else "language_english"
    return translate(interface_language, key)


def _format_money(amount: Decimal) -> str:
    normalized = amount.quantize(Decimal("0.01"))
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{normalized:.2f}"


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")


def _format_order_credentials(
    delivery_data: dict[str, str] | None,
    fulfillment_payload: dict[str, object] | None,
) -> str:
    credentials = dict(delivery_data or {})
    confirm_buy = fulfillment_payload.get("confirm_buy") if fulfillment_payload else None
    if isinstance(confirm_buy, dict):
        item = confirm_buy.get("item")
        login_data = item.get("loginData") if isinstance(item, dict) else None
        if isinstance(login_data, dict):
            for field in ("login", "password"):
                value = login_data.get(field)
                if isinstance(value, str) and value.strip() and not credentials.get(field):
                    credentials[field] = value.strip()

    values = [credentials[key] for key in ("login", "password") if credentials.get(key)]
    return escape(";".join(values) if values else "-")

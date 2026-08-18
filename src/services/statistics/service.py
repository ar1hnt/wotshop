from datetime import UTC, datetime, timedelta
from decimal import Decimal

from aiogram.types import User as TelegramUser
from pydantic import ValidationError

from src.config import settings
from src.db import async_session_factory
from src.db.repositories import OrderRepository, ReviewRepository, UserRepository
from src.i18n import Language, translate
from src.schemas.admin import (
    StatisticsCustomPeriodInputSchema,
    StatisticsPeriodPreset,
    StatisticsPeriodSchema,
    StatisticsSummarySchema,
)


class StatisticsPeriodValidationError(Exception):
    pass


class StatisticsService:
    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await session.commit()

        return Language(user.language)

    async def get_summary_for_preset(
        self,
        telegram_user: TelegramUser,
        preset: StatisticsPeriodPreset,
    ) -> StatisticsSummarySchema:
        period = self._build_period_from_preset(preset)
        return await self._get_summary(telegram_user, period)

    async def get_summary_for_custom_period(
        self,
        telegram_user: TelegramUser,
        raw_value: str,
    ) -> StatisticsSummarySchema:
        try:
            custom_period = StatisticsCustomPeriodInputSchema.from_raw(raw_value)
        except (ValidationError, ValueError) as error:
            raise StatisticsPeriodValidationError from error

        period = StatisticsPeriodSchema(
            preset=StatisticsPeriodPreset.CUSTOM,
            start_at=self._local_to_utc(custom_period.start_at),
            end_at=self._local_to_utc(custom_period.end_at),
        )
        return await self._get_summary(telegram_user, period)

    async def _get_summary(
        self,
        telegram_user: TelegramUser,
        period: StatisticsPeriodSchema,
    ) -> StatisticsSummarySchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            order_repository = OrderRepository(session)
            review_repository = ReviewRepository(session)

            admin = await user_repository.get_or_create_from_telegram(telegram_user)
            new_users_count = await user_repository.count_created_in_period(
                start_at=period.start_at,
                end_at=period.end_at,
            )
            orders_count, revenue, supplier_expense, payout_commission = await order_repository.get_financial_summary(
                start_at=period.start_at,
                end_at=period.end_at,
            )
            positive_reviews_count, negative_reviews_count = await review_repository.get_rating_totals_in_period(
                start_at=period.start_at,
                end_at=period.end_at,
            )
            await session.commit()

        total_expense = supplier_expense + payout_commission
        profit = revenue - total_expense
        average_order_value = Decimal("0.00") if orders_count == 0 else (revenue / Decimal(orders_count))

        return StatisticsSummarySchema(
            language=Language(admin.language),
            period=period,
            new_users_count=new_users_count,
            orders_count=orders_count,
            revenue=self._normalize_money(revenue),
            supplier_expense=self._normalize_money(supplier_expense),
            payout_commission=self._normalize_money(payout_commission),
            total_expense=self._normalize_money(total_expense),
            profit=self._normalize_money(profit),
            average_order_value=self._normalize_money(average_order_value),
            positive_reviews_count=positive_reviews_count,
            negative_reviews_count=negative_reviews_count,
        )

    @staticmethod
    def _build_period_from_preset(preset: StatisticsPeriodPreset) -> StatisticsPeriodSchema:
        now_local = datetime.now(settings.default_timezone).replace(microsecond=0)
        start_of_day = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        if preset == StatisticsPeriodPreset.ALL_TIME:
            return StatisticsPeriodSchema(preset=preset)

        if preset == StatisticsPeriodPreset.DAY:
            return StatisticsPeriodSchema(
                preset=preset,
                start_at=StatisticsService._local_to_utc(start_of_day),
                end_at=StatisticsService._local_to_utc(now_local),
            )

        if preset == StatisticsPeriodPreset.WEEK:
            start_of_week = start_of_day - timedelta(days=start_of_day.weekday())
            return StatisticsPeriodSchema(
                preset=preset,
                start_at=StatisticsService._local_to_utc(start_of_week),
                end_at=StatisticsService._local_to_utc(now_local),
            )

        if preset == StatisticsPeriodPreset.CURRENT_MONTH:
            start_of_month = start_of_day.replace(day=1)
            return StatisticsPeriodSchema(
                preset=preset,
                start_at=StatisticsService._local_to_utc(start_of_month),
                end_at=StatisticsService._local_to_utc(now_local),
            )

        current_month_start = start_of_day.replace(day=1)
        previous_month_end = current_month_start - timedelta(seconds=1)
        previous_month_start = previous_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return StatisticsPeriodSchema(
            preset=StatisticsPeriodPreset.PREVIOUS_MONTH,
            start_at=StatisticsService._local_to_utc(previous_month_start),
            end_at=StatisticsService._local_to_utc(previous_month_end),
        )

    @staticmethod
    def _local_to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=settings.default_timezone).astimezone(UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _normalize_money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


def render_admin_statistics_menu_text(language: Language) -> str:
    return translate(language, "admin_statistics_menu_title")


def render_admin_statistics_custom_period_prompt_text(language: Language) -> str:
    return translate(language, "admin_statistics_custom_period_prompt")


def render_admin_statistics_text(summary: StatisticsSummarySchema) -> str:
    lines = [
        translate(summary.language, "admin_statistics_title"),
        "",
        translate(
            summary.language,
            "admin_statistics_period_value",
            value=_period_label(summary.language, summary.period.preset),
        ),
    ]

    if summary.period.start_at is not None and summary.period.end_at is not None:
        lines.extend(
            (
                translate(
                    summary.language,
                    "admin_statistics_range_value",
                    start_at=_format_datetime(summary.period.start_at),
                    end_at=_format_datetime(summary.period.end_at),
                ),
            )
        )

    lines.extend(
        (
            "",
            translate(summary.language, "admin_statistics_new_users_value", count=summary.new_users_count),
            translate(summary.language, "admin_statistics_orders_count_value", count=summary.orders_count),
            translate(
                summary.language,
                "admin_statistics_average_check_value",
                amount=_format_money(summary.average_order_value),
            ),
            "",
            translate(summary.language, "admin_statistics_revenue_value", amount=_format_money(summary.revenue)),
            translate(
                summary.language,
                "admin_statistics_supplier_expense_value",
                amount=_format_money(summary.supplier_expense),
            ),
            translate(
                summary.language,
                "admin_statistics_payout_commission_value",
                amount=_format_money(summary.payout_commission),
            ),
            translate(summary.language, "admin_statistics_total_expense_value", amount=_format_money(summary.total_expense)),
            translate(summary.language, "admin_statistics_profit_value", amount=_format_money(summary.profit)),
            "",
            translate(
                summary.language,
                "admin_statistics_reviews_value",
                positive_count=summary.positive_reviews_count,
                negative_count=summary.negative_reviews_count,
            ),
        )
    )
    return "\n".join(lines)


def _period_label(language: Language, preset: StatisticsPeriodPreset) -> str:
    key_by_preset = {
        StatisticsPeriodPreset.ALL_TIME: "admin_statistics_button_all_time",
        StatisticsPeriodPreset.CURRENT_MONTH: "admin_statistics_button_current_month",
        StatisticsPeriodPreset.PREVIOUS_MONTH: "admin_statistics_button_previous_month",
        StatisticsPeriodPreset.WEEK: "admin_statistics_button_week",
        StatisticsPeriodPreset.DAY: "admin_statistics_button_day",
        StatisticsPeriodPreset.CUSTOM: "admin_statistics_button_custom",
    }
    return translate(language, key_by_preset[preset])


def _format_money(amount: Decimal) -> str:
    normalized = amount.quantize(Decimal("0.01"))
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{normalized:.2f}"


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")

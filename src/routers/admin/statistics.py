from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.filters.admin import IsAdminFilter
from src.i18n import translate
from src.keyboards.callbacks import (
    AdminStatisticsAction,
    AdminStatisticsCallback,
)
from src.keyboards.inline import (
    build_admin_main_markup,
    build_admin_statistics_back_markup,
    build_admin_statistics_menu_markup,
)
from src.routers.common.navigation import render_screen_message, render_screen_message_by_id
from src.schemas.admin import StatisticsPeriodPreset
from src.services.reviews import render_admin_menu_text
from src.services.statistics import (
    StatisticsPeriodValidationError,
    StatisticsService,
    render_admin_statistics_custom_period_prompt_text,
    render_admin_statistics_menu_text,
    render_admin_statistics_text,
)
from src.services.system import BotSettingsService
from src.states.admin_statistics import AdminStatisticsState

router = Router(name="admin-statistics")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())
statistics_service = StatisticsService()
bot_settings_service = BotSettingsService()


@router.callback_query(AdminStatisticsCallback.filter())
async def handle_admin_statistics(
    callback: CallbackQuery,
    callback_data: AdminStatisticsCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await statistics_service.get_user_language(callback.from_user)
    action = callback_data.action

    if action == AdminStatisticsAction.OPEN_MENU:
        await state.clear()
        await render_screen_message(
            callback.message,
            text=render_admin_statistics_menu_text(language),
            reply_markup=build_admin_statistics_menu_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminStatisticsAction.BACK_TO_MAIN:
        await state.clear()
        _, sales_enabled = await bot_settings_service.get_admin_context(callback.from_user)
        await render_screen_message(
            callback.message,
            text=render_admin_menu_text(language),
            reply_markup=build_admin_main_markup(language, sales_enabled),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminStatisticsAction.CUSTOM:
        await state.set_state(AdminStatisticsState.waiting_for_custom_period)
        await state.update_data(
            anchor_chat_id=callback.message.chat.id,
            anchor_message_id=callback.message.message_id,
        )
        await render_screen_message(
            callback.message,
            text=render_admin_statistics_custom_period_prompt_text(language),
            reply_markup=build_admin_statistics_back_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    await state.clear()
    summary = await statistics_service.get_summary_for_preset(
        callback.from_user,
        _resolve_preset(action),
    )
    await render_screen_message(
        callback.message,
        text=render_admin_statistics_text(summary),
        reply_markup=build_admin_statistics_back_markup(summary.language),
        edit=True,
    )
    await callback.answer()


@router.message(AdminStatisticsState.waiting_for_custom_period)
async def handle_custom_statistics_period(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    language = await statistics_service.get_user_language(message.from_user)

    try:
        summary = await statistics_service.get_summary_for_custom_period(
            message.from_user,
            message.text or "",
        )
    except StatisticsPeriodValidationError:
        await message.answer(
            translate(language, "admin_statistics_custom_period_invalid"),
            reply_markup=build_admin_statistics_back_markup(language),
        )
        return

    await state.clear()
    await render_screen_message_by_id(
        bot,
        chat_id=int(data["anchor_chat_id"]),
        message_id=int(data["anchor_message_id"]),
        text=render_admin_statistics_text(summary),
        reply_markup=build_admin_statistics_back_markup(summary.language),
    )


def _resolve_preset(action: AdminStatisticsAction) -> StatisticsPeriodPreset:
    mapping = {
        AdminStatisticsAction.ALL_TIME: StatisticsPeriodPreset.ALL_TIME,
        AdminStatisticsAction.CURRENT_MONTH: StatisticsPeriodPreset.CURRENT_MONTH,
        AdminStatisticsAction.PREVIOUS_MONTH: StatisticsPeriodPreset.PREVIOUS_MONTH,
        AdminStatisticsAction.WEEK: StatisticsPeriodPreset.WEEK,
        AdminStatisticsAction.DAY: StatisticsPeriodPreset.DAY,
    }
    return mapping[action]

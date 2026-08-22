import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.db.models.catalog_account import CatalogSortField, GameAccountType
from src.i18n import translate
from src.keyboards.callbacks import (
    AccountRefreshSource,
    CatalogAccountAction,
    CatalogAccountActionCallback,
    CatalogAccountDetailCallback,
    CatalogBooleanFilterCallback,
    CatalogClearFieldCallback,
    CatalogFilterAction,
    CatalogFilterActionCallback,
    CatalogFilterFieldCallback,
    CatalogFilterPageCallback,
    CatalogGameTypeCallback,
    CatalogResultsPageCallback,
    CatalogSortCallback,
)
from src.keyboards.inline import (
    build_catalog_account_detail_markup,
    build_catalog_boolean_markup,
    build_catalog_filter_input_back_markup,
    build_catalog_filter_markup,
    build_catalog_search_progress_markup,
    build_catalog_reset_confirmation_markup,
    build_catalog_results_markup,
)
from src.routers.common.navigation import (
    render_screen_message,
    render_screen_message_by_id,
)
from src.routers.user.account_refresh import start_account_purchase, start_account_refresh
from src.schemas.catalog import CatalogBooleanChoice, CatalogFilterField
from src.schemas.common.menu import (
    CATALOG_ACCOUNT_SCREEN_MEDIA,
    CATALOG_FILTER_SCREEN_MEDIA,
    CATALOG_RESULTS_SCREEN_MEDIA,
)
from src.services.catalog import (
    CatalogAccountNotFoundError,
    CatalogFilterValidationError,
    CatalogService,
    get_catalog_filter_value_label,
    render_catalog_boolean_prompt,
    render_catalog_detail_text,
    render_catalog_favorite_alert,
    render_catalog_filter_input_prompt,
    render_catalog_filter_text,
    render_catalog_results_text,
)
from src.services.system import BotSettingsService, render_sales_disabled_alert
from src.states.catalog import CatalogFilterState

logger = logging.getLogger(__name__)
router = Router(name="user-catalog")
catalog_service = CatalogService()
bot_settings_service = BotSettingsService()


@router.callback_query(CatalogGameTypeCallback.filter())
async def handle_catalog_game_type(
    callback: CallbackQuery,
    callback_data: CatalogGameTypeCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    game_type = GameAccountType(callback_data.game_type)
    if not await bot_settings_service.is_sales_enabled(game_type):
        language = await catalog_service.get_user_language(callback.from_user)
        await callback.answer(render_sales_disabled_alert(language, game_type), show_alert=True)
        return

    await state.clear()
    results = await catalog_service.get_search_results(callback.from_user, game_type=game_type, page=1)
    await render_screen_message(
        callback.message,
        text=render_catalog_results_text(results),
        reply_markup=build_catalog_results_markup(results),
        media=CATALOG_RESULTS_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer()


@router.callback_query(CatalogFilterPageCallback.filter())
async def handle_catalog_filter_page(
    callback: CallbackQuery,
    callback_data: CatalogFilterPageCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    view = await catalog_service.get_filter_view(
        callback.from_user,
        game_type=GameAccountType(callback_data.game_type),
        page=callback_data.page,
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_filter_text(view),
        reply_markup=build_catalog_filter_markup(view),
        media=CATALOG_FILTER_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer()


@router.callback_query(CatalogFilterFieldCallback.filter())
async def handle_catalog_filter_field(
    callback: CallbackQuery,
    callback_data: CatalogFilterFieldCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    field = CatalogFilterField(callback_data.field)
    game_type = GameAccountType(callback_data.game_type)
    await state.clear()
    view = await catalog_service.get_filter_view(callback.from_user, game_type=game_type, page=callback_data.page)
    current_value = get_catalog_filter_value_label(view.language, view.catalog_filter, field)

    if field in {
        CatalogFilterField.HAS_TIER_11,
        CatalogFilterField.IS_PHONE_BOUND,
        CatalogFilterField.IS_IN_CLAN,
    }:
        language = await catalog_service.get_user_language(callback.from_user)
        await render_screen_message(
            callback.message,
            text=render_catalog_boolean_prompt(language, field, current_value=current_value),
            reply_markup=build_catalog_boolean_markup(language, game_type, callback_data.page, field),
            media=CATALOG_FILTER_SCREEN_MEDIA,
            edit=True,
        )
        await callback.answer()
        return

    language = await catalog_service.get_user_language(callback.from_user)
    await state.set_state(CatalogFilterState.waiting_for_value)
    await state.update_data(
        game_type=game_type.value,
        page=callback_data.page,
        field=field.value,
        anchor_chat_id=callback.message.chat.id,
        anchor_message_id=callback.message.message_id,
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_filter_input_prompt(language, field, current_value=current_value),
        reply_markup=build_catalog_filter_input_back_markup(language, game_type, callback_data.page, field),
        media=CATALOG_FILTER_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer()


@router.callback_query(CatalogBooleanFilterCallback.filter())
async def handle_catalog_boolean_filter(
    callback: CallbackQuery,
    callback_data: CatalogBooleanFilterCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    view = await catalog_service.update_boolean_filter(
        callback.from_user,
        game_type=GameAccountType(callback_data.game_type),
        field=CatalogFilterField(callback_data.field),
        choice=CatalogBooleanChoice(callback_data.choice),
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_filter_text(view),
        reply_markup=build_catalog_filter_markup(view),
        media=CATALOG_FILTER_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer(translate(view.language, "catalog_filter_updated"))


@router.callback_query(CatalogFilterActionCallback.filter())
async def handle_catalog_filter_action(
    callback: CallbackQuery,
    callback_data: CatalogFilterActionCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    game_type = GameAccountType(callback_data.game_type)

    if callback_data.action == CatalogFilterAction.OPEN_FILTER:
        view = await catalog_service.get_filter_view(callback.from_user, game_type=game_type, page=1)
        await render_screen_message(
            callback.message,
            text=render_catalog_filter_text(view),
            reply_markup=build_catalog_filter_markup(view),
            media=CATALOG_FILTER_SCREEN_MEDIA,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == CatalogFilterAction.ASK_RESET:
        language = await catalog_service.get_user_language(callback.from_user)
        await render_screen_message(
            callback.message,
            text=translate(language, "catalog_reset_confirm_text"),
            reply_markup=build_catalog_reset_confirmation_markup(language, game_type, callback_data.page),
            media=CATALOG_FILTER_SCREEN_MEDIA,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == CatalogFilterAction.CONFIRM_RESET:
        view = await catalog_service.reset_filter(callback.from_user, game_type=game_type)
        await render_screen_message(
            callback.message,
            text=render_catalog_filter_text(view),
            reply_markup=build_catalog_filter_markup(view),
            media=CATALOG_FILTER_SCREEN_MEDIA,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == CatalogFilterAction.CANCEL_RESET:
        view = await catalog_service.get_filter_view(callback.from_user, game_type=game_type, page=callback_data.page)
        await render_screen_message(
            callback.message,
            text=render_catalog_filter_text(view),
            reply_markup=build_catalog_filter_markup(view),
            media=CATALOG_FILTER_SCREEN_MEDIA,
            edit=True,
        )
        await callback.answer()
        return

    results = await catalog_service.get_search_results(callback.from_user, game_type=game_type, page=1)
    await render_screen_message(
        callback.message,
        text=render_catalog_results_text(results),
        reply_markup=build_catalog_results_markup(results),
        media=CATALOG_RESULTS_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer()


@router.callback_query(CatalogClearFieldCallback.filter())
async def handle_catalog_clear_field(
    callback: CallbackQuery,
    callback_data: CatalogClearFieldCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    view = await catalog_service.clear_filter_field(
        callback.from_user,
        game_type=GameAccountType(callback_data.game_type),
        field=CatalogFilterField(callback_data.field),
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_filter_text(view),
        reply_markup=build_catalog_filter_markup(view),
        media=CATALOG_FILTER_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer(translate(view.language, "catalog_filter_updated"))


@router.callback_query(CatalogResultsPageCallback.filter())
async def handle_catalog_results_page(
    callback: CallbackQuery,
    callback_data: CatalogResultsPageCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    results = await catalog_service.get_search_results(
        callback.from_user,
        game_type=GameAccountType(callback_data.game_type),
        page=callback_data.page,
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_results_text(results),
        reply_markup=build_catalog_results_markup(results),
        media=CATALOG_RESULTS_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer()


@router.callback_query(CatalogSortCallback.filter())
async def handle_catalog_sort(
    callback: CallbackQuery,
    callback_data: CatalogSortCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    results = await catalog_service.toggle_sort(
        callback.from_user,
        game_type=GameAccountType(callback_data.game_type),
        field=CatalogSortField(callback_data.field),
    )
    await render_screen_message(
        callback.message,
        text=render_catalog_results_text(results),
        reply_markup=build_catalog_results_markup(results),
        media=CATALOG_RESULTS_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer()


@router.callback_query(CatalogAccountDetailCallback.filter())
async def handle_catalog_account_detail(
    callback: CallbackQuery,
    callback_data: CatalogAccountDetailCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    try:
        detail = await catalog_service.get_account_detail(
            callback.from_user,
            account_id=callback_data.account_id,
            detail_page=callback_data.detail_page,
        )
    except CatalogAccountNotFoundError:
        language = await catalog_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_catalog_detail_text(detail),
        reply_markup=build_catalog_account_detail_markup(detail, page=callback_data.page),
        media=CATALOG_ACCOUNT_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer()


@router.callback_query(CatalogAccountActionCallback.filter())
async def handle_catalog_account_action(
    callback: CallbackQuery,
    callback_data: CatalogAccountActionCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    game_type = GameAccountType(callback_data.game_type)

    if callback_data.action == CatalogAccountAction.BUY:
        language = await catalog_service.get_user_language(callback.from_user)
        if not await bot_settings_service.is_sales_enabled(game_type):
            await callback.answer(render_sales_disabled_alert(language, game_type), show_alert=True)
            return
        await start_account_purchase(
            callback,
            source=AccountRefreshSource.CATALOG,
            account_id=callback_data.account_id,
            page=callback_data.page,
            detail_page=callback_data.detail_page,
        )
        return

    if callback_data.action == CatalogAccountAction.REFRESH:
        await start_account_refresh(
            callback,
            source=AccountRefreshSource.CATALOG,
            account_id=callback_data.account_id,
            page=callback_data.page,
            detail_page=callback_data.detail_page,
        )
        return

    if callback_data.action in {
        CatalogAccountAction.PREVIOUS_DETAIL_PAGE,
        CatalogAccountAction.NEXT_DETAIL_PAGE,
    }:
        target_detail_page = callback_data.detail_page
        if callback_data.action == CatalogAccountAction.PREVIOUS_DETAIL_PAGE:
            target_detail_page -= 1
        elif callback_data.action == CatalogAccountAction.NEXT_DETAIL_PAGE:
            target_detail_page += 1

        try:
            detail = await catalog_service.get_account_detail(
                callback.from_user,
                account_id=callback_data.account_id,
                detail_page=target_detail_page,
            )
        except CatalogAccountNotFoundError:
            language = await catalog_service.get_user_language(callback.from_user)
            await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
            return

        await render_screen_message(
            callback.message,
            text=render_catalog_detail_text(detail),
            reply_markup=build_catalog_account_detail_markup(detail, page=callback_data.page),
            media=CATALOG_ACCOUNT_SCREEN_MEDIA,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == CatalogAccountAction.BACK_TO_RESULTS:
        results = await catalog_service.get_search_results(callback.from_user, game_type=game_type, page=callback_data.page)
        await render_screen_message(
            callback.message,
            text=render_catalog_results_text(results),
            reply_markup=build_catalog_results_markup(results),
            media=CATALOG_RESULTS_SCREEN_MEDIA,
            edit=True,
        )
        await callback.answer()
        return

    try:
        detail, is_added = await catalog_service.toggle_favorite(
            callback.from_user,
            account_id=callback_data.account_id,
        )
    except CatalogAccountNotFoundError:
        language = await catalog_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "catalog_account_not_found"), show_alert=True)
        return

    current_detail = detail.model_copy(update={"detail_page": callback_data.detail_page})
    await render_screen_message(
        callback.message,
        text=render_catalog_detail_text(current_detail),
        reply_markup=build_catalog_account_detail_markup(current_detail, page=callback_data.page),
        media=CATALOG_ACCOUNT_SCREEN_MEDIA,
        edit=True,
    )
    await callback.answer(render_catalog_favorite_alert(detail.language, added=is_added))


@router.message(CatalogFilterState.waiting_for_value)
async def handle_catalog_filter_value(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    game_type = GameAccountType(data["game_type"])
    page = int(data["page"])
    field = CatalogFilterField(data["field"])

    try:
        view = await catalog_service.update_filter_from_text(
            message.from_user,
            game_type=game_type,
            field=field,
            raw_value=message.text or "",
        )
    except CatalogFilterValidationError:
        language = await catalog_service.get_user_language(message.from_user)
        await message.answer(
            translate(language, "catalog_filter_invalid_value"),
            reply_markup=build_catalog_filter_input_back_markup(
                language,
                game_type,
                page,
                field,
                include_clear_field=False,
            ),
        )
        return

    await _try_delete_message(message)
    await state.clear()
    await render_screen_message_by_id(
        message.bot,
        chat_id=int(data["anchor_chat_id"]),
        message_id=int(data["anchor_message_id"]),
        text=render_catalog_filter_text(view),
        reply_markup=build_catalog_filter_markup(view),
        media=CATALOG_FILTER_SCREEN_MEDIA,
    )


async def _try_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        logger.debug("Failed to delete catalog input message id=%s", message.message_id)

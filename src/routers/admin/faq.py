from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.filters.admin import IsAdminFilter
from src.i18n import translate
from src.keyboards.callbacks import (
    AdminFaqAction,
    AdminFaqActionCallback,
    AdminFaqAddCallback,
    AdminFaqDeleteAction,
    AdminFaqDeleteCallback,
    AdminFaqDetailCallback,
    AdminFaqEditFieldCallback,
    AdminFaqPageCallback,
)
from src.keyboards.inline import (
    build_admin_back_markup,
    build_admin_faq_delete_confirmation_markup,
    build_admin_faq_detail_markup,
    build_admin_faq_list_markup,
    build_admin_faq_prompt_markup,
    build_admin_main_markup,
)
from src.routers.common.navigation import render_screen_message, render_screen_message_by_id
from src.schemas.common.menu import Screen, render_menu_view
from src.services.faq import (
    FAQ_FIELD_SEQUENCE,
    FaqNotFoundError,
    FaqService,
    FaqValidationError,
    render_admin_faq_delete_confirmation_text,
    render_admin_faq_detail_text,
    render_admin_faq_list_text,
    render_admin_faq_prompt_text,
)
from src.services.reviews import render_admin_menu_text
from src.services.system import BotSettingsService
from src.states.admin_faq import AdminFaqState

router = Router(name="admin-faq")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())
faq_service = FaqService()
bot_settings_service = BotSettingsService()


@router.callback_query(AdminFaqActionCallback.filter())
async def handle_admin_faq_action(
    callback: CallbackQuery,
    callback_data: AdminFaqActionCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await faq_service.get_user_language(callback.from_user)

    if callback_data.action == AdminFaqAction.OPEN_MENU:
        await state.clear()
        await _render_faq_list(callback.message, callback.from_user, edit=True, page=1)
        await callback.answer()
        return

    if callback_data.action == AdminFaqAction.BACK_TO_MAIN:
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

    await callback.answer()


@router.callback_query(AdminFaqAddCallback.filter())
async def handle_admin_faq_add(
    callback: CallbackQuery,
    callback_data: AdminFaqAddCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await faq_service.get_user_language(callback.from_user)
    await state.clear()
    await state.set_state(AdminFaqState.waiting_for_text)
    await state.update_data(
        mode="create",
        page=callback_data.page,
        step_index=0,
        anchor_chat_id=callback.message.chat.id,
        anchor_message_id=callback.message.message_id,
    )
    await render_screen_message(
        callback.message,
        text=render_admin_faq_prompt_text(
            language,
            mode="create",
            field_name=FAQ_FIELD_SEQUENCE[0],
        ),
        reply_markup=build_admin_faq_prompt_markup(language, page=callback_data.page),
        media=render_menu_view(Screen.FAQ, language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminFaqPageCallback.filter())
async def handle_admin_faq_page(
    callback: CallbackQuery,
    callback_data: AdminFaqPageCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    await _render_faq_list(callback.message, callback.from_user, edit=True, page=callback_data.page)
    await callback.answer()


@router.callback_query(AdminFaqDetailCallback.filter())
async def handle_admin_faq_detail(
    callback: CallbackQuery,
    callback_data: AdminFaqDetailCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    try:
        detail = await faq_service.get_detail(callback.from_user, callback_data.faq_id, page=callback_data.page)
    except FaqNotFoundError:
        language = await faq_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "admin_faq_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_admin_faq_detail_text(detail),
        reply_markup=build_admin_faq_detail_markup(detail),
        media=render_menu_view(Screen.FAQ, detail.language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminFaqEditFieldCallback.filter())
async def handle_admin_faq_edit_field(
    callback: CallbackQuery,
    callback_data: AdminFaqEditFieldCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        detail = await faq_service.get_detail(callback.from_user, callback_data.faq_id, page=callback_data.page)
    except FaqNotFoundError:
        language = await faq_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "admin_faq_not_found"), show_alert=True)
        return

    await state.clear()
    await state.update_data(
        faq_id=detail.id,
        page=callback_data.page,
        mode="edit",
        field_name=callback_data.field.value,
        anchor_chat_id=callback.message.chat.id,
        anchor_message_id=callback.message.message_id,
    )
    await state.set_state(AdminFaqState.waiting_for_text)
    text = render_admin_faq_prompt_text(
        detail.language,
        mode="edit",
        field_name=callback_data.field.value,
        current_value=str(getattr(detail, callback_data.field.value)),
    )

    await render_screen_message(
        callback.message,
        text=text,
        reply_markup=build_admin_faq_prompt_markup(detail.language, faq_id=detail.id, page=callback_data.page),
        media=render_menu_view(Screen.FAQ, detail.language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminFaqDeleteCallback.filter())
async def handle_admin_faq_delete(
    callback: CallbackQuery,
    callback_data: AdminFaqDeleteCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await faq_service.get_user_language(callback.from_user)

    try:
        detail = await faq_service.get_detail(callback.from_user, callback_data.faq_id, page=callback_data.page)
    except FaqNotFoundError:
        await callback.answer(translate(language, "admin_faq_not_found"), show_alert=True)
        return

    if callback_data.action == AdminFaqDeleteAction.ASK:
        await state.clear()
        await render_screen_message(
            callback.message,
            text=render_admin_faq_delete_confirmation_text(language, detail),
            reply_markup=build_admin_faq_delete_confirmation_markup(language, detail.id, page=callback_data.page),
            media=render_menu_view(Screen.FAQ, language).media,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminFaqDeleteAction.CANCEL:
        await state.clear()
        await render_screen_message(
            callback.message,
            text=render_admin_faq_detail_text(detail),
            reply_markup=build_admin_faq_detail_markup(detail),
            media=render_menu_view(Screen.FAQ, detail.language).media,
            edit=True,
        )
        await callback.answer()
        return

    await state.clear()
    deleted_language = await faq_service.delete(callback.from_user, faq_id=callback_data.faq_id)
    await render_screen_message(
        callback.message,
        text=translate(deleted_language, "admin_faq_deleted_alert"),
        reply_markup=build_admin_back_markup(
            deleted_language,
            AdminFaqActionCallback(action=AdminFaqAction.OPEN_MENU).pack(),
        ),
        edit=True,
    )
    await callback.answer()


@router.message(AdminFaqState.waiting_for_text)
async def handle_faq_text_input(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    language = await faq_service.get_user_language(message.from_user)
    new_value = (message.text or "").strip()
    mode = str(data.get("mode", "create"))

    if not new_value:
        await message.answer(
            translate(language, "admin_faq_text_empty"),
            reply_markup=build_admin_faq_prompt_markup(
                language,
                faq_id=int(data["faq_id"]) if data.get("faq_id") is not None else None,
                page=int(data.get("page", 1)),
            ),
        )
        return

    try:
        if mode == "edit":
            detail = await faq_service.update_localized_field(
                message.from_user,
                faq_id=int(data["faq_id"]),
                page=int(data.get("page", 1)),
                field_name=str(data["field_name"]),
                value=new_value,
            )
        else:
            detail = await _handle_faq_create_step(
                message=message,
                state=state,
                data=data,
                language=language,
                new_value=new_value,
            )
            if detail is None:
                return
    except FaqValidationError:
        await message.answer(
            translate(language, "admin_faq_text_empty"),
            reply_markup=build_admin_faq_prompt_markup(
                language,
                faq_id=int(data["faq_id"]) if data.get("faq_id") is not None else None,
                page=int(data.get("page", 1)),
            ),
        )
        return
    except FaqNotFoundError:
        await state.clear()
        await message.answer(
            translate(language, "admin_faq_not_found"),
            reply_markup=build_admin_faq_prompt_markup(
                language,
                faq_id=int(data["faq_id"]) if data.get("faq_id") is not None else None,
                page=int(data.get("page", 1)),
            ),
        )
        return

    await _try_delete_message(message)
    await state.clear()
    await render_screen_message_by_id(
        message.bot,
        chat_id=int(data["anchor_chat_id"]),
        message_id=int(data["anchor_message_id"]),
        text=render_admin_faq_detail_text(detail),
        reply_markup=build_admin_faq_detail_markup(detail),
        media=render_menu_view(Screen.FAQ, detail.language).media,
    )


async def _render_faq_list(message: Message, admin_user, *, edit: bool, page: int) -> None:
    faq_view = await faq_service.get_admin_list(admin_user, page=page)
    await render_screen_message(
        message,
        text=render_admin_faq_list_text(faq_view),
        reply_markup=build_admin_faq_list_markup(faq_view),
        media=render_menu_view(Screen.FAQ, faq_view.language).media,
        edit=edit,
    )


async def _try_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        return


async def _handle_faq_create_step(
    *,
    message: Message,
    state: FSMContext,
    data: dict,
    language,
    new_value: str,
):
    step_index = int(data.get("step_index", 0))
    field_name = FAQ_FIELD_SEQUENCE[step_index]
    payload = {key: str(data.get(key, "")).strip() for key in FAQ_FIELD_SEQUENCE}
    payload[field_name] = new_value

    if step_index < len(FAQ_FIELD_SEQUENCE) - 1:
        next_step_index = step_index + 1
        await state.update_data(step_index=next_step_index, **payload)
        await render_screen_message_by_id(
            message.bot,
            chat_id=int(data["anchor_chat_id"]),
            message_id=int(data["anchor_message_id"]),
            text=render_admin_faq_prompt_text(
                language,
                mode="create",
                field_name=FAQ_FIELD_SEQUENCE[next_step_index],
            ),
            reply_markup=build_admin_faq_prompt_markup(language, page=int(data.get("page", 1))),
            media=render_menu_view(Screen.FAQ, language).media,
        )
        return None

    return await faq_service.create(
        message.from_user,
        page=int(data.get("page", 1)),
        **payload,
    )


async def _build_faq_prompt_with_error(
    telegram_user,
    language,
    data: dict,
    *,
    fallback_value: str | None = None,
) -> str | None:
    mode = str(data.get("mode", "create"))
    if mode == "edit":
        faq_id = int(data["faq_id"])
        field_name = str(data["field_name"])
        try:
            detail = await faq_service.get_detail(telegram_user, faq_id)
        except FaqNotFoundError:
            return None
        current_value = fallback_value or str(getattr(detail, field_name))
        base_text = render_admin_faq_prompt_text(
            language,
            mode="edit",
            field_name=field_name,
            current_value=current_value,
        )
    else:
        step_index = int(data.get("step_index", 0))
        field_name = FAQ_FIELD_SEQUENCE[step_index]
        current_value = fallback_value or str(data.get(field_name, "")).strip() or None
        base_text = render_admin_faq_prompt_text(
            language,
            mode="create",
            field_name=field_name,
            current_value=current_value,
        )

    return "\n\n".join((base_text, translate(language, "admin_faq_text_empty")))

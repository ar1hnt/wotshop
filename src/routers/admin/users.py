from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.filters.admin import IsAdminFilter
from src.i18n import Language, translate
from src.keyboards.callbacks import (
    AdminBroadcastAction,
    AdminBroadcastCallback,
    AdminUserEditField,
    AdminUserEditFieldCallback,
    AdminUserLookupTypeCallback,
    AdminUserViewCallback,
    AdminUsersAction,
    AdminUsersCallback,
)
from src.keyboards.inline import (
    build_admin_back_markup,
    build_admin_broadcast_confirmation_markup,
    build_admin_broadcast_prompt_markup,
    build_admin_main_markup,
    build_admin_user_balance_prompt_markup,
    build_admin_user_detail_markup,
    build_admin_user_lookup_prompt_markup,
    build_admin_user_lookup_type_markup,
    build_admin_users_menu_markup,
)
from src.routers.common.navigation import render_screen_message, render_screen_message_by_id
from src.schemas.admin import BroadcastDraftSchema
from src.services.reviews import render_admin_menu_text
from src.services.system import BotSettingsService
from src.services.users import (
    BalanceValidationError,
    BroadcastValidationError,
    UserLookupError,
    UserService,
    render_admin_users_menu_text,
    render_balance_prompt_text,
    render_balance_updated_text,
    render_broadcast_confirmation_text,
    render_broadcast_prompt_text,
    render_broadcast_result_text,
    render_direct_broadcast_confirmation_text,
    render_direct_broadcast_lookup_text,
    render_direct_broadcast_prompt_text,
    render_direct_broadcast_result_text,
    render_user_detail_text,
    render_user_lookup_prompt_text,
    render_user_lookup_type_text,
)
from src.states.admin_users import AdminBroadcastState, AdminDirectBroadcastState, AdminUserLookupState

router = Router(name="admin-users")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())
user_service = UserService()
bot_settings_service = BotSettingsService()


@router.callback_query(AdminUsersCallback.filter())
async def handle_admin_users_menu(
    callback: CallbackQuery,
    callback_data: AdminUsersCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await user_service.get_user_language(callback.from_user)
    action = callback_data.action

    if action == AdminUsersAction.OPEN_MENU:
        await state.clear()
        total_users = await user_service.get_total_users_count()
        await render_screen_message(
            callback.message,
            text=render_admin_users_menu_text(language, total_users),
            reply_markup=build_admin_users_menu_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminUsersAction.BACK_TO_MAIN:
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

    if action == AdminUsersAction.BROADCAST:
        sent_message = await callback.message.edit_text(
            text=render_broadcast_prompt_text(language),
            reply_markup=build_admin_broadcast_prompt_markup(language),
        )
        await state.set_state(AdminBroadcastState.waiting_for_content)
        await state.update_data(
            anchor_chat_id=sent_message.chat.id,
            anchor_message_id=sent_message.message_id,
        )
        await callback.answer()
        return

    if action == AdminUsersAction.DIRECT_BROADCAST:
        await state.set_state(AdminUserLookupState.waiting_for_identifier_value)
        await state.update_data(direct_broadcast=True)
        await render_screen_message(
            callback.message,
            text=render_direct_broadcast_lookup_text(language),
            reply_markup=build_admin_user_lookup_type_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminUsersAction.EXPORT:
        await state.clear()
        export_language, export_file = await user_service.export_users_xlsx(callback.from_user)
        await callback.message.answer_document(document=export_file)
        await render_screen_message(
            callback.message,
            text=translate(export_language, "admin_export_users_done"),
            reply_markup=build_admin_back_markup(
                export_language,
                AdminUsersCallback(action=AdminUsersAction.OPEN_MENU).pack(),
            ),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminUsersAction.EDIT:
        await state.clear()
        await render_screen_message(
            callback.message,
            text=render_user_lookup_type_text(language),
            reply_markup=build_admin_user_lookup_type_markup(language),
            edit=True,
        )
        await callback.answer()
        return


@router.message(AdminBroadcastState.waiting_for_content)
async def handle_broadcast_content(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    try:
        draft = await user_service.build_broadcast_draft(message.from_user, message)
    except BroadcastValidationError:
        language = await user_service.get_user_language(message.from_user)
        await message.answer(
            translate(language, "admin_broadcast_invalid"),
            reply_markup=build_admin_broadcast_prompt_markup(language),
        )
        return

    await state.update_data(
        draft_html_text=draft.html_text,
        draft_photo_file_id=draft.photo_file_id,
        draft_language=draft.language.value,
        anchor_chat_id=data["anchor_chat_id"],
        anchor_message_id=data["anchor_message_id"],
    )
    await state.set_state(AdminBroadcastState.waiting_for_confirmation)
    await message.answer(
        text=render_broadcast_confirmation_text(draft.language, draft),
        reply_markup=build_admin_broadcast_confirmation_markup(draft.language),
    )


@router.message(AdminDirectBroadcastState.waiting_for_content)
async def handle_direct_broadcast_content(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    try:
        draft = await user_service.build_broadcast_draft(message.from_user, message)
    except BroadcastValidationError:
        language = await user_service.get_user_language(message.from_user)
        await message.answer(translate(language, "admin_broadcast_invalid"))
        return
    try:
        recipient = await user_service.find_user_by_identifier(
            message.from_user,
            identifier_type="bot_id",
            identifier_value=str(data["recipient_bot_user_id"]),
        )
    except UserLookupError:
        language = await user_service.get_user_language(message.from_user)
        await state.clear()
        await message.answer(translate(language, "admin_user_not_found"))
        return

    await state.update_data(
        draft_html_text=draft.html_text,
        draft_photo_file_id=draft.photo_file_id,
        draft_language=draft.language.value,
    )
    await state.set_state(AdminDirectBroadcastState.waiting_for_confirmation)
    await message.answer(
        text=render_direct_broadcast_confirmation_text(draft.language, draft, recipient),
        reply_markup=build_admin_broadcast_confirmation_markup(draft.language),
    )


@router.callback_query(AdminBroadcastCallback.filter())
async def handle_broadcast_confirmation(
    callback: CallbackQuery,
    callback_data: AdminBroadcastCallback,
    state: FSMContext,
    bot: Bot,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    data = await state.get_data()
    language = await user_service.get_user_language(callback.from_user)
    action = callback_data.action
    is_direct_broadcast = await state.get_state() == AdminDirectBroadcastState.waiting_for_confirmation.state

    if action == AdminBroadcastAction.BACK:
        if is_direct_broadcast:
            try:
                recipient = await user_service.find_user_by_identifier(
                    callback.from_user,
                    identifier_type="bot_id",
                    identifier_value=str(data["recipient_bot_user_id"]),
                )
            except UserLookupError:
                await state.clear()
                await callback.answer(translate(language, "admin_user_not_found"), show_alert=True)
                return
            await state.set_state(AdminDirectBroadcastState.waiting_for_content)
            prompt_text = render_direct_broadcast_prompt_text(language, recipient)
        else:
            await state.set_state(AdminBroadcastState.waiting_for_content)
            prompt_text = render_broadcast_prompt_text(language)
        await render_screen_message(
            callback.message,
            text=prompt_text,
            reply_markup=build_admin_broadcast_prompt_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminBroadcastAction.CANCEL:
        await state.clear()
        await render_screen_message(
            callback.message,
            text=render_admin_users_menu_text(language, await user_service.get_total_users_count()),
            reply_markup=build_admin_users_menu_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    draft = BroadcastDraftSchema(
        language=Language(data.get("draft_language", language.value)),
        html_text=data.get("draft_html_text", ""),
        photo_file_id=data.get("draft_photo_file_id"),
    )
    if not draft.html_text:
        await state.set_state(AdminBroadcastState.waiting_for_content)
        await render_screen_message(
            callback.message,
            text=render_broadcast_prompt_text(language),
            reply_markup=build_admin_broadcast_prompt_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if is_direct_broadcast:
        try:
            recipient = await user_service.find_user_by_identifier(
                callback.from_user,
                identifier_type="bot_id",
                identifier_value=str(data["recipient_bot_user_id"]),
            )
        except UserLookupError:
            await state.clear()
            await callback.answer(translate(language, "admin_user_not_found"), show_alert=True)
            return
        result = await user_service.send_direct_broadcast(bot, telegram_id=recipient.telegram_id, draft=draft)
        result_text = render_direct_broadcast_result_text(result, recipient)
    else:
        result = await user_service.send_broadcast(bot, draft)
        result_text = render_broadcast_result_text(result)
    await state.clear()
    await render_screen_message(
        callback.message,
        text=result_text,
        reply_markup=build_admin_broadcast_prompt_markup(result.language),
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminUserLookupTypeCallback.filter())
async def handle_user_lookup_type(
    callback: CallbackQuery,
    callback_data: AdminUserLookupTypeCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await user_service.get_user_language(callback.from_user)
    data = await state.get_data()
    await state.set_state(AdminUserLookupState.waiting_for_identifier_value)
    await state.update_data(
        direct_broadcast=bool(data.get("direct_broadcast")),
        identifier_type=callback_data.identifier_type,
        anchor_chat_id=callback.message.chat.id,
        anchor_message_id=callback.message.message_id,
    )
    prompt_text = (
        translate(language, "admin_user_lookup_prompt", identifier=translate(language, "admin_user_identifier_bot_id") if callback_data.identifier_type == "bot_id" else translate(language, "admin_user_identifier_tg_id"))
    )
    await render_screen_message(
        callback.message,
        text=prompt_text,
        reply_markup=build_admin_user_lookup_prompt_markup(language),
        edit=True,
    )
    await callback.answer()


@router.message(AdminUserLookupState.waiting_for_identifier_value)
async def handle_user_lookup_value(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return

    language = await user_service.get_user_language(message.from_user)

    data = await state.get_data()
    try:
        user = await user_service.find_user_by_identifier(
            message.from_user,
            identifier_type=data["identifier_type"],
            identifier_value=message.text or "",
        )
    except UserLookupError:
        await message.answer(
            translate(language, "admin_user_not_found"),
            reply_markup=build_admin_user_lookup_prompt_markup(language),
        )
        return

    if data.get("direct_broadcast"):
        await state.set_state(AdminDirectBroadcastState.waiting_for_content)
        await state.update_data(recipient_bot_user_id=user.bot_user_id)
        await message.answer(text=render_direct_broadcast_prompt_text(language, user))
        return

    await state.clear()
    await message.answer(
        text=render_user_detail_text(user),
        reply_markup=build_admin_user_detail_markup(user),
    )


@router.callback_query(AdminUserViewCallback.filter())
async def handle_user_view(
    callback: CallbackQuery,
    callback_data: AdminUserViewCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    language = await user_service.get_user_language(callback.from_user)
    try:
        user = await user_service.find_user_by_identifier(
            callback.from_user,
            identifier_type="bot_id",
            identifier_value=str(callback_data.user_id),
        )
    except UserLookupError:
        await callback.answer(translate(language, "admin_user_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_user_detail_text(user),
        reply_markup=build_admin_user_detail_markup(user),
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminUserEditFieldCallback.filter())
async def handle_user_edit_field(
    callback: CallbackQuery,
    callback_data: AdminUserEditFieldCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await user_service.get_user_language(callback.from_user)
    try:
        user = await user_service.find_user_by_identifier(
            callback.from_user,
            identifier_type="bot_id",
            identifier_value=str(callback_data.user_id),
        )
    except UserLookupError:
        await callback.answer(translate(language, "admin_user_not_found"), show_alert=True)
        return

    if callback_data.field == AdminUserEditField.BALANCE:
        await state.set_state(AdminUserLookupState.waiting_for_balance)
        await state.update_data(
            target_user_id=user.bot_user_id,
            anchor_chat_id=callback.message.chat.id,
            anchor_message_id=callback.message.message_id,
        )
        await render_screen_message(
            callback.message,
            text=render_balance_prompt_text(language, user),
            reply_markup=build_admin_user_balance_prompt_markup(language, user.bot_user_id),
            edit=True,
        )
        await callback.answer()


@router.message(AdminUserLookupState.waiting_for_balance)
async def handle_user_balance_update(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    language = await user_service.get_user_language(message.from_user)

    try:
        user = await user_service.update_user_balance(
            message.from_user,
            target_user_id=int(data["target_user_id"]),
            balance_value=message.text or "",
        )
    except BalanceValidationError:
        await message.answer(
            translate(language, "admin_user_balance_invalid"),
            reply_markup=build_admin_user_balance_prompt_markup(language, int(data["target_user_id"])),
        )
        return
    except UserLookupError:
        await state.clear()
        await message.answer(
            translate(language, "admin_user_not_found"),
            reply_markup=build_admin_user_balance_prompt_markup(language, int(data["target_user_id"])),
        )
        return

    await state.clear()
    await message.answer(
        text=render_balance_updated_text(user),
        reply_markup=build_admin_user_balance_prompt_markup(user.language, user.bot_user_id),
    )

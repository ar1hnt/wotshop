from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.db.models.transaction import TransactionStatus
from src.filters.admin import IsAdminFilter
from src.i18n import translate
from src.keyboards.callbacks import (
    AdminPanelAction,
    AdminPanelCallback,
    AdminTransactionAction,
    AdminTransactionActionCallback,
    AdminTransactionDetailCallback,
    AdminTransactionPageCallback,
    AdminTransactionsAction,
    AdminTransactionsCallback,
)
from src.keyboards.inline import (
    build_admin_back_markup,
    build_admin_main_markup,
    build_admin_transaction_detail_markup,
    build_admin_transaction_lookup_prompt_markup,
    build_admin_transactions_menu_markup,
    build_admin_transactions_page_markup,
)
from src.routers.common.navigation import render_screen_message
from src.services.reviews import render_admin_menu_text
from src.services.system import BotSettingsService
from src.services.transactions import (
    TransactionNotFoundError,
    TransactionService,
    render_admin_transaction_cancel_placeholder_text,
    render_admin_transaction_detail_text,
    render_admin_transaction_lookup_prompt_text,
    render_admin_transactions_menu_text,
    render_admin_transactions_page_text,
)
from src.states.admin_transactions import AdminTransactionState

router = Router(name="admin-transactions")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

transaction_service = TransactionService()
bot_settings_service = BotSettingsService()


@router.callback_query(AdminTransactionsCallback.filter())
async def handle_admin_transactions_menu(
    callback: CallbackQuery,
    callback_data: AdminTransactionsCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await transaction_service.get_user_language(callback.from_user)
    action = callback_data.action

    if action == AdminTransactionsAction.OPEN_MENU:
        await state.clear()
        await _render_transactions_menu(callback.message, callback.from_user, edit=True)
        await callback.answer()
        return

    if action == AdminTransactionsAction.BACK_TO_MAIN:
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

    if action == AdminTransactionsAction.OPEN_COMPLETED:
        await state.clear()
        await _render_transactions_page(
            callback.message,
            callback.from_user,
            status=TransactionStatus.COMPLETED,
            page=1,
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminTransactionsAction.OPEN_PENDING:
        await state.clear()
        await _render_transactions_page(
            callback.message,
            callback.from_user,
            status=TransactionStatus.PENDING,
            page=1,
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminTransactionsAction.LOOKUP:
        await state.clear()
        await state.set_state(AdminTransactionState.waiting_for_completed_transaction_id)
        await render_screen_message(
            callback.message,
            text=render_admin_transaction_lookup_prompt_text(language),
            reply_markup=build_admin_transaction_lookup_prompt_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminTransactionsAction.EXPORT:
        await state.clear()
        export_language, export_file = await transaction_service.export_completed_xlsx(callback.from_user)
        await callback.message.answer_document(document=export_file)
        await render_screen_message(
            callback.message,
            text=translate(export_language, "admin_export_transactions_done"),
            reply_markup=build_admin_back_markup(
                export_language,
                AdminTransactionsCallback(action=AdminTransactionsAction.OPEN_MENU).pack(),
            ),
            edit=True,
        )
        await callback.answer()
        return

    await callback.answer()


@router.message(AdminTransactionState.waiting_for_completed_transaction_id)
async def handle_admin_transaction_lookup(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return

    language = await transaction_service.get_user_language(message.from_user)
    raw_value = (message.text or "").strip()

    try:
        transaction_id = int(raw_value)
        if transaction_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            translate(language, "admin_transaction_invalid_id"),
            reply_markup=build_admin_transaction_lookup_prompt_markup(language),
        )
        return

    try:
        detail = await transaction_service.get_detail(
            message.from_user,
            transaction_id=transaction_id,
            expected_status=TransactionStatus.COMPLETED,
        )
    except TransactionNotFoundError:
        await message.answer(
            translate(language, "admin_transaction_not_found"),
            reply_markup=build_admin_transaction_lookup_prompt_markup(language),
        )
        return

    await _try_delete_message(message)
    await state.clear()
    await message.answer(
        text=render_admin_transaction_detail_text(detail),
        reply_markup=build_admin_transaction_detail_markup(
            detail,
            status=TransactionStatus.COMPLETED,
            page=1,
        ),
    )


@router.callback_query(AdminTransactionPageCallback.filter())
async def handle_admin_transaction_page(
    callback: CallbackQuery,
    callback_data: AdminTransactionPageCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    await _render_transactions_page(
        callback.message,
        callback.from_user,
        status=TransactionStatus(callback_data.status),
        page=callback_data.page,
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminTransactionDetailCallback.filter())
async def handle_admin_transaction_detail(
    callback: CallbackQuery,
    callback_data: AdminTransactionDetailCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    status = TransactionStatus(callback_data.status)
    try:
        detail = await transaction_service.get_detail(
            callback.from_user,
            transaction_id=callback_data.transaction_id,
            expected_status=status,
        )
    except TransactionNotFoundError:
        language = await transaction_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "admin_transaction_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_admin_transaction_detail_text(detail),
        reply_markup=build_admin_transaction_detail_markup(detail, status=status, page=callback_data.page),
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminTransactionActionCallback.filter())
async def handle_admin_transaction_action(
    callback: CallbackQuery,
    callback_data: AdminTransactionActionCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    language = await transaction_service.get_user_language(callback.from_user)

    if callback_data.action == AdminTransactionAction.CANCEL:
        await callback.answer(
            render_admin_transaction_cancel_placeholder_text(language),
            show_alert=True,
        )
        return

    await callback.answer()


async def _render_transactions_menu(message: Message, user, *, edit: bool) -> None:
    language, completed_count, pending_count = await transaction_service.get_transactions_menu_context(user)
    await render_screen_message(
        message,
        text=render_admin_transactions_menu_text(
            language,
            completed_count=completed_count,
            pending_count=pending_count,
        ),
        reply_markup=build_admin_transactions_menu_markup(language),
        edit=edit,
    )


async def _render_transactions_page(
    message: Message,
    user,
    *,
    status: TransactionStatus,
    page: int,
    edit: bool,
) -> None:
    page_data = await transaction_service.get_page(user, status=status, page=page)
    await render_screen_message(
        message,
        text=render_admin_transactions_page_text(page_data),
        reply_markup=build_admin_transactions_page_markup(page_data),
        edit=edit,
    )


async def _try_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        return

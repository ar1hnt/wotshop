from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.filters.admin import IsAdminFilter
from src.i18n import translate
from src.keyboards.callbacks import (
    AdminPanelAction,
    AdminPanelCallback,
    AdminProductDeleteAction,
    AdminProductDeleteCallback,
    AdminProductDetailCallback,
    AdminProductsAction,
    AdminProductsCallback,
)
from src.keyboards.inline import (
    build_admin_back_markup,
    build_admin_main_markup,
    build_admin_product_delete_confirmation_markup,
    build_admin_product_detail_markup,
    build_admin_product_lookup_prompt_markup,
    build_admin_products_menu_markup,
)
from src.routers.common.navigation import render_screen_message
from src.services.products import (
    ProductNotFoundError,
    ProductService,
    render_admin_product_delete_confirmation_text,
    render_admin_product_detail_text,
    render_admin_product_lookup_prompt_text,
    render_admin_products_menu_text,
)
from src.services.reviews import render_admin_menu_text
from src.services.sync import render_pricing_formula_text
from src.services.system import BotSettingsService
from src.states.admin_products import AdminProductState

router = Router(name="admin-products")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

product_service = ProductService()
bot_settings_service = BotSettingsService()


@router.callback_query(AdminProductsCallback.filter())
async def handle_admin_products_menu(
    callback: CallbackQuery,
    callback_data: AdminProductsCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await product_service.get_user_language(callback.from_user)
    action = callback_data.action

    if action == AdminProductsAction.OPEN_MENU:
        await state.clear()
        await _render_products_menu(callback.message, callback.from_user, edit=True)
        await callback.answer()
        return

    if action == AdminProductsAction.BACK_TO_MAIN:
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

    if action == AdminProductsAction.LOOKUP:
        await state.clear()
        await state.set_state(AdminProductState.waiting_for_product_id)
        await render_screen_message(
            callback.message,
            text=render_admin_product_lookup_prompt_text(language),
            reply_markup=build_admin_product_lookup_prompt_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminProductsAction.EXPORT:
        await state.clear()
        export_language, export_file = await product_service.export_products_xlsx(callback.from_user)
        await callback.message.answer_document(document=export_file)
        await render_screen_message(
            callback.message,
            text=translate(export_language, "admin_export_products_done"),
            reply_markup=build_admin_back_markup(
                export_language,
                AdminProductsCallback(action=AdminProductsAction.OPEN_MENU).pack(),
            ),
            edit=True,
        )
        await callback.answer()
        return

    if action == AdminProductsAction.MARKUPS:
        await state.clear()
        await render_screen_message(
            callback.message,
            text=render_pricing_formula_text(language),
            reply_markup=build_admin_product_lookup_prompt_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    await callback.answer()


@router.message(AdminProductState.waiting_for_product_id)
async def handle_admin_product_lookup(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return

    language = await product_service.get_user_language(message.from_user)
    raw_value = (message.text or "").strip()

    try:
        product_id = int(raw_value)
        if product_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            translate(language, "admin_product_invalid_id"),
            reply_markup=build_admin_product_lookup_prompt_markup(language),
        )
        return

    try:
        product = await product_service.get_product_detail(message.from_user, product_id=product_id, detail_page=1)
    except ProductNotFoundError:
        await message.answer(
            translate(language, "admin_product_not_found"),
            reply_markup=build_admin_product_lookup_prompt_markup(language),
        )
        return

    await _try_delete_message(message)
    await state.clear()
    await message.answer(
        text=render_admin_product_detail_text(product),
        reply_markup=build_admin_product_detail_markup(product),
    )


@router.callback_query(AdminProductDetailCallback.filter())
async def handle_admin_product_detail(
    callback: CallbackQuery,
    callback_data: AdminProductDetailCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    try:
        product = await product_service.get_product_detail(
            callback.from_user,
            product_id=callback_data.product_id,
            detail_page=callback_data.detail_page,
        )
    except ProductNotFoundError:
        language = await product_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "admin_product_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_admin_product_detail_text(product),
        reply_markup=build_admin_product_detail_markup(product),
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminProductDeleteCallback.filter())
async def handle_admin_product_delete(
    callback: CallbackQuery,
    callback_data: AdminProductDeleteCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await product_service.get_user_language(callback.from_user)

    if callback_data.action == AdminProductDeleteAction.ASK:
        await state.clear()
        await render_screen_message(
            callback.message,
            text=render_admin_product_delete_confirmation_text(language, product_id=callback_data.product_id),
            reply_markup=build_admin_product_delete_confirmation_markup(
                language,
                callback_data.product_id,
                detail_page=callback_data.detail_page,
            ),
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminProductDeleteAction.CANCEL:
        await state.clear()
        try:
            product = await product_service.get_product_detail(
                callback.from_user,
                product_id=callback_data.product_id,
                detail_page=callback_data.detail_page,
            )
        except ProductNotFoundError:
            await callback.answer(translate(language, "admin_product_not_found"), show_alert=True)
            return

        await render_screen_message(
            callback.message,
            text=render_admin_product_detail_text(product),
            reply_markup=build_admin_product_detail_markup(product),
            edit=True,
        )
        await callback.answer()
        return

    try:
        deleted_language = await product_service.delete_product(callback.from_user, product_id=callback_data.product_id)
    except ProductNotFoundError:
        await callback.answer(translate(language, "admin_product_not_found"), show_alert=True)
        return

    await state.clear()
    await render_screen_message(
        callback.message,
        text=translate(deleted_language, "admin_product_deleted_alert"),
        reply_markup=build_admin_back_markup(
            deleted_language,
            AdminProductsCallback(action=AdminProductsAction.OPEN_MENU).pack(),
        ),
        edit=True,
    )
    await callback.answer()


async def _render_products_menu(message: Message, user, *, edit: bool) -> None:
    language = await product_service.get_user_language(user)
    total_products = await product_service.get_total_products_count()
    await render_screen_message(
        message,
        text=render_admin_products_menu_text(language, total_products),
        reply_markup=build_admin_products_menu_markup(language),
        edit=edit,
    )


async def _try_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        return

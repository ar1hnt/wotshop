from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.db.models.catalog_account import GameAccountType
from src.db.models.review import ReviewStatus
from src.filters.admin import IsAdminFilter
from src.i18n import translate
from src.keyboards.callbacks import (
    AdminPanelAction,
    AdminPanelCallback,
    AdminSalesAction,
    AdminSalesCallback,
    AdminReviewAction,
    AdminReviewActionCallback,
    AdminReviewDetailCallback,
    AdminReviewRegistryCallback,
)
from src.keyboards.inline import (
    build_admin_back_markup,
    build_admin_faq_list_markup,
    build_admin_approved_detail_markup,
    build_admin_delete_confirmation_markup,
    build_admin_main_markup,
    build_admin_sales_markup,
    build_admin_products_menu_markup,
    build_admin_pending_detail_markup,
    build_admin_rejection_prompt_markup,
    build_admin_registry_menu_markup,
    build_admin_registry_page_markup,
    build_admin_statistics_menu_markup,
    build_admin_transactions_menu_markup,
    build_admin_users_menu_markup,
)
from src.routers.common.navigation import render_screen_message, render_screen_message_by_id
from src.schemas.common.menu import Screen, render_menu_view
from src.services.faq import FaqService, render_admin_faq_list_text
from src.services.products import ProductService, render_admin_products_menu_text
from src.services.reviews import (
    ReviewNotFoundError,
    ReviewPermissionError,
    ReviewService,
    render_admin_delete_confirmation_text,
    render_admin_menu_text,
    render_admin_registry_text,
    render_admin_rejection_prompt_text,
    render_admin_review_detail_text,
)
from src.services.statistics import render_admin_statistics_menu_text
from src.services.sync import (
    catalog_sync_service,
    render_catalog_refresh_not_configured_text,
    render_catalog_sync_running_alert,
    render_catalog_sync_started_text,
)
from src.services.system import BotSettingsService, render_sales_management_text
from src.services.transactions import TransactionService, render_admin_transactions_menu_text
from src.services.users import UserService, render_admin_users_menu_text
from src.states.reviews import AdminReviewModerationState

router = Router(name="admin-panel")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())
review_service = ReviewService()
user_service = UserService()
faq_service = FaqService()
product_service = ProductService()
bot_settings_service = BotSettingsService()
transaction_service = TransactionService()


@router.message(Command("admin"))
async def handle_admin_menu(message: Message) -> None:
    if message.from_user is None:
        return

    summary, is_created = await user_service.ensure_user(message.from_user)
    if is_created:
        await user_service.notify_admins_about_new_user(message.bot, summary)

    language = summary.language
    _, sales_enabled = await bot_settings_service.get_admin_context(message.from_user)
    await message.answer(
        text=render_admin_menu_text(language),
        reply_markup=build_admin_main_markup(language, sales_enabled),
    )


@router.callback_query(AdminPanelCallback.filter())
async def handle_admin_panel(
    callback: CallbackQuery,
    callback_data: AdminPanelCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    language = await review_service.get_user_language(callback.from_user)

    if callback_data.action == AdminPanelAction.REGISTRY:
        await render_screen_message(
            callback.message,
            text=translate(language, "admin_registry_menu_title"),
            reply_markup=build_admin_registry_menu_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminPanelAction.USERS:
        total_users = await user_service.get_total_users_count()
        await render_screen_message(
            callback.message,
            text=render_admin_users_menu_text(language, total_users),
            reply_markup=build_admin_users_menu_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminPanelAction.SALES:
        sales_context = await bot_settings_service.get_sales_context(callback.from_user)
        await render_screen_message(
            callback.message,
            text=render_sales_management_text(sales_context),
            reply_markup=build_admin_sales_markup(sales_context.language, sales_context.game_enabled),
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminPanelAction.STATISTICS:
        await render_screen_message(
            callback.message,
            text=render_admin_statistics_menu_text(language),
            reply_markup=build_admin_statistics_menu_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminPanelAction.FAQ:
        faq_view = await faq_service.get_admin_list(callback.from_user, page=1)
        await render_screen_message(
            callback.message,
            text=render_admin_faq_list_text(faq_view),
            reply_markup=build_admin_faq_list_markup(faq_view),
            media=render_menu_view(Screen.FAQ, faq_view.language).media,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminPanelAction.PRODUCTS:
        total_products = await product_service.get_total_products_count()
        await render_screen_message(
            callback.message,
            text=render_admin_products_menu_text(language, total_products),
            reply_markup=build_admin_products_menu_markup(language),
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminPanelAction.TRANSACTIONS:
        menu_language, completed_count, pending_count = await transaction_service.get_transactions_menu_context(
            callback.from_user
        )
        await render_screen_message(
            callback.message,
            text=render_admin_transactions_menu_text(
                menu_language,
                completed_count=completed_count,
                pending_count=pending_count,
            ),
            reply_markup=build_admin_transactions_menu_markup(menu_language),
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == AdminPanelAction.FORCE_REFRESH:
        if not catalog_sync_service.is_configured():
            await callback.answer(render_catalog_refresh_not_configured_text(language), show_alert=True)
            return

        started = await catalog_sync_service.start_background_sync(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            language=language,
            trigger="admin_panel",
        )
        if not started:
            await callback.answer(render_catalog_sync_running_alert(language), show_alert=True)
            return

        await render_screen_message(
            callback.message,
            text=render_catalog_sync_started_text(language),
            reply_markup=build_admin_back_markup(
                language,
                AdminPanelCallback(action=AdminPanelAction.BACK_TO_MAIN).pack(),
            ),
            edit=True,
        )
        await callback.answer()
        return

    _, sales_enabled = await bot_settings_service.get_admin_context(callback.from_user)
    await render_screen_message(
        callback.message,
        text=render_admin_menu_text(language),
        reply_markup=build_admin_main_markup(language, sales_enabled),
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminSalesCallback.filter())
async def handle_admin_sales(callback: CallbackQuery, callback_data: AdminSalesCallback) -> None:
    if callback.message is None:
        await callback.answer()
        return

    if callback_data.action == AdminSalesAction.BACK:
        language, sales_enabled = await bot_settings_service.get_admin_context(callback.from_user)
        await render_screen_message(
            callback.message,
            text=render_admin_menu_text(language),
            reply_markup=build_admin_main_markup(language, sales_enabled),
            edit=True,
        )
        await callback.answer()
        return

    action_to_game_type = {
        AdminSalesAction.TOGGLE_MIR_TANKOV: GameAccountType.MIR_TANKOV,
        AdminSalesAction.TOGGLE_TANKS_BLITZ: GameAccountType.TANKS_BLITZ,
        AdminSalesAction.TOGGLE_WORLD_OF_TANKS: GameAccountType.WORLD_OF_TANKS,
        AdminSalesAction.TOGGLE_WOT_BLITZ: GameAccountType.WOT_BLITZ,
    }
    if callback_data.action == AdminSalesAction.TOGGLE_ALL:
        context = await bot_settings_service.toggle_global_sales(callback.from_user)
    else:
        context = await bot_settings_service.toggle_game_sales(
            callback.from_user,
            action_to_game_type[callback_data.action],
        )
    await render_screen_message(
        callback.message,
        text=render_sales_management_text(context),
        reply_markup=build_admin_sales_markup(context.language, context.game_enabled),
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminReviewRegistryCallback.filter())
async def handle_admin_registry_page(
    callback: CallbackQuery,
    callback_data: AdminReviewRegistryCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    status = ReviewStatus(callback_data.status)
    page_data = await review_service.get_registry_page(
        callback.from_user,
        status=status,
        page=callback_data.page,
    )
    await render_screen_message(
        callback.message,
        text=render_admin_registry_text(page_data),
        reply_markup=build_admin_registry_page_markup(page_data),
        edit=True,
    )
    await callback.answer()


@router.callback_query(AdminReviewDetailCallback.filter())
async def handle_admin_review_detail(
    callback: CallbackQuery,
    callback_data: AdminReviewDetailCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await state.clear()
    try:
        await render_admin_review_detail_view(
            callback.message,
            admin_user=callback.from_user,
            review_id=callback_data.review_id,
            status=ReviewStatus(callback_data.status),
            page=callback_data.page,
            edit=True,
        )
    except ReviewNotFoundError:
        language = await review_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "admin_review_not_found"), show_alert=True)
        return
    await callback.answer()


@router.callback_query(AdminReviewActionCallback.filter())
async def handle_admin_review_action(
    callback: CallbackQuery,
    callback_data: AdminReviewActionCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    status = ReviewStatus(callback_data.status)
    action = callback_data.action

    try:
        if action == AdminReviewAction.APPROVE:
            await state.clear()
            detail = await review_service.approve_review(
                callback_data.review_id,
                admin_telegram_id=callback.from_user.id,
            )
            admin_language = await review_service.get_user_language(callback.from_user)
            await render_screen_message(
                callback.message,
                text=translate(admin_language, "admin_review_approved_alert"),
                reply_markup=build_admin_back_markup(
                    admin_language,
                    AdminReviewRegistryCallback(
                        status=ReviewStatus.APPROVED.value,
                        page=1,
                    ).pack(),
                ),
                edit=True,
            )
            await callback.answer()
            return

        if action == AdminReviewAction.REJECT:
            detail = await review_service.get_detail(callback_data.review_id)
            language = await review_service.get_user_language(callback.from_user)
            await state.set_state(AdminReviewModerationState.waiting_for_rejection_reason)
            await state.update_data(
                review_id=callback_data.review_id,
                status=status.value,
                page=callback_data.page,
                anchor_chat_id=callback.message.chat.id,
                anchor_message_id=callback.message.message_id,
            )
            await render_screen_message(
                callback.message,
                text=render_admin_rejection_prompt_text(language, detail),
                reply_markup=build_admin_rejection_prompt_markup(
                    callback_data.review_id,
                    status,
                    callback_data.page,
                    language,
                ),
                edit=True,
            )
            await callback.answer()
            return

        if action == AdminReviewAction.ASK_DELETE:
            await state.clear()
            detail = await review_service.get_detail(callback_data.review_id)
            language = await review_service.get_user_language(callback.from_user)
            await render_screen_message(
                callback.message,
                text=render_admin_delete_confirmation_text(language, detail),
                reply_markup=build_admin_delete_confirmation_markup(detail.id, status, callback_data.page, language),
                edit=True,
            )
            await callback.answer()
            return

        if action == AdminReviewAction.CANCEL_DELETE:
            await state.clear()
            await render_admin_review_detail_view(
                callback.message,
                admin_user=callback.from_user,
                review_id=callback_data.review_id,
                status=status,
                page=callback_data.page,
                edit=True,
            )
            await callback.answer()
            return

        if action == AdminReviewAction.DELETE:
            await state.clear()
            await review_service.delete_review(
                callback_data.review_id,
                admin_telegram_id=callback.from_user.id,
            )
            page_data = await review_service.get_registry_page(
                callback.from_user,
                status=ReviewStatus.APPROVED,
                page=callback_data.page,
            )
            await render_screen_message(
                callback.message,
                text=translate(page_data.language, "admin_review_deleted_alert"),
                reply_markup=build_admin_back_markup(
                    page_data.language,
                    AdminReviewRegistryCallback(
                        status=ReviewStatus.APPROVED.value,
                        page=page_data.page,
                    ).pack(),
                ),
                edit=True,
            )
            await callback.answer()
            return
    except ReviewNotFoundError:
        language = await review_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "admin_review_not_found"), show_alert=True)
        return


@router.message(AdminReviewModerationState.waiting_for_rejection_reason)
async def handle_rejection_reason(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    try:
        detail = await review_service.reject_review(
            int(data["review_id"]),
            admin_telegram_id=message.from_user.id,
            reason=message.text or "",
        )
    except ReviewNotFoundError:
        language = await review_service.get_user_language(message.from_user)
        await state.clear()
        await message.answer(
            translate(language, "admin_review_not_found"),
            reply_markup=build_admin_back_markup(
                language,
                AdminReviewRegistryCallback(
                    status=ReviewStatus.PENDING.value,
                    page=int(data.get("page", 1)),
                ).pack(),
            ),
        )
        return
    except ReviewPermissionError:
        language = await review_service.get_user_language(message.from_user)
        await message.answer(
            translate(language, "review_text_empty"),
            reply_markup=build_admin_rejection_prompt_markup(
                int(data["review_id"]),
                ReviewStatus(data["status"]),
                int(data["page"]),
                language,
            ),
        )
        return

    await notify_review_rejected(
        bot,
        detail.author.telegram_id,
        detail.author.language,
        detail.moderation_reason or "",
    )
    await render_admin_registry_anchor(
        bot,
        admin_user=message.from_user,
        chat_id=int(data["anchor_chat_id"]),
        message_id=int(data["anchor_message_id"]),
        status=ReviewStatus.PENDING,
        page=int(data["page"]),
    )
    await state.clear()
    await message.answer(translate(await review_service.get_user_language(message.from_user), "admin_review_rejected_alert"))


async def render_admin_review_detail_view(
    message: Message,
    *,
    admin_user,
    review_id: int,
    status: ReviewStatus,
    page: int,
    edit: bool,
) -> None:
    detail = await review_service.get_detail(review_id)
    registry = await review_service.get_registry_page(admin_user, status=status, page=page)
    markup = (
        build_admin_pending_detail_markup(detail.id, status, page, registry.language)
        if status == ReviewStatus.PENDING
        else build_admin_approved_detail_markup(detail.id, status, page, registry.language)
    )
    await render_screen_message(
        message,
        text=render_admin_review_detail_text(registry.language, detail),
        reply_markup=markup,
        edit=edit,
    )


async def render_admin_registry_anchor(
    bot: Bot,
    *,
    admin_user,
    chat_id: int,
    message_id: int,
    status: ReviewStatus,
    page: int,
) -> None:
    page_data = await review_service.get_registry_page(admin_user, status=status, page=page)
    await render_screen_message_by_id(
        bot,
        chat_id=chat_id,
        message_id=message_id,
        text=render_admin_registry_text(page_data),
        reply_markup=build_admin_registry_page_markup(page_data),
    )


async def notify_review_rejected(bot: Bot, telegram_id: int, language, reason: str) -> None:
    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=translate(language, "review_rejected_user_notification", reason=reason),
        )
    except TelegramAPIError:
        return

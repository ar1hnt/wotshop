import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

from src.i18n import Language, translate
from src.keyboards.callbacks import (
    FaqDetailCallback,
    FaqPageCallback,
    NavigationCallback,
    ProfileAction,
    ProfileActionCallback,
    ProfileHistoryPageCallback,
    ProfileLanguageCallback,
)
from src.keyboards.inline import (
    build_catalog_game_type_markup,
    build_favorites_markup,
    build_menu_markup,
    build_public_faq_detail_markup,
    build_public_faq_list_markup,
    build_profile_history_markup,
    build_profile_language_markup,
    build_profile_markup,
    build_payment_link_markup,
    build_top_up_prompt_markup,
    build_reviews_markup,
)
from src.schemas.common.menu import BUY_SCREEN_MEDIA, Screen, ScreenMediaSchema, render_menu_view
from src.services.faq import FaqNotFoundError, FaqService, render_public_faq_detail_text, render_public_faq_list_text
from src.services.catalog import CatalogService, render_catalog_game_type_text
from src.services.favorites import render_favorites_text
from src.services.media.media_cache import remember_photo_file_id, resolve_photo_input
from src.services.profile import (
    ProfileService,
    render_language_text,
    render_order_history_text,
    render_profile_text,
)
from src.services.payments import PaymentError, PaymentUnavailableError, payment_service
from src.services.reviews import ReviewService, render_reviews_text
from src.services.system import BotSettingsService, render_sales_disabled_alert
from src.services.users import UserService
from src.states.catalog import PaymentState

logger = logging.getLogger(__name__)
profile_service = ProfileService()
review_service = ReviewService()
user_service = UserService()
catalog_service = CatalogService()
faq_service = FaqService()
bot_settings_service = BotSettingsService()


router = Router(name="common-navigation")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user is None:
        return

    summary, is_created = await user_service.ensure_user(message.from_user)
    if is_created:
        await user_service.notify_admins_about_new_user(message.bot, summary)

    await show_screen(message, Screen.MAIN, message.from_user)


@router.callback_query(NavigationCallback.filter())
async def handle_navigation(
    callback: CallbackQuery,
    callback_data: NavigationCallback,
    state: FSMContext,
) -> None:
    screen = Screen(callback_data.screen)

    if callback.message is None:
        await callback.answer()
        return

    await state.clear()

    if screen == Screen.BUY and not await bot_settings_service.is_sales_enabled():
        language = await profile_service.get_user_language(callback.from_user)
        await callback.answer(render_sales_disabled_alert(language), show_alert=True)
        return

    await show_screen(callback.message, screen, callback.from_user, edit=True)
    await callback.answer()


@router.callback_query(FaqDetailCallback.filter())
async def handle_faq_detail(
    callback: CallbackQuery,
    callback_data: FaqDetailCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    try:
        detail = await faq_service.get_detail(callback.from_user, callback_data.faq_id, page=callback_data.page)
    except FaqNotFoundError:
        language = await faq_service.get_user_language(callback.from_user)
        await callback.answer(translate(language, "faq_not_found"), show_alert=True)
        return

    await render_screen_message(
        callback.message,
        text=render_public_faq_detail_text(detail),
        reply_markup=build_public_faq_detail_markup(detail.language, page=detail.page),
        media=render_menu_view(Screen.FAQ, detail.language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(FaqPageCallback.filter())
async def handle_faq_page(
    callback: CallbackQuery,
    callback_data: FaqPageCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await show_faq_screen(callback.message, callback.from_user, edit=True, page=callback_data.page)
    await callback.answer()


@router.callback_query(ProfileActionCallback.filter())
async def handle_profile_action(
    callback: CallbackQuery,
    callback_data: ProfileActionCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    if callback_data.action == ProfileAction.TOP_UP:
        summary = await profile_service.get_profile_summary(callback.from_user)
        await render_screen_message(
            callback.message,
            text=translate(summary.language, "payment_top_up_prompt"),
            reply_markup=build_top_up_prompt_markup(summary.language),
            media=render_menu_view(Screen.PROFILE, summary.language).media,
            edit=True,
        )
        await state.set_state(PaymentState.waiting_for_top_up_amount)
        await state.update_data(anchor_chat_id=callback.message.chat.id, anchor_message_id=callback.message.message_id)
        await callback.answer()
        return

    if callback_data.action == ProfileAction.OPEN_LANGUAGE:
        summary = await profile_service.get_profile_summary(callback.from_user)
        await render_screen_message(
            callback.message,
            text=render_language_text(summary.language),
            reply_markup=build_profile_language_markup(summary.language),
            media=render_menu_view(Screen.PROFILE, summary.language).media,
            edit=True,
        )
        await callback.answer()
        return

    if callback_data.action == ProfileAction.HISTORY:
        history_page = await profile_service.get_order_history_page(callback.from_user, page=1)
        await render_screen_message(
            callback.message,
            text=render_order_history_text(history_page),
            reply_markup=build_profile_history_markup(
                history_page.language,
                page=history_page.page,
                has_previous=history_page.has_previous,
                has_next=history_page.has_next,
            ),
            media=render_menu_view(Screen.PROFILE, history_page.language).media,
            edit=True,
        )
        await callback.answer()
        return

    await callback.answer()


@router.message(PaymentState.waiting_for_top_up_amount)
async def handle_top_up_amount(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    language = await profile_service.get_user_language(message.from_user)
    try:
        payment = await payment_service.create_top_up_payment(message.bot, message.from_user, message.text or "")
    except PaymentUnavailableError:
        await message.answer(
            translate(language, "payment_unavailable"),
            reply_markup=build_top_up_prompt_markup(language),
        )
        return
    except PaymentError:
        await message.answer(
            translate(language, "payment_top_up_invalid"),
            reply_markup=build_top_up_prompt_markup(language),
        )
        return

    await state.clear()
    await _try_delete_message(message)
    await render_screen_message_by_id(
        message.bot,
        chat_id=int(data["anchor_chat_id"]),
        message_id=int(data["anchor_message_id"]),
        text=translate(payment.language, "payment_top_up_pending", amount=_format_payment_amount(payment.amount)),
        reply_markup=build_payment_link_markup(payment.language, payment.payment_url),
        media=render_menu_view(Screen.PROFILE, payment.language).media,
    )


@router.callback_query(ProfileHistoryPageCallback.filter())
async def handle_profile_history_page(
    callback: CallbackQuery,
    callback_data: ProfileHistoryPageCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    history_page = await profile_service.get_order_history_page(callback.from_user, page=callback_data.page)
    await render_screen_message(
        callback.message,
        text=render_order_history_text(history_page),
        reply_markup=build_profile_history_markup(
            history_page.language,
            page=history_page.page,
            has_previous=history_page.has_previous,
            has_next=history_page.has_next,
        ),
        media=render_menu_view(Screen.PROFILE, history_page.language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(ProfileLanguageCallback.filter())
async def handle_profile_language_change(
    callback: CallbackQuery,
    callback_data: ProfileLanguageCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = Language(callback_data.language)
    summary = await profile_service.set_language(callback.from_user, language)

    await render_screen_message(
        callback.message,
        text=render_profile_text(summary),
        reply_markup=build_profile_markup(summary.language),
        media=render_menu_view(Screen.PROFILE, summary.language).media,
        edit=True,
    )
    await callback.answer(translate(summary.language, "language_updated"))


async def show_screen(message: Message, screen: Screen, user, edit: bool = False) -> None:
    if screen == Screen.BUY:
        await show_buy_screen(message, user, edit=edit)
        return
    if screen == Screen.FAVORITES:
        await show_favorites_screen(message, user, edit=edit)
        return
    if screen == Screen.PROFILE:
        await show_profile_screen(message, user, edit=edit)
        return
    if screen == Screen.REVIEWS:
        await show_reviews_screen(message, user, edit=edit)
        return
    if screen == Screen.FAQ:
        await show_faq_screen(message, user, edit=edit)
        return

    language = await profile_service.get_user_language(user)
    view = render_menu_view(screen, language)

    await render_screen_message(
        message,
        text=view.text,
        reply_markup=build_menu_markup(screen, language),
        media=view.media,
        edit=edit,
    )


async def show_profile_screen(message: Message, user, edit: bool = False) -> None:
    summary = await profile_service.get_profile_summary(user)
    await render_screen_message(
        message,
        text=render_profile_text(summary),
        reply_markup=build_profile_markup(summary.language),
        media=render_menu_view(Screen.PROFILE, summary.language).media,
        edit=edit,
    )


async def show_buy_screen(message: Message, user, edit: bool = False) -> None:
    language = await catalog_service.get_user_language(user)
    await render_screen_message(
        message,
        text=render_catalog_game_type_text(language),
        reply_markup=build_catalog_game_type_markup(language),
        media=BUY_SCREEN_MEDIA,
        edit=edit,
    )


async def show_faq_screen(message: Message, user, edit: bool = False, page: int = 1) -> None:
    faq_view = await faq_service.get_public_list(user, page=page)
    await render_screen_message(
        message,
        text=render_public_faq_list_text(faq_view),
        reply_markup=build_public_faq_list_markup(faq_view),
        media=render_menu_view(Screen.FAQ, faq_view.language).media,
        edit=edit,
    )


async def show_favorites_screen(message: Message, user, edit: bool = False, page: int = 1) -> None:
    favorites_page = await catalog_service.get_favorites_page(user, page=page)
    await render_screen_message(
        message,
        text=render_favorites_text(favorites_page),
        reply_markup=build_favorites_markup(favorites_page),
        media=render_menu_view(Screen.FAVORITES, favorites_page.language).media,
        edit=edit,
    )


async def show_reviews_screen(message: Message, user, edit: bool = False, page: int = 1) -> None:
    review_page = await review_service.get_public_page(user, page=page)
    await render_screen_message(
        message,
        text=render_reviews_text(review_page),
        reply_markup=build_reviews_markup(
            page=review_page.page,
            has_previous=review_page.has_previous,
            has_next=review_page.has_next,
            language=review_page.language,
        ),
        media=render_menu_view(Screen.REVIEWS, review_page.language).media,
        edit=edit,
    )


async def render_screen_message(
    message: Message,
    *,
    text: str,
    reply_markup,
    media: ScreenMediaSchema | None = None,
    edit: bool = False,
) -> None:
    if not edit:
        await send_screen_message(
            message,
            text=text,
            reply_markup=reply_markup,
            media=media,
        )
        return

    if await try_edit_screen_message(
        message,
        text=text,
        reply_markup=reply_markup,
        media=media,
    ):
        return

    await delete_message(message)
    await send_screen_message(
        message,
        text=text,
        reply_markup=reply_markup,
        media=media,
    )


async def render_screen_message_by_id(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup,
    media: ScreenMediaSchema | None = None,
) -> None:
    if await try_edit_screen_message_by_id(
        bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
        media=media,
    ):
        return

    await delete_message_by_id(bot, chat_id=chat_id, message_id=message_id)
    await send_screen_message_by_id(
        bot,
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        media=media,
    )


async def send_screen_message(
    message: Message,
    *,
    text: str,
    reply_markup,
    media: ScreenMediaSchema | None,
) -> None:
    if media is None:
        await message.answer(
            text=text,
            reply_markup=reply_markup,
        )
        return

    sent_message = await message.answer_photo(
        photo=resolve_photo_input(media),
        caption=text,
        reply_markup=reply_markup,
    )
    remember_photo_file_id(media, sent_message)


async def send_screen_message_by_id(
    bot: Bot,
    *,
    chat_id: int,
    text: str,
    reply_markup,
    media: ScreenMediaSchema | None,
) -> None:
    if media is None:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return

    sent_message = await bot.send_photo(
        chat_id=chat_id,
        photo=resolve_photo_input(media),
        caption=text,
        reply_markup=reply_markup,
    )
    remember_photo_file_id(media, sent_message)


async def try_edit_screen_message(
    message: Message,
    *,
    text: str,
    reply_markup,
    media: ScreenMediaSchema | None,
) -> bool:
    current_has_photo = bool(message.photo)
    target_has_photo = media is not None

    if current_has_photo != target_has_photo:
        return False

    try:
        if media is None:
            await message.edit_text(
                text=text,
                reply_markup=reply_markup,
            )
            return True

        edited_message = await message.edit_media(
            media=InputMediaPhoto(
                media=resolve_photo_input(media),
                caption=text,
            ),
            reply_markup=reply_markup,
        )
        if isinstance(edited_message, Message):
            remember_photo_file_id(media, edited_message)
        return True
    except TelegramBadRequest as error:
        error_text = str(error).lower()
        if "message is not modified" in error_text:
            return True
        if "there is no text in the message to edit" in error_text:
            return False
        if "message content is not modified" in error_text:
            return True
        logger.warning("Failed to edit screen message: %s", error)
        return False


async def try_edit_screen_message_by_id(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup,
    media: ScreenMediaSchema | None,
) -> bool:
    try:
        if media is None:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return True

        edited_message = await bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=InputMediaPhoto(
                media=resolve_photo_input(media),
                caption=text,
            ),
            reply_markup=reply_markup,
        )
        if isinstance(edited_message, Message):
            remember_photo_file_id(media, edited_message)
        return True
    except TelegramBadRequest as error:
        error_text = str(error).lower()
        if "message is not modified" in error_text:
            return True
        if "there is no text in the message to edit" in error_text:
            return False
        if "message content is not modified" in error_text:
            return True
        logger.warning("Failed to edit screen message by id: %s", error)
        return False


async def delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest as error:
        if "message can't be deleted" not in str(error).lower():
            logger.warning("Failed to delete message: %s", error)
            raise


async def delete_message_by_id(bot: Bot, *, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as error:
        if "message can't be deleted" not in str(error).lower():
            logger.warning("Failed to delete message by id: %s", error)
            raise


async def _try_delete_message(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        logger.debug("Failed to delete payment amount message_id=%s", message.message_id)


def _format_payment_amount(amount) -> str:
    return str(int(amount)) if amount == amount.to_integral() else f"{amount:.2f}"

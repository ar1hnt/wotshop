import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.db.models.review import ReviewRating
from src.i18n import translate
from src.keyboards.callbacks import (
    ReviewFlowAction,
    ReviewFlowCallback,
    ReviewRatingCallback,
    ReviewRulesCallback,
    ReviewsPageCallback,
)
from src.keyboards.inline import (
    build_review_rating_markup_for_page,
    build_review_rules_markup,
    build_review_waiting_markup,
)
from src.routers.common.navigation import render_screen_message, render_screen_message_by_id, show_reviews_screen
from src.schemas.common.menu import Screen, render_menu_view
from src.services.reviews import (
    ReviewLimitReachedError,
    ReviewPermissionError,
    ReviewService,
    ReviewTooLongError,
    ReviewValidationError,
    render_review_composer_text,
    render_review_rules_text,
)
from src.states.reviews import ReviewCreationState

logger = logging.getLogger(__name__)
router = Router(name="user-reviews")
review_service = ReviewService()


@router.callback_query(ReviewsPageCallback.filter())
async def handle_reviews_page(
    callback: CallbackQuery,
    callback_data: ReviewsPageCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    await show_reviews_screen(
        callback.message,
        callback.from_user,
        edit=True,
        page=callback_data.page,
    )
    await callback.answer()


@router.callback_query(ReviewFlowCallback.filter())
async def handle_review_flow(
    callback: CallbackQuery,
    callback_data: ReviewFlowCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    if callback_data.action == ReviewFlowAction.CANCEL:
        await state.clear()
        await show_reviews_screen(
            callback.message,
            callback.from_user,
            edit=True,
            page=callback_data.page,
        )
        await callback.answer()
        return

    language, has_purchases, has_available_review_slot = await review_service.user_can_leave_review(callback.from_user)
    if not has_purchases:
        await callback.answer(
            translate(language, "review_purchase_required"),
            show_alert=True,
        )
        return
    if not has_available_review_slot:
        await callback.answer(
            translate(language, "review_limit_reached"),
            show_alert=True,
        )
        return

    await render_screen_message(
        callback.message,
        text=render_review_composer_text(language),
        reply_markup=build_review_rating_markup_for_page(language, callback_data.page),
        media=render_menu_view(Screen.REVIEWS, language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(ReviewRulesCallback.filter())
async def handle_review_rules(
    callback: CallbackQuery,
    callback_data: ReviewRulesCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language = await review_service.get_user_language(callback.from_user)
    await render_screen_message(
        callback.message,
        text=render_review_rules_text(language),
        reply_markup=build_review_rules_markup(language, callback_data.page),
        media=render_menu_view(Screen.REVIEWS, language).media,
        edit=True,
    )
    await callback.answer()


@router.callback_query(ReviewRatingCallback.filter())
async def handle_review_rating(
    callback: CallbackQuery,
    callback_data: ReviewRatingCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    language, has_purchases, has_available_review_slot = await review_service.user_can_leave_review(callback.from_user)
    if not has_purchases:
        await state.clear()
        await callback.answer(
            translate(language, "review_purchase_required"),
            show_alert=True,
        )
        return
    if not has_available_review_slot:
        await state.clear()
        await callback.answer(
            translate(language, "review_limit_reached"),
            show_alert=True,
        )
        return

    rating = ReviewRating(callback_data.rating)
    await state.set_state(ReviewCreationState.waiting_for_text)
    await state.update_data(
        rating=rating.value,
        page=callback_data.page,
        anchor_chat_id=callback.message.chat.id,
        anchor_message_id=callback.message.message_id,
        language=language.value,
    )

    await render_screen_message(
        callback.message,
        text=render_review_composer_text(language, rating),
        reply_markup=build_review_waiting_markup(language, callback_data.page),
        media=render_menu_view(Screen.REVIEWS, language).media,
        edit=True,
    )
    await callback.answer()


@router.message(ReviewCreationState.waiting_for_text)
async def handle_review_text(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    rating = ReviewRating(data["rating"])
    anchor_chat_id = int(data["anchor_chat_id"])
    anchor_message_id = int(data["anchor_message_id"])

    try:
        review = await review_service.create_review(
            message.from_user,
            rating=rating,
            text=message.text or "",
        )
    except ReviewValidationError:
        language, _, _ = await review_service.user_can_leave_review(message.from_user)
        await message.answer(
            translate(language, "review_text_empty"),
            reply_markup=build_review_waiting_markup(language, int(data["page"])),
        )
        return
    except ReviewTooLongError:
        language, _, _ = await review_service.user_can_leave_review(message.from_user)
        await message.answer(
            translate(language, "review_text_too_long", limit=150),
            reply_markup=build_review_waiting_markup(language, int(data["page"])),
        )
        return
    except ReviewPermissionError:
        language, _, _ = await review_service.user_can_leave_review(message.from_user)
        await message.answer(
            translate(language, "review_purchase_required"),
            reply_markup=build_review_waiting_markup(language, int(data["page"])),
        )
        return
    except ReviewLimitReachedError:
        language, _, _ = await review_service.user_can_leave_review(message.from_user)
        await message.answer(
            translate(language, "review_limit_reached"),
            reply_markup=build_review_waiting_markup(language, int(data["page"])),
        )
        return

    await notify_admins_about_review(bot, review.id)
    await state.clear()

    await render_public_reviews_anchor(
        bot,
        user=message.from_user,
        chat_id=anchor_chat_id,
        message_id=anchor_message_id,
        page=1,
    )
    page_data = await review_service.get_public_page(message.from_user, page=1)
    await message.answer(translate(page_data.language, "review_published"))


async def notify_admins_about_review(bot: Bot, review_id: int) -> None:
    from src.config import settings
    from src.keyboards.inline import build_admin_pending_detail_markup
    from src.services.reviews import render_admin_notification_text

    review = await review_service.get_detail(review_id)

    for admin_id in settings.admin_ids:
        try:
            admin_language = await review_service.get_language_by_telegram_id(admin_id)
            await bot.send_message(
                chat_id=admin_id,
                text=render_admin_notification_text(admin_language, review),
                reply_markup=build_admin_pending_detail_markup(
                    review_id=review.id,
                    status=review.status,
                    page=1,
                    language=admin_language,
                ),
            )
        except TelegramAPIError:
            logger.warning("Failed to notify admin telegram_id=%s about review_id=%s", admin_id, review_id)


async def render_public_reviews_anchor(
    bot: Bot,
    *,
    user,
    chat_id: int,
    message_id: int,
    page: int,
) -> None:
    from src.keyboards.inline import build_reviews_markup
    from src.services.reviews import render_reviews_text

    page_data = await review_service.get_public_page(user, page=page)
    await render_screen_message_by_id(
        bot,
        chat_id=chat_id,
        message_id=message_id,
        text=render_reviews_text(page_data),
        reply_markup=build_reviews_markup(
            page=page_data.page,
            has_previous=page_data.has_previous,
            has_next=page_data.has_next,
            language=page_data.language,
        ),
        media=render_menu_view(Screen.REVIEWS, page_data.language).media,
    )

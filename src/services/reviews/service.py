import logging
from datetime import UTC, datetime
from html import escape

from aiogram.types import User as TelegramUser

from src.config import settings
from src.db import async_session_factory
from src.db.models.review import ReviewRating, ReviewStatus
from src.db.repositories import OrderRepository, ReviewRepository, UserRepository
from src.i18n import Language, translate
from src.schemas.reviews import (
    ReviewAuthorSchema,
    ReviewDetailSchema,
    ReviewListItemSchema,
    ReviewPageSchema,
    ReviewRegistryPageSchema,
)

logger = logging.getLogger(__name__)

COMMON_REVIEWS_PAGE_SIZE = 5
ADMIN_REVIEWS_PAGE_SIZE = 8
MAX_REVIEW_TEXT_LENGTH = 150


class ReviewPermissionError(Exception):
    pass


class ReviewLimitReachedError(Exception):
    pass


class ReviewValidationError(Exception):
    pass


class ReviewTooLongError(Exception):
    pass


class ReviewNotFoundError(Exception):
    pass


class ReviewService:
    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await session.commit()

        return Language(user.language)

    async def get_language_by_telegram_id(self, telegram_id: int) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_by_telegram_id(telegram_id)
            await session.commit()

        if user is None:
            return Language.RU

        return Language(user.language)

    async def get_public_page(self, telegram_user: TelegramUser, page: int = 1) -> ReviewPageSchema:
        safe_page = max(page, 1)

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            review_repository = ReviewRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            total_items = await review_repository.count_public()
            last_page = max(1, (total_items + COMMON_REVIEWS_PAGE_SIZE - 1) // COMMON_REVIEWS_PAGE_SIZE)
            safe_page = min(safe_page, last_page)
            reviews = await review_repository.get_public_page(
                offset=(safe_page - 1) * COMMON_REVIEWS_PAGE_SIZE,
                limit=COMMON_REVIEWS_PAGE_SIZE,
            )
            positive_count, negative_count = await review_repository.get_public_rating_totals()
            await session.commit()

        has_previous = safe_page > 1
        has_next = total_items > safe_page * COMMON_REVIEWS_PAGE_SIZE

        return ReviewPageSchema(
            language=Language(user.language),
            positive_count=positive_count,
            negative_count=negative_count,
            page=safe_page,
            total_pages=last_page,
            total_count=total_items,
            has_previous=has_previous,
            has_next=has_next,
            items=tuple(self._to_list_item(review) for review in reviews),
        )

    async def user_can_leave_review(self, telegram_user: TelegramUser) -> tuple[Language, bool, bool]:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            order_repository = OrderRepository(session)
            review_repository = ReviewRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            purchases_count, _ = await order_repository.get_user_stats(user.id)
            reviews_count = await review_repository.count_consumed_slots_by_user(user_id=user.id)
            await session.commit()

        has_purchases = purchases_count > 0
        has_available_review_slot = purchases_count > reviews_count
        return Language(user.language), has_purchases, has_available_review_slot

    async def create_review(
        self,
        telegram_user: TelegramUser,
        *,
        rating: ReviewRating,
        text: str,
    ) -> ReviewDetailSchema:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ReviewValidationError
        if len(cleaned_text) > MAX_REVIEW_TEXT_LENGTH:
            raise ReviewTooLongError

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            order_repository = OrderRepository(session)
            review_repository = ReviewRepository(session)

            user = await user_repository.get_or_create_from_telegram(telegram_user)
            purchases_count, _ = await order_repository.get_user_stats(user.id)
            reviews_count = await review_repository.count_consumed_slots_by_user(user_id=user.id)
            if purchases_count <= 0:
                await session.rollback()
                raise ReviewPermissionError
            if purchases_count <= reviews_count:
                await session.rollback()
                raise ReviewLimitReachedError

            review = await review_repository.create(
                user_id=user.id,
                rating=rating,
                text=cleaned_text,
            )
            review = await review_repository.get_by_id(review.id) or review
            await session.commit()

        logger.info(
            "Created review id=%s user_id=%s telegram_id=%s rating=%s",
            review.id,
            user.id,
            telegram_user.id,
            rating.value,
        )
        return self._to_detail(review)

    async def get_detail(self, review_id: int) -> ReviewDetailSchema:
        async with async_session_factory() as session:
            review_repository = ReviewRepository(session)
            review = await review_repository.get_by_id(review_id)
            await session.commit()

        if review is None:
            raise ReviewNotFoundError

        return self._to_detail(review)

    async def get_registry_page(
        self,
        admin_user: TelegramUser,
        *,
        status: ReviewStatus,
        page: int = 1,
    ) -> ReviewRegistryPageSchema:
        safe_page = max(page, 1)

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            review_repository = ReviewRepository(session)

            admin = await user_repository.get_or_create_from_telegram(admin_user)
            total_items = await review_repository.count_by_status(status)
            last_page = max(1, (total_items + ADMIN_REVIEWS_PAGE_SIZE - 1) // ADMIN_REVIEWS_PAGE_SIZE)
            safe_page = min(safe_page, last_page)
            reviews = await review_repository.get_page_by_status(
                status=status,
                offset=(safe_page - 1) * ADMIN_REVIEWS_PAGE_SIZE,
                limit=ADMIN_REVIEWS_PAGE_SIZE,
            )
            await session.commit()

        return ReviewRegistryPageSchema(
            language=Language(admin.language),
            status=status,
            page=safe_page,
            has_previous=safe_page > 1,
            has_next=total_items > safe_page * ADMIN_REVIEWS_PAGE_SIZE,
            items=tuple(self._to_detail(review) for review in reviews),
        )

    async def approve_review(self, review_id: int, *, admin_telegram_id: int) -> ReviewDetailSchema:
        async with async_session_factory() as session:
            review_repository = ReviewRepository(session)
            review = await review_repository.get_by_id(review_id)
            if review is None:
                await session.rollback()
                raise ReviewNotFoundError

            await review_repository.approve(review, admin_telegram_id=admin_telegram_id)
            await session.commit()

        logger.info("Approved review id=%s admin_telegram_id=%s", review_id, admin_telegram_id)
        return self._to_detail(review)

    async def reject_review(
        self,
        review_id: int,
        *,
        admin_telegram_id: int,
        reason: str,
    ) -> ReviewDetailSchema:
        cleaned_reason = reason.strip()
        if not cleaned_reason:
            raise ReviewPermissionError

        async with async_session_factory() as session:
            review_repository = ReviewRepository(session)
            review = await review_repository.get_by_id(review_id)
            if review is None:
                await session.rollback()
                raise ReviewNotFoundError

            await review_repository.reject(
                review,
                admin_telegram_id=admin_telegram_id,
                reason=cleaned_reason,
            )
            await session.commit()

        logger.info("Rejected review id=%s admin_telegram_id=%s", review_id, admin_telegram_id)
        return self._to_detail(review)

    async def delete_review(self, review_id: int, *, admin_telegram_id: int) -> ReviewDetailSchema:
        async with async_session_factory() as session:
            review_repository = ReviewRepository(session)
            review = await review_repository.get_by_id(review_id)
            if review is None:
                await session.rollback()
                raise ReviewNotFoundError

            await review_repository.delete(review, admin_telegram_id=admin_telegram_id)
            await session.commit()

        logger.info("Deleted review id=%s admin_telegram_id=%s", review_id, admin_telegram_id)
        return self._to_detail(review)

    @staticmethod
    def _to_author(review) -> ReviewAuthorSchema:
        user = review.user
        username = f"@{user.username}" if user.username else _resolve_name(user.first_name, user.last_name)
        return ReviewAuthorSchema(
            bot_user_id=user.id,
            telegram_id=user.telegram_id,
            username=username or translate(Language.RU, "unknown_username"),
            language=Language(user.language),
        )

    @classmethod
    def _to_list_item(cls, review) -> ReviewListItemSchema:
        return ReviewListItemSchema(
            id=review.id,
            rating=ReviewRating(review.rating),
            text=review.text,
            created_at=review.created_at,
            author=cls._to_author(review),
        )

    @classmethod
    def _to_detail(cls, review) -> ReviewDetailSchema:
        return ReviewDetailSchema(
            id=review.id,
            rating=ReviewRating(review.rating),
            status=ReviewStatus(review.status),
            text=review.text,
            created_at=review.created_at,
            moderation_reason=review.moderation_reason,
            author=cls._to_author(review),
        )


def render_reviews_text(page: ReviewPageSchema) -> str:
    lines = [
        translate(page.language, "reviews_title"),
        "",
        translate(
            page.language,
            "reviews_totals",
            positive_count=page.positive_count,
            negative_count=page.negative_count,
        ),
        "",
    ]

    if page.total_count > 0:
        lines.extend(
            (
                translate(
                    page.language,
                    "reviews_page_meta",
                    page=page.page,
                    total_pages=page.total_pages,
                ),
                "",
            )
        )

    if not page.items:
        lines.append(translate(page.language, "reviews_empty"))
        return "\n".join(lines)

    lines.extend(_render_public_review_block(page.language, item) for item in page.items)
    return "\n".join(lines)


def render_review_composer_text(language: Language, rating: ReviewRating | None = None) -> str:
    if rating is None:
        return translate(language, "review_create_choose_rating")

    return translate(
        language,
        "review_create_prompt",
        rating=_rating_label(language, rating),
    )


def render_review_rules_text(language: Language) -> str:
    return "\n".join(
        (
            translate(language, "review_rules_title"),
            "",
            f"1. {translate(language, 'review_rules_item_1')}",
            f"2. {translate(language, 'review_rules_item_2')}",
            f"3. {translate(language, 'review_rules_item_3')}",
            f"4. {translate(language, 'review_rules_item_4')}",
            f"5. {translate(language, 'review_rules_item_5')}",
            f"6. {translate(language, 'review_rules_item_6')}",
            "",
            translate(language, "review_rules_note"),
        )
    )


def render_admin_menu_text(language: Language) -> str:
    return translate(language, "admin_menu_title")


def render_admin_registry_text(page: ReviewRegistryPageSchema) -> str:
    title_key = "admin_pending_title" if page.status == ReviewStatus.PENDING else "admin_approved_title"
    lines = [
        translate(page.language, title_key),
        "",
    ]

    if not page.items:
        lines.append(translate(page.language, "admin_reviews_empty"))
        return "\n".join(lines)

    lines.append(
        translate(
            page.language,
            "admin_reviews_page_meta",
            page=page.page,
            count=len(page.items),
        )
    )
    return "\n".join(lines)


def render_admin_review_detail_text(language: Language, review: ReviewDetailSchema) -> str:
    return "\n".join(
        (
            translate(language, "admin_review_detail_title", review_id=review.id),
            "",
            translate(language, "admin_review_author_bot_id", bot_user_id=review.author.bot_user_id),
            translate(language, "admin_review_author_tg_id", telegram_id=review.author.telegram_id),
            translate(language, "admin_review_author_username", username=escape(review.author.username)),
            translate(language, "admin_review_type", rating=_rating_label(language, review.rating)),
            "",
            translate(language, "admin_review_date", created_at=_format_datetime(review.created_at)),
            translate(language, "admin_review_status", status=_status_label(language, review.status)),
            "",
            "<b>Текст:</b>",
            f"<blockquote>{escape(review.text)}</blockquote>",
        )
    )


def render_admin_delete_confirmation_text(language: Language, review: ReviewDetailSchema) -> str:
    return translate(language, "admin_review_delete_confirm", review_id=review.id)


def render_admin_rejection_prompt_text(language: Language, review: ReviewDetailSchema) -> str:
    return "\n".join(
        (
            translate(language, "admin_review_reject_prompt", review_id=review.id),
            "",
            f"<blockquote>{escape(review.text)}</blockquote>",
        )
    )


def render_admin_notification_text(language: Language, review: ReviewDetailSchema) -> str:
    return "\n".join(
        (
            translate(language, "admin_review_notification_title", review_id=review.id),
            "",
            translate(language, "admin_review_author_bot_id", bot_user_id=review.author.bot_user_id),
            translate(language, "admin_review_author_tg_id", telegram_id=review.author.telegram_id),
            translate(language, "admin_review_author_username", username=escape(review.author.username)),
            "",
            translate(language, "admin_review_type", rating=_rating_label(language, review.rating)),
            translate(language, "admin_review_date", created_at=_format_datetime(review.created_at)),
            "",
            "<b>Текст:</b>",
            f"<blockquote>{escape(review.text)}</blockquote>",
        )
    )


def build_admin_review_button_text(review: ReviewDetailSchema) -> str:
    short_text = review.text.strip().replace("\n", " ")
    shortened = short_text if len(short_text) <= 30 else f"{short_text[:27]}..."
    return f"#{review.id} — {shortened}"


def _render_public_review_block(language: Language, item: ReviewListItemSchema) -> str:
    return "\n".join(
        (
            f"<blockquote>{_rating_emoji(item.rating)} | ID: {item.author.bot_user_id} | {_format_datetime(item.created_at)}",
            escape(item.text),
            "</blockquote>",
        )
    )


def _rating_label(language: Language, rating: ReviewRating) -> str:
    key = "review_rating_positive" if rating == ReviewRating.POSITIVE else "review_rating_negative"
    return translate(language, key)


def _status_label(language: Language, status: ReviewStatus) -> str:
    mapping = {
        ReviewStatus.PENDING: "review_status_pending",
        ReviewStatus.APPROVED: "review_status_approved",
        ReviewStatus.REJECTED: "review_status_rejected",
        ReviewStatus.DELETED: "review_status_deleted",
    }
    return translate(language, mapping[status])


def _rating_emoji(rating: ReviewRating) -> str:
    return "👍" if rating == ReviewRating.POSITIVE else "👎"


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")


def _resolve_name(first_name: str | None, last_name: str | None) -> str:
    return " ".join(part for part in (first_name, last_name) if part)

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.db.models import Review
from src.db.models.review import ReviewRating, ReviewStatus


PUBLIC_REVIEW_STATUSES: tuple[str, ...] = (
    ReviewStatus.PENDING.value,
    ReviewStatus.APPROVED.value,
)

CONSUMED_REVIEW_SLOT_STATUSES: tuple[str, ...] = (
    ReviewStatus.PENDING.value,
    ReviewStatus.APPROVED.value,
    ReviewStatus.DELETED.value,
)


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        rating: ReviewRating,
        text: str,
    ) -> Review:
        review = Review(
            user_id=user_id,
            rating=rating.value,
            status=ReviewStatus.PENDING.value,
            text=text,
        )
        self.session.add(review)
        await self.session.flush()
        return review

    async def get_by_id(self, review_id: int) -> Review | None:
        query = (
            select(Review)
            .options(joinedload(Review.user))
            .where(Review.id == review_id)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_public_page(self, *, offset: int, limit: int) -> list[Review]:
        query = (
            select(Review)
            .options(joinedload(Review.user))
            .where(Review.status.in_(PUBLIC_REVIEW_STATUSES))
            .order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique())

    async def count_public(self) -> int:
        query = select(func.count(Review.id)).where(Review.status.in_(PUBLIC_REVIEW_STATUSES))
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def count_by_user(self, *, user_id: int) -> int:
        query = select(func.count(Review.id)).where(Review.user_id == user_id)
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def count_consumed_slots_by_user(self, *, user_id: int) -> int:
        query = (
            select(func.count(Review.id))
            .where(Review.user_id == user_id)
            .where(Review.status.in_(CONSUMED_REVIEW_SLOT_STATUSES))
        )
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def get_public_rating_totals(self) -> tuple[int, int]:
        query = select(
            func.coalesce(
                func.sum(case((Review.rating == ReviewRating.POSITIVE.value, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((Review.rating == ReviewRating.NEGATIVE.value, 1), else_=0)),
                0,
            ),
        ).where(Review.status.in_(PUBLIC_REVIEW_STATUSES))
        result = await self.session.execute(query)
        positive_count, negative_count = result.one()
        return int(positive_count), int(negative_count)

    async def get_rating_totals_in_period(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> tuple[int, int]:
        query = select(
            func.coalesce(
                func.sum(case((Review.rating == ReviewRating.POSITIVE.value, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((Review.rating == ReviewRating.NEGATIVE.value, 1), else_=0)),
                0,
            ),
        )

        if start_at is not None:
            query = query.where(Review.created_at >= start_at)
        if end_at is not None:
            query = query.where(Review.created_at <= end_at)

        result = await self.session.execute(query)
        positive_count, negative_count = result.one()
        return int(positive_count), int(negative_count)

    async def get_page_by_status(
        self,
        *,
        status: ReviewStatus,
        offset: int,
        limit: int,
    ) -> list[Review]:
        query = (
            select(Review)
            .options(joinedload(Review.user))
            .where(Review.status == status.value)
            .order_by(Review.created_at.desc(), Review.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique())

    async def count_by_status(self, status: ReviewStatus) -> int:
        query = select(func.count(Review.id)).where(Review.status == status.value)
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def approve(self, review: Review, *, admin_telegram_id: int) -> None:
        review.status = ReviewStatus.APPROVED.value
        review.moderation_reason = None
        review.moderated_by_telegram_id = admin_telegram_id
        await self.session.flush()

    async def reject(self, review: Review, *, admin_telegram_id: int, reason: str) -> None:
        review.status = ReviewStatus.REJECTED.value
        review.moderation_reason = reason
        review.moderated_by_telegram_id = admin_telegram_id
        await self.session.flush()

    async def delete(self, review: Review, *, admin_telegram_id: int) -> None:
        review.status = ReviewStatus.DELETED.value
        review.moderation_reason = None
        review.moderated_by_telegram_id = admin_telegram_id
        await self.session.flush()

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.user import User


class ReviewRating(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELETED = "deleted"


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default=ReviewStatus.PENDING.value, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    moderation_reason: Mapped[str | None] = mapped_column(Text)
    moderated_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger)

    user: Mapped["User"] = relationship(back_populates="reviews")

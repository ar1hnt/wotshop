from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.db.models.review import ReviewRating, ReviewStatus
from src.i18n import Language


class ReviewAuthorSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    bot_user_id: int
    telegram_id: int
    username: str
    language: Language


class ReviewListItemSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    rating: ReviewRating
    text: str
    created_at: datetime
    author: ReviewAuthorSchema


class ReviewPageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    positive_count: int
    negative_count: int
    page: int = Field(ge=1)
    total_pages: int = Field(ge=1)
    total_count: int = Field(ge=0)
    has_previous: bool
    has_next: bool
    items: tuple[ReviewListItemSchema, ...]


class ReviewDetailSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    rating: ReviewRating
    status: ReviewStatus
    text: str
    created_at: datetime
    moderation_reason: str | None
    author: ReviewAuthorSchema


class ReviewRegistryPageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    status: ReviewStatus
    page: int = Field(ge=1)
    has_previous: bool
    has_next: bool
    items: tuple[ReviewDetailSchema, ...]

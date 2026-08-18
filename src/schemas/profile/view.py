from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.i18n import Language


class ProfileSummarySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    username: str
    user_id: int
    telegram_id: int
    balance: Decimal
    purchases_count: int
    total_spent: Decimal


class OrderHistoryEntrySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: int
    amount: Decimal
    currency: str
    created_at: datetime
    delivery_data: dict[str, str] | None
    fulfillment_payload: dict[str, object] | None


class OrderHistoryPageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    items: list[OrderHistoryEntrySchema]
    page: int
    total_pages: int
    total_count: int
    has_previous: bool
    has_next: bool

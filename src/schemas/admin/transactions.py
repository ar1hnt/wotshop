from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.db.models.transaction import TransactionStatus, TransactionType
from src.i18n import Language


class AdminTransactionListItemSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    user_id: int
    telegram_id: int
    username: str
    transaction_type: TransactionType
    status: TransactionStatus
    amount: Decimal
    currency: str
    description: str | None
    created_at: datetime


class AdminTransactionPageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    status: TransactionStatus
    page: int
    total_pages: int
    total_count: int
    items: list[AdminTransactionListItemSchema]

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


class AdminTransactionDetailSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    id: int
    catalog_account_id: int | None
    user_id: int
    telegram_id: int
    username: str
    order_id: int | None
    transaction_type: TransactionType
    status: TransactionStatus
    amount: Decimal
    currency: str
    description: str | None
    provider_name: str | None
    provider_transaction_id: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    canceled_at: datetime | None

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.order import Order
    from src.db.models.user import User


class TransactionType(StrEnum):
    PURCHASE = "purchase"
    TOP_UP = "top_up"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    catalog_account_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_accounts.id", ondelete="SET NULL"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TransactionStatus.PENDING.value, nullable=False)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    provider_name: Mapped[str | None] = mapped_column(String(64))
    provider_transaction_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    payment_url: Mapped[str | None] = mapped_column(Text)
    provider_payment_method: Mapped[int | None]
    failure_reason: Mapped[str | None] = mapped_column(Text)
    checkout_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    checkout_message_id: Mapped[int | None]
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    balance_refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="transactions")
    order: Mapped["Order | None"] = relationship(back_populates="transactions")

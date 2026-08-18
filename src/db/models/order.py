from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.financial import CARD_WITHDRAWAL_LOSS_PERCENT
from src.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.db.models.transaction import Transaction
    from src.db.models.user import User


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    catalog_account_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_accounts.id", ondelete="SET NULL"))
    supplier_item_id: Mapped[int | None] = mapped_column(BigInteger)
    account_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    fulfillment_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    delivery_data: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    sale_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    supplier_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    payout_fee_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=CARD_WITHDRAWAL_LOSS_PERCENT,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="paid", nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="orders")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="order")

    @property
    def payout_commission_amount(self) -> Decimal:
        return (self.sale_amount * self.payout_fee_percent / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def profit_amount(self) -> Decimal:
        return (self.sale_amount - self.supplier_amount - self.payout_commission_amount).quantize(Decimal("0.01"))

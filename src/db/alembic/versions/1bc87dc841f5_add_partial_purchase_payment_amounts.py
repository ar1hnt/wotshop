"""add partial purchase payment amounts

Revision ID: 1bc87dc841f5
Revises: 8cf8f904eb61
Create Date: 2026-08-16 18:35:43.264965

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bc87dc841f5'
down_revision: Union[str, Sequence[str], None] = '8cf8f904eb61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add amounts used by the partial-balance purchase flow."""
    # Existing purchases did not split their amount: none was reserved from the
    # internal balance and the entire transaction amount was external payment.
    op.add_column(
        "transactions",
        sa.Column("balance_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("payment_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("balance_refunded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE transactions SET balance_amount = 0, payment_amount = amount")
    op.alter_column("transactions", "balance_amount", nullable=False)
    op.alter_column("transactions", "payment_amount", nullable=False)


def downgrade() -> None:
    """Remove partial-balance purchase fields."""
    op.drop_column("transactions", "balance_refunded_at")
    op.drop_column("transactions", "payment_amount")
    op.drop_column("transactions", "balance_amount")

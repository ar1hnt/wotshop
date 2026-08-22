"""add catalog price filter

Revision ID: c4e8f1a2b6d9
Revises: 9a1d3f5b7c2e
Create Date: 2026-08-22 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e8f1a2b6d9"
down_revision: Union[str, Sequence[str], None] = "9a1d3f5b7c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_catalog_filters", sa.Column("sale_price_min", sa.Numeric(12, 2), nullable=True))
    op.add_column("user_catalog_filters", sa.Column("sale_price_max", sa.Numeric(12, 2), nullable=True))
    op.execute(
        """
        UPDATE user_catalog_filters
        SET active_sort_field = 'price', price_sort_direction = 'asc'
        """
    )


def downgrade() -> None:
    op.drop_column("user_catalog_filters", "sale_price_max")
    op.drop_column("user_catalog_filters", "sale_price_min")

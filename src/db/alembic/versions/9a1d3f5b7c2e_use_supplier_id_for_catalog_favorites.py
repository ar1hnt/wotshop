"""use supplier IDs for catalog favorites

Revision ID: 9a1d3f5b7c2e
Revises: 668dab870efe
Create Date: 2026-08-22 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "9a1d3f5b7c2e"
down_revision: Union[str, Sequence[str], None] = "668dab870efe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate existing favorites while their old local catalog IDs still exist."""
    op.execute(
        """
        UPDATE favorites AS favorite
        SET product_code = 'catalog_supplier:' || account.supplier_item_id::text
        FROM catalog_accounts AS account
        WHERE favorite.product_code = 'catalog_account:' || account.id::text
        """
    )


def downgrade() -> None:
    """Restore local catalog IDs for rows whose catalog account is still present."""
    op.execute(
        """
        UPDATE favorites AS favorite
        SET product_code = 'catalog_account:' || account.id::text
        FROM catalog_accounts AS account
        WHERE favorite.product_code = 'catalog_supplier:' || account.supplier_item_id::text
        """
    )

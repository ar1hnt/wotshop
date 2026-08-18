from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin


class GameAccountType(StrEnum):
    MIR_TANKOV = "mir_tankov"
    TANKS_BLITZ = "tanks_blitz"
    WORLD_OF_TANKS = "world_of_tanks"
    WOT_BLITZ = "wot_blitz"


class CatalogAccountStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    ARCHIVED = "archived"


class CatalogSortField(StrEnum):
    PRICE = "price"
    LAST_ACTIVITY = "last_activity"
    NEWEST = "newest"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


class CatalogAccount(TimestampMixin, Base):
    __tablename__ = "catalog_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    supplier_category_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    supplier_item_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    game_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16),
        default=CatalogAccountStatus.AVAILABLE.value,
        nullable=False,
        index=True,
    )
    reserved_for_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    top_tank_count: Mapped[int] = mapped_column(default=0, nullable=False)
    premium_tank_count: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tank_count: Mapped[int] = mapped_column(default=0, nullable=False)
    silver_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    gold_amount: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    battles_count: Mapped[int] = mapped_column(default=0, nullable=False)
    wins_count: Mapped[int] = mapped_column(default=0, nullable=False)
    win_rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_tier_11: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supplier_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False, index=True)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_phone_bound: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_in_clan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tanks_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    region: Mapped[str | None] = mapped_column(String(64), index=True)
    tanks_payload: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    supplier_loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

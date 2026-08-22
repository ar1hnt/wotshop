from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin
from src.db.models.catalog_account import CatalogSortField, GameAccountType, SortDirection


class UserCatalogFilter(TimestampMixin, Base):
    __tablename__ = "user_catalog_filters"
    __table_args__ = (
        UniqueConstraint("user_id", "game_type", name="uq_user_catalog_filters_user_game_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    game_type: Mapped[str] = mapped_column(String(32), default=GameAccountType.MIR_TANKOV.value, nullable=False)

    sale_price_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sale_price_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    top_tank_count_min: Mapped[int | None] = mapped_column()
    top_tank_count_max: Mapped[int | None] = mapped_column()
    premium_tank_count_min: Mapped[int | None] = mapped_column()
    premium_tank_count_max: Mapped[int | None] = mapped_column()
    total_tank_count_min: Mapped[int | None] = mapped_column()
    total_tank_count_max: Mapped[int | None] = mapped_column()
    silver_amount_min: Mapped[int | None] = mapped_column(BigInteger)
    silver_amount_max: Mapped[int | None] = mapped_column(BigInteger)
    gold_amount_min: Mapped[int | None] = mapped_column(BigInteger)
    gold_amount_max: Mapped[int | None] = mapped_column(BigInteger)
    battles_count_min: Mapped[int | None] = mapped_column()
    battles_count_max: Mapped[int | None] = mapped_column()
    wins_count_min: Mapped[int | None] = mapped_column()
    wins_count_max: Mapped[int | None] = mapped_column()
    win_rate_percent_min: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    win_rate_percent_max: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    last_active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_active_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    has_tier_11: Mapped[bool | None] = mapped_column(Boolean)
    registered_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registered_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_phone_bound: Mapped[bool | None] = mapped_column(Boolean)
    is_in_clan: Mapped[bool | None] = mapped_column(Boolean)
    tank_query: Mapped[str | None] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(64))
    supplier_loaded_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supplier_loaded_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    active_sort_field: Mapped[str] = mapped_column(String(32), default=CatalogSortField.PRICE.value, nullable=False)
    price_sort_direction: Mapped[str] = mapped_column(String(4), default=SortDirection.ASC.value, nullable=False)
    last_activity_sort_direction: Mapped[str] = mapped_column(String(4), default=SortDirection.ASC.value, nullable=False)
    newest_sort_direction: Mapped[str] = mapped_column(String(4), default=SortDirection.DESC.value, nullable=False)

    user = relationship("User", back_populates="catalog_filters")

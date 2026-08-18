from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin


class BotSettings(TimestampMixin, Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    sales_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mir_tankov_sales_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tanks_blitz_sales_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    world_of_tanks_sales_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    wot_blitz_sales_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

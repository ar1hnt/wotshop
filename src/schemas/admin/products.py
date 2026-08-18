from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.i18n import Language


class AdminProductDetailSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    id: int
    supplier_item_id: int
    supplier_category_slug: str
    supplier_item_state: str
    game_type: str
    status: str
    top_tank_count: int
    premium_tank_count: int
    total_tank_count: int
    silver_amount: int
    gold_amount: int
    battles_count: int
    wins_count: int
    win_rate_percent: Decimal
    last_active_at: datetime | None
    has_tier_11: bool
    supplier_price: Decimal
    sale_price: Decimal
    registered_at: datetime | None
    is_phone_bound: bool
    is_in_clan: bool
    tanks_text: str
    region: str | None
    supplier_loaded_at: datetime | None
    created_at: datetime
    updated_at: datetime
    detail_page: int = 1
    total_detail_pages: int = 1

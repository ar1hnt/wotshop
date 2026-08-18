import re

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from src.db.models.catalog_account import CatalogSortField, GameAccountType, SortDirection
from src.i18n import Language


DATE_INPUT_FORMAT = "%d.%m.%Y"
CATALOG_PAGE_SIZE = 10
FILTER_PAGES_COUNT = 2


class CatalogFilterField(StrEnum):
    TOP_TANK_COUNT = "top_tank_count"
    PREMIUM_TANK_COUNT = "premium_tank_count"
    TOTAL_TANK_COUNT = "total_tank_count"
    SILVER_AMOUNT = "silver_amount"
    GOLD_AMOUNT = "gold_amount"
    BATTLES_COUNT = "battles_count"
    WINS_COUNT = "wins_count"
    WIN_RATE_PERCENT = "win_rate_percent"
    LAST_ACTIVE = "last_active"
    HAS_TIER_11 = "has_tier_11"
    REGISTERED_AT = "registered_at"
    IS_PHONE_BOUND = "is_phone_bound"
    IS_IN_CLAN = "is_in_clan"
    TANK_QUERY = "tank_query"
    REGION = "region"
    SUPPLIER_LOADED_AT = "supplier_loaded_at"


class CatalogBooleanChoice(StrEnum):
    YES = "yes"
    NO = "no"
    ANY = "any"


class CatalogFilterSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    game_type: GameAccountType
    top_tank_count_min: int | None = None
    top_tank_count_max: int | None = None
    premium_tank_count_min: int | None = None
    premium_tank_count_max: int | None = None
    total_tank_count_min: int | None = None
    total_tank_count_max: int | None = None
    silver_amount_min: int | None = None
    silver_amount_max: int | None = None
    gold_amount_min: int | None = None
    gold_amount_max: int | None = None
    battles_count_min: int | None = None
    battles_count_max: int | None = None
    wins_count_min: int | None = None
    wins_count_max: int | None = None
    win_rate_percent_min: Decimal | None = None
    win_rate_percent_max: Decimal | None = None
    last_active_from: datetime | None = None
    last_active_to: datetime | None = None
    has_tier_11: bool | None = None
    registered_from: datetime | None = None
    registered_to: datetime | None = None
    is_phone_bound: bool | None = None
    is_in_clan: bool | None = None
    tank_query: str | None = None
    region: str | None = None
    supplier_loaded_from: datetime | None = None
    supplier_loaded_to: datetime | None = None
    active_sort_field: CatalogSortField
    price_sort_direction: SortDirection
    last_activity_sort_direction: SortDirection
    newest_sort_direction: SortDirection


class CatalogFilterViewSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    game_type: GameAccountType
    page: int
    total_pages: int
    active_filters_count: int
    catalog_filter: CatalogFilterSchema
    flash_message: str | None = None


class CatalogAccountSummarySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    game_type: GameAccountType
    sale_price: Decimal
    top_tanks_preview: tuple[str, ...]
    last_active_at: datetime | None
    supplier_loaded_at: datetime | None


class CatalogTankSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    tank_id: int | None = None
    name: str
    short_name: str
    name_en: str | None = None
    short_name_en: str | None = None
    tier: int = 0
    is_premium: bool = False
    region: str | None = None
    image_url: str | None = None
    alt_image_url: str | None = None


class CatalogResultsPageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    game_type: GameAccountType
    page: int
    total_pages: int
    total_count: int
    active_sort_field: CatalogSortField
    price_sort_direction: SortDirection
    last_activity_sort_direction: SortDirection
    newest_sort_direction: SortDirection
    items: tuple[CatalogAccountSummarySchema, ...]


class CatalogAccountDetailSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    id: int
    game_type: GameAccountType
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
    sale_price: Decimal
    registered_at: datetime | None
    is_phone_bound: bool
    is_in_clan: bool
    tanks_text: str
    tanks_payload: tuple[CatalogTankSchema, ...] = ()
    region: str | None
    supplier_loaded_at: datetime | None
    is_favorite: bool
    detail_page: int = 1
    total_detail_pages: int = 1


class CatalogIntegerRangeInputSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_value: str
    min_value: int | None = None
    max_value: int | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "CatalogIntegerRangeInputSchema":
        if self.min_value is None and self.max_value is None:
            raise ValueError("Range value is empty.")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("Range start must be less than or equal to end.")
        return self

    @classmethod
    def from_raw(cls, raw_value: str) -> "CatalogIntegerRangeInputSchema":
        value = raw_value.strip().replace(" ", "")
        if re.fullmatch(r"\d+", value):
            parsed = cls(raw_value=raw_value, min_value=int(value), max_value=int(value))
        elif re.fullmatch(r"\d+\+", value):
            parsed = cls(raw_value=raw_value, min_value=int(value[:-1]), max_value=None)
        elif re.fullmatch(r"\d+-\d+", value):
            min_value, max_value = value.split("-", 1)
            parsed = cls(raw_value=raw_value, min_value=int(min_value), max_value=int(max_value))
        else:
            raise ValueError("Invalid integer range format.")
        return parsed


class CatalogDecimalRangeInputSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_value: str
    min_value: Decimal | None = None
    max_value: Decimal | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "CatalogDecimalRangeInputSchema":
        if self.min_value is None and self.max_value is None:
            raise ValueError("Range value is empty.")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("Range start must be less than or equal to end.")
        return self

    @classmethod
    def from_raw(cls, raw_value: str) -> "CatalogDecimalRangeInputSchema":
        value = raw_value.strip().replace(" ", "").replace(",", ".")
        decimal_pattern = r"\d+(?:\.\d{1,2})?"
        if re.fullmatch(decimal_pattern, value):
            parsed = cls(raw_value=raw_value, min_value=Decimal(value), max_value=Decimal(value))
        elif re.fullmatch(fr"{decimal_pattern}\+", value):
            parsed = cls(raw_value=raw_value, min_value=Decimal(value[:-1]), max_value=None)
        elif re.fullmatch(fr"{decimal_pattern}-{decimal_pattern}", value):
            min_value, max_value = value.split("-", 1)
            parsed = cls(raw_value=raw_value, min_value=Decimal(min_value), max_value=Decimal(max_value))
        else:
            raise ValueError("Invalid decimal range format.")
        return parsed


class CatalogDateRangeInputSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_value: str
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "CatalogDateRangeInputSchema":
        if self.date_from is None and self.date_to is None:
            raise ValueError("Date range value is empty.")
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("Date range start must be less than or equal to end.")
        return self

    @classmethod
    def from_raw(cls, raw_value: str) -> "CatalogDateRangeInputSchema":
        value = raw_value.strip().replace(" ", "")
        date_pattern = r"\d{2}\.\d{2}\.\d{4}"
        if re.fullmatch(date_pattern, value):
            parsed_date = datetime.strptime(value, DATE_INPUT_FORMAT)
            return cls(raw_value=raw_value, date_from=parsed_date, date_to=parsed_date)
        if re.fullmatch(fr"{date_pattern}\+", value):
            parsed_date = datetime.strptime(value[:-1], DATE_INPUT_FORMAT)
            return cls(raw_value=raw_value, date_from=parsed_date, date_to=None)
        if re.fullmatch(fr"{date_pattern}-{date_pattern}", value):
            raw_from, raw_to = value.split("-", 1)
            return cls(
                raw_value=raw_value,
                date_from=datetime.strptime(raw_from, DATE_INPUT_FORMAT),
                date_to=datetime.strptime(raw_to, DATE_INPUT_FORMAT),
            )
        raise ValueError("Invalid date range format.")


class CatalogLastActivityDateInputSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_value: str
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "CatalogLastActivityDateInputSchema":
        if self.date_from is None and self.date_to is None:
            raise ValueError("Date range value is empty.")
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("Date range start must be less than or equal to end.")
        return self

    @classmethod
    def from_raw(cls, raw_value: str) -> "CatalogLastActivityDateInputSchema":
        value = raw_value.strip().replace(" ", "")
        date_pattern = r"\d{2}\.\d{2}\.\d{4}"
        if re.fullmatch(date_pattern, value):
            parsed_date = datetime.strptime(value, DATE_INPUT_FORMAT)
            return cls(raw_value=raw_value, date_from=parsed_date, date_to=parsed_date)
        if re.fullmatch(fr"-{date_pattern}", value):
            parsed_date = datetime.strptime(value[1:], DATE_INPUT_FORMAT)
            return cls(raw_value=raw_value, date_from=None, date_to=parsed_date)
        if re.fullmatch(fr"{date_pattern}-{date_pattern}", value):
            raw_from, raw_to = value.split("-", 1)
            return cls(
                raw_value=raw_value,
                date_from=datetime.strptime(raw_from, DATE_INPUT_FORMAT),
                date_to=datetime.strptime(raw_to, DATE_INPUT_FORMAT),
            )
        raise ValueError("Invalid last activity date range format.")

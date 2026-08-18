import re

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.i18n import Language


CUSTOM_PERIOD_INPUT_FORMAT = "%d.%m.%Y %H:%M:%S"


class StatisticsPeriodPreset(StrEnum):
    ALL_TIME = "all_time"
    CURRENT_MONTH = "current_month"
    PREVIOUS_MONTH = "previous_month"
    WEEK = "week"
    DAY = "day"
    CUSTOM = "custom"


class StatisticsPeriodSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    preset: StatisticsPeriodPreset
    start_at: datetime | None = None
    end_at: datetime | None = None


class StatisticsSummarySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    period: StatisticsPeriodSchema
    new_users_count: int
    orders_count: int
    revenue: Decimal
    supplier_expense: Decimal
    payout_commission: Decimal
    total_expense: Decimal
    profit: Decimal
    average_order_value: Decimal
    positive_reviews_count: int
    negative_reviews_count: int


class StatisticsCustomPeriodInputSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_value: str
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at", mode="before")
    @classmethod
    def parse_datetime(cls, value: object) -> datetime:
        if isinstance(value, datetime):
            return value

        if not isinstance(value, str):
            raise TypeError("Datetime value must be a string.")

        return datetime.strptime(value.strip(), CUSTOM_PERIOD_INPUT_FORMAT)

    @model_validator(mode="after")
    def validate_period(self) -> "StatisticsCustomPeriodInputSchema":
        if self.start_at > self.end_at:
            raise ValueError("Period start must be earlier than or equal to period end.")
        return self

    @classmethod
    def from_raw(cls, raw_value: str) -> "StatisticsCustomPeriodInputSchema":
        normalized = " ".join(raw_value.strip().split())
        parts = re.split(r"\s*-\s*", normalized, maxsplit=1)
        if len(parts) != 2:
            raise ValueError("Invalid custom period format.")

        return cls.model_validate(
            {
                "raw_value": raw_value,
                "start_at": parts[0],
                "end_at": parts[1],
            }
        )

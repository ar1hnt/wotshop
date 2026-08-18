from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.i18n import Language


class AdminUserSummarySchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    bot_user_id: int
    telegram_id: int
    username: str
    first_name: str | None
    last_name: str | None
    balance: Decimal
    purchases_count: int
    total_spent: Decimal
    created_at: datetime
    updated_at: datetime


class NewUserNotificationSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    bot_user_id: int
    telegram_id: int
    username: str


class BroadcastDraftSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    html_text: str
    photo_file_id: str | None


class BroadcastResultSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    total_users: int
    sent_count: int
    failed_count: int

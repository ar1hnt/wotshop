from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(__file__).resolve().parent
IMAGES_DIR = CONFIG_DIR / "images"
LOGS_DIR = BASE_DIR / "logs"

class Settings(BaseSettings):
    bot_token: str = Field(validation_alias="BOT_TOKEN")
    lzt_market_token: str | None = Field(default=None, validation_alias="LZT_MARKET_TOKEN")
    lzt_balance_id: int = Field(validation_alias="LZT_BALANCE_ID")
    platega_merchant_id: str | None = Field(default=None, validation_alias="PLATEGA_MERCHANT_ID")
    platega_secret: str | None = Field(default=None, validation_alias="PLATEGA_SECRET")
    platega_return_url: str | None = Field(default=None, validation_alias="PLATEGA_RETURN_URL")
    platega_failed_url: str | None = Field(default=None, validation_alias="PLATEGA_FAILED_URL")
    payment_webhook_host: str = Field(default="0.0.0.0", validation_alias="PAYMENT_WEBHOOK_HOST")
    payment_webhook_port: int = Field(default=8080, validation_alias="PAYMENT_WEBHOOK_PORT")
    payment_reservation_minutes: int = Field(default=20, validation_alias="PAYMENT_RESERVATION_MINUTES")
    database_migration_lock_timeout_seconds: int = Field(
        default=15,
        validation_alias="DATABASE_MIGRATION_LOCK_TIMEOUT_SECONDS",
    )
    database_migration_statement_timeout_seconds: int = Field(
        default=120,
        validation_alias="DATABASE_MIGRATION_STATEMENT_TIMEOUT_SECONDS",
    )
    admin_ids: tuple[int, ...] = Field(default_factory=tuple, validation_alias="ADMIN_IDS")
    support_tag_name: str = Field(validation_alias="SUPPORT_TAG_NAME")

    database_url: str = Field(validation_alias="DATABASE_URL")
    default_timezone: ZoneInfo = ZoneInfo("Europe/Moscow")

    menu_image_path: Path = IMAGES_DIR / "menu.png"
    favorites_image_path: Path = IMAGES_DIR / "favorites.png"
    profile_image_path: Path = IMAGES_DIR / "profile.png"
    reviews_image_path: Path = IMAGES_DIR / "reviews.png"
    support_image_path: Path = IMAGES_DIR / "support.png"
    info_image_path: Path = IMAGES_DIR / "info.png"
    faq_image_path: Path = IMAGES_DIR / "faq.png"
    buy_image_path: Path = IMAGES_DIR / "buy.png"
    filter_image_path: Path = IMAGES_DIR / "filter.png"
    catalog_image_path: Path = IMAGES_DIR / "catalog.png"
    account_image_path: Path = IMAGES_DIR / "account.png"
    unique_tops_path: Path = CONFIG_DIR / "unique_tops.json"
    app_log_path: Path = LOGS_DIR / "bot.log"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> tuple[int, ...]:
        if value in (None, "", ()):
            return ()

        if isinstance(value, int):
            return (value,)

        if isinstance(value, str):
            return tuple(
                int(item.strip())
                for item in value.split(",")
                if item.strip()
            )

        return tuple(int(item) for item in value)


settings = Settings()

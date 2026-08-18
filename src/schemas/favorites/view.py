from pydantic import BaseModel, ConfigDict

from src.i18n import Language
from src.schemas.catalog import CatalogAccountSummarySchema


class FavoritesPageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    page: int
    total_pages: int
    total_count: int
    items: tuple[CatalogAccountSummarySchema, ...]

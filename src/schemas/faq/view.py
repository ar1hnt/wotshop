from pydantic import BaseModel, ConfigDict, Field

from src.i18n import Language


class FaqItemSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    question_ru: str
    question_en: str
    answer_ru: str
    answer_en: str
    display_question: str
    sort_order: int


class FaqListViewSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    page: int = Field(ge=1)
    total_pages: int = Field(ge=1)
    total_items: int = Field(ge=0)
    has_previous: bool
    has_next: bool
    items: tuple[FaqItemSchema, ...]


class FaqDetailSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    language: Language
    id: int
    page: int = Field(ge=1, default=1)
    content_page: int = Field(ge=1, default=1)
    total_content_pages: int = Field(ge=1, default=1)
    question_ru: str
    question_en: str
    answer_ru: str
    answer_en: str

    @property
    def localized_question(self) -> str:
        return self.question_ru if self.language == Language.RU else self.question_en

    @property
    def localized_answer(self) -> str:
        return self.answer_ru if self.language == Language.RU else self.answer_en

    @property
    def has_previous_content_page(self) -> bool:
        return self.content_page > 1

    @property
    def has_next_content_page(self) -> bool:
        return self.content_page < self.total_content_pages

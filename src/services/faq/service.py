from html import escape

from aiogram.types import User as TelegramUser

from src.db import async_session_factory
from src.db.models.faq_entry import FaqEntry
from src.db.repositories import FaqEntryRepository, UserRepository
from src.i18n import Language, translate
from src.schemas.faq import FaqDetailSchema, FaqItemSchema, FaqListViewSchema

FAQ_PAGE_SIZE = 8
# FAQ is sent together with an image, therefore Telegram limits its caption to
# 1024 characters.  The conservative limit also leaves room for the question,
# title and page indicator after HTML escaping.
# The limit is measured after HTML escaping: an ampersand, for example, grows
# from one character to five in a Telegram caption.
FAQ_ANSWER_PAGE_SIZE = 700
FAQ_FIELD_SEQUENCE: tuple[str, ...] = ("question_ru", "answer_ru", "question_en", "answer_en")
FAQ_FIELD_LABEL_KEYS: dict[str, str] = {
    "question_ru": "admin_faq_field_question_ru",
    "question_en": "admin_faq_field_question_en",
    "answer_ru": "admin_faq_field_answer_ru",
    "answer_en": "admin_faq_field_answer_en",
}


class FaqNotFoundError(Exception):
    pass


class FaqValidationError(Exception):
    pass


class FaqService:
    async def get_public_list(self, telegram_user: TelegramUser, page: int = 1) -> FaqListViewSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            faq_repository = FaqEntryRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            language = Language(user.language)
            total_items = await faq_repository.count_all()
            total_pages = max(1, (total_items + FAQ_PAGE_SIZE - 1) // FAQ_PAGE_SIZE)
            safe_page = min(max(page, 1), total_pages)
            items = await faq_repository.get_page(
                offset=(safe_page - 1) * FAQ_PAGE_SIZE,
                limit=FAQ_PAGE_SIZE,
            )
            await session.commit()

        return FaqListViewSchema(
            language=language,
            page=safe_page,
            total_pages=total_pages,
            total_items=total_items,
            has_previous=safe_page > 1,
            has_next=total_items > safe_page * FAQ_PAGE_SIZE,
            items=tuple(_to_item_schema(item, language) for item in items),
        )

    async def get_detail(
        self,
        telegram_user: TelegramUser,
        faq_id: int,
        page: int = 1,
        content_page: int = 1,
        answer_language: Language | None = None,
    ) -> FaqDetailSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            faq_repository = FaqEntryRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            item = await faq_repository.get_by_id(faq_id)
            await session.commit()

        if item is None:
            raise FaqNotFoundError

        return _to_detail_schema(
            item,
            Language(user.language),
            page=page,
            content_page=content_page,
            answer_language=answer_language,
        )

    async def get_admin_list(self, admin_user: TelegramUser, page: int = 1) -> FaqListViewSchema:
        return await self.get_public_list(admin_user, page=page)

    async def create(
        self,
        admin_user: TelegramUser,
        *,
        page: int,
        question_ru: str,
        answer_ru: str,
        question_en: str,
        answer_en: str,
    ) -> FaqDetailSchema:
        payload = {
            "question_ru": question_ru.strip(),
            "answer_ru": answer_ru.strip(),
            "question_en": question_en.strip(),
            "answer_en": answer_en.strip(),
        }
        if any(not value for value in payload.values()):
            raise FaqValidationError

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            faq_repository = FaqEntryRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            item = await faq_repository.add(**payload)
            await session.commit()

        return _to_detail_schema(item, Language(admin.language), page=page)

    async def update_localized_field(
        self,
        admin_user: TelegramUser,
        *,
        faq_id: int,
        page: int,
        field_name: str,
        value: str,
        content_page: int = 1,
        answer_language: Language | None = None,
    ) -> FaqDetailSchema:
        normalized_value = value.strip()
        if field_name not in FAQ_FIELD_SEQUENCE or not normalized_value:
            raise FaqValidationError

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            faq_repository = FaqEntryRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            item = await faq_repository.get_by_id(faq_id)
            if item is None:
                await session.commit()
                raise FaqNotFoundError
            await faq_repository.update_localized_field(item, field_name, normalized_value)
            await session.commit()

        return _to_detail_schema(
            item,
            Language(admin.language),
            page=page,
            content_page=content_page,
            answer_language=answer_language,
        )

    async def delete(self, admin_user: TelegramUser, *, faq_id: int) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            faq_repository = FaqEntryRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            item = await faq_repository.get_by_id(faq_id)
            if item is None:
                await session.commit()
                raise FaqNotFoundError
            await faq_repository.delete(item)
            await session.commit()
        return Language(admin.language)

    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await session.commit()
        return Language(user.language)


def render_public_faq_list_text(view: FaqListViewSchema) -> str:
    lines = [translate(view.language, "menu_faq_text")]
    lines.append(translate(view.language, "faq_page_meta", page=view.page, total_pages=view.total_pages))
    lines.append(translate(view.language, "faq_total_items", count=view.total_items))
    lines.append("")
    lines.append(
        translate(view.language, "faq_list_hint")
        if view.items
        else translate(view.language, "faq_list_empty")
    )
    return "\n".join(lines)


def render_public_faq_detail_text(detail: FaqDetailSchema) -> str:
    answer_pages = _split_answer_for_caption(detail.localized_answer)
    answer = escape(answer_pages[detail.content_page - 1])
    return "\n".join(
        (
            translate(detail.language, "faq_detail_title"),
            "",
            f"<b>{escape(detail.localized_question)}</b>",
            "",
            translate(
                detail.language,
                "faq_detail_page_meta",
                page=detail.content_page,
                total_pages=detail.total_content_pages,
            ),
            "",
            answer,
        )
    )


def render_admin_faq_list_text(view: FaqListViewSchema) -> str:
    lines = [translate(view.language, "admin_faq_list_title"), ""]
    lines.append(translate(view.language, "admin_faq_page_meta", page=view.page, total_pages=view.total_pages))
    lines.append(translate(view.language, "admin_faq_total_items", count=view.total_items))
    lines.append("")
    lines.append(
        translate(view.language, "admin_faq_list_hint")
        if view.items
        else translate(view.language, "admin_faq_empty")
    )
    return "\n".join(lines)


def render_admin_faq_detail_text(detail: FaqDetailSchema) -> str:
    return "\n".join(
        (
            translate(detail.language, "admin_faq_detail_title", faq_id=detail.id),
            "",
            _render_admin_block(detail.language, "admin_faq_field_question_ru", detail.question_ru),
            "",
            _render_admin_block(detail.language, "admin_faq_field_question_en", detail.question_en),
        )
    )


def render_admin_faq_answer_text(detail: FaqDetailSchema, answer_language: Language) -> str:
    answer = detail.answer_ru if answer_language == Language.RU else detail.answer_en
    question = detail.question_ru if answer_language == Language.RU else detail.question_en
    answer_label_key = (
        "admin_faq_field_answer_ru" if answer_language == Language.RU else "admin_faq_field_answer_en"
    )
    answer_pages = _split_answer_for_caption(answer)
    return "\n".join(
        (
            translate(answer_language, "admin_faq_answer_title", faq_id=detail.id),
            "",
            _render_admin_block(answer_language, "admin_faq_field_question_ru" if answer_language == Language.RU else "admin_faq_field_question_en", question),
            "",
            translate(
                answer_language,
                "faq_detail_page_meta",
                page=detail.content_page,
                total_pages=len(answer_pages),
            ),
            "",
            _render_admin_block(answer_language, answer_label_key, answer_pages[detail.content_page - 1]),
        )
    )


def render_admin_faq_prompt_text(
    language: Language,
    *,
    mode: str,
    field_name: str,
    current_value: str | None = None,
) -> str:
    field_label = translate(language, FAQ_FIELD_LABEL_KEYS[field_name])
    prompt_key = "admin_faq_add_field_prompt" if mode == "create" else "admin_faq_edit_field_prompt"
    lines = [translate(language, prompt_key, field_label=field_label)]
    if current_value is not None:
        current_value_text = escape(current_value)
        # Editing a long answer must fit Telegram's media-caption limit too.
        if field_name.startswith("answer_"):
            current_value_text = _split_answer_for_caption(current_value)[0]
            current_value_text = escape(current_value_text)
        lines.extend(("", translate(language, "admin_faq_current_value", value=current_value_text)))
    return "\n".join(lines)


def render_admin_faq_delete_confirmation_text(language: Language, detail: FaqDetailSchema) -> str:
    return "\n".join(
        (
            translate(language, "admin_faq_delete_confirm_title"),
            "",
            f"<b>{escape(detail.localized_question)}</b>",
            "",
            translate(language, "admin_faq_delete_confirm_text"),
        )
    )


def _to_item_schema(item: FaqEntry, language: Language) -> FaqItemSchema:
    return FaqItemSchema(
        id=item.id,
        question_ru=item.question_ru,
        question_en=item.question_en,
        answer_ru=item.answer_ru,
        answer_en=item.answer_en,
        display_question=_get_localized_value(item, language, kind="question"),
        sort_order=item.sort_order,
    )


def _to_detail_schema(
    item: FaqEntry,
    language: Language,
    *,
    page: int,
    content_page: int = 1,
    answer_language: Language | None = None,
) -> FaqDetailSchema:
    localized_answer = _get_localized_value(item, answer_language or language, kind="answer")
    total_content_pages = len(_split_answer_for_caption(localized_answer))
    return FaqDetailSchema(
        language=language,
        id=item.id,
        page=page,
        content_page=min(max(content_page, 1), total_content_pages),
        total_content_pages=total_content_pages,
        question_ru=item.question_ru,
        question_en=item.question_en,
        answer_ru=item.answer_ru,
        answer_en=item.answer_en,
    )


def _get_localized_value(item: FaqEntry, language: Language, *, kind: str) -> str:
    field_name = f"{kind}_{language.value}"
    return str(getattr(item, field_name))


def _render_admin_block(language: Language, label_key: str, value: str) -> str:
    return "\n".join(
        (
            f"<b>{translate(language, label_key)}</b>",
            f"<blockquote>{escape(value)}</blockquote>",
        )
    )


def _split_answer_for_caption(answer: str) -> tuple[str, ...]:
    """Split FAQ text without cutting words; each part is escaped before output."""
    answer = answer.strip()
    if not answer:
        return ("",)

    pages: list[str] = []
    remaining = answer
    while len(escape(remaining)) > FAQ_ANSWER_PAGE_SIZE:
        split_at = _find_caption_split_point(remaining, FAQ_ANSWER_PAGE_SIZE)
        if split_at <= 0:
            split_at = 1
        pages.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    pages.append(remaining)
    return tuple(pages)


def _find_caption_split_point(text: str, limit: int) -> int:
    """Return the largest source-text prefix which fits after HTML escaping."""
    escaped_length = 0
    end = 0
    for index, char in enumerate(text, start=1):
        escaped_length += len(escape(char))
        if escaped_length > limit:
            break
        end = index

    if end == len(text):
        return end

    word_boundary = max(text.rfind("\n", 0, end + 1), text.rfind(" ", 0, end + 1))
    return word_boundary if word_boundary > 0 else end

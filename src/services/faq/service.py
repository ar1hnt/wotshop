from html import escape

from aiogram.types import User as TelegramUser

from src.db import async_session_factory
from src.db.models.faq_entry import FaqEntry
from src.db.repositories import FaqEntryRepository, UserRepository
from src.i18n import Language, translate
from src.schemas.faq import FaqDetailSchema, FaqItemSchema, FaqListViewSchema

FAQ_PAGE_SIZE = 8
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

    async def get_detail(self, telegram_user: TelegramUser, faq_id: int, page: int = 1) -> FaqDetailSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            faq_repository = FaqEntryRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            item = await faq_repository.get_by_id(faq_id)
            await session.commit()

        if item is None:
            raise FaqNotFoundError

        return _to_detail_schema(item, Language(user.language), page=page)

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

        return _to_detail_schema(item, Language(admin.language), page=page)

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
    return "\n".join(
        (
            f"<b>{escape(detail.localized_question)}</b>",
            "",
            escape(detail.localized_answer),
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
            _render_admin_block(detail.language, "admin_faq_field_answer_ru", detail.answer_ru),
            "",
            _render_admin_block(detail.language, "admin_faq_field_question_en", detail.question_en),
            "",
            _render_admin_block(detail.language, "admin_faq_field_answer_en", detail.answer_en),
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
        lines.extend(("", translate(language, "admin_faq_current_value", value=escape(current_value))))
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


def _to_detail_schema(item: FaqEntry, language: Language, *, page: int) -> FaqDetailSchema:
    return FaqDetailSchema(
        language=language,
        id=item.id,
        page=page,
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

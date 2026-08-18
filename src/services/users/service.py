import asyncio
import logging

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, Message
from aiogram.types import User as TelegramUser

from src.config import settings
from src.db import async_session_factory
from src.db.repositories import UserRepository
from src.i18n import Language, translate
from src.schemas.admin import (
    AdminUserSummarySchema,
    BroadcastDraftSchema,
    BroadcastResultSchema,
    NewUserNotificationSchema,
)

logger = logging.getLogger(__name__)


class UserLookupError(Exception):
    pass


class BalanceValidationError(Exception):
    pass


class BroadcastValidationError(Exception):
    pass


class UserService:
    async def ensure_user(self, telegram_user: TelegramUser) -> tuple[AdminUserSummarySchema, bool]:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user, is_created = await user_repository.get_or_create_from_telegram_with_flag(telegram_user)
            purchases_count, total_spent = await user_repository.get_user_stats_summary(user.id)
            await session.commit()

        return self._to_summary(user, purchases_count, total_spent), is_created

    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        summary, _ = await self.ensure_user(telegram_user)
        return summary.language

    async def get_total_users_count(self) -> int:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            count = await user_repository.count_all()
            await session.commit()
        return count

    async def find_user_by_identifier(
        self,
        admin_user: TelegramUser,
        *,
        identifier_type: str,
        identifier_value: str,
    ) -> AdminUserSummarySchema:
        try:
            numeric_identifier = int(identifier_value.strip())
        except ValueError as error:
            raise UserLookupError from error

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            admin, _ = await user_repository.get_or_create_from_telegram_with_flag(admin_user)
            user = await user_repository.search_by_bot_or_telegram_id(
                identifier_type=identifier_type,
                identifier_value=numeric_identifier,
            )

            if user is None:
                await session.commit()
                raise UserLookupError

            purchases_count, total_spent = await user_repository.get_user_stats_summary(user.id)
            await session.commit()

        return self._to_summary(user, purchases_count, total_spent, language=Language(admin.language))

    async def update_user_balance(
        self,
        admin_user: TelegramUser,
        *,
        target_user_id: int,
        balance_value: str,
    ) -> AdminUserSummarySchema:
        try:
            balance = Decimal(balance_value.strip())
        except (InvalidOperation, ValueError) as error:
            raise BalanceValidationError from error

        if balance < 0:
            raise BalanceValidationError

        normalized = balance.quantize(Decimal("0.01"))

        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            admin, _ = await user_repository.get_or_create_from_telegram_with_flag(admin_user)
            admin_language = Language(admin.language)
            user = await user_repository.get_by_id(target_user_id)
            if user is None:
                await session.commit()
                raise UserLookupError

            await user_repository.update_balance(user, normalized)
            purchases_count, total_spent = await user_repository.get_user_stats_summary(user.id)
            await session.refresh(user)
            await session.commit()

        logger.info(
            "Updated user balance target_user_id=%s admin_telegram_id=%s balance=%s",
            target_user_id,
            admin_user.id,
            normalized,
        )
        return self._to_summary(user, purchases_count, total_spent, language=admin_language)

    async def build_broadcast_draft(self, admin_user: TelegramUser, message: Message) -> BroadcastDraftSchema:
        language = await self.get_user_language(admin_user)
        html_text = (message.html_text or "").strip()
        if not html_text:
            raise BroadcastValidationError

        photo_file_id = message.photo[-1].file_id if message.photo else None
        return BroadcastDraftSchema(
            language=language,
            html_text=html_text,
            photo_file_id=photo_file_id,
        )

    async def send_broadcast(self, bot: Bot, draft: BroadcastDraftSchema) -> BroadcastResultSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            telegram_ids = await user_repository.list_telegram_ids()
            await session.commit()

        sent_count = 0
        failed_count = 0

        for telegram_id in telegram_ids:
            try:
                if draft.photo_file_id is None:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=draft.html_text,
                    )
                else:
                    await bot.send_photo(
                        chat_id=telegram_id,
                        photo=draft.photo_file_id,
                        caption=draft.html_text,
                    )
                sent_count += 1
            except TelegramAPIError:
                failed_count += 1
            await asyncio.sleep(0.5)

        logger.info(
            "Broadcast finished total_users=%s sent=%s failed=%s",
            len(telegram_ids),
            sent_count,
            failed_count,
        )
        return BroadcastResultSchema(
            language=draft.language,
            total_users=len(telegram_ids),
            sent_count=sent_count,
            failed_count=failed_count,
        )

    async def export_users_xlsx(self, admin_user: TelegramUser) -> tuple[Language, BufferedInputFile]:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            admin, _ = await user_repository.get_or_create_from_telegram_with_flag(admin_user)
            users = await user_repository.list_all()
            rows = []
            for user in users:
                purchases_count, total_spent = await user_repository.get_user_stats_summary(user.id)
                rows.append(
                    (
                        str(user.id),
                        str(user.telegram_id),
                        user.username or "",
                        user.first_name or "",
                        user.last_name or "",
                        user.language,
                        _format_money(user.balance),
                        str(purchases_count),
                        _format_money(total_spent),
                        _format_datetime(user.created_at),
                        _format_datetime(user.updated_at),
                    )
                )
            await session.commit()

        workbook_bytes = _build_users_xlsx(rows)
        filename = f"wotshop-users-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.xlsx"
        return Language(admin.language), BufferedInputFile(workbook_bytes, filename=filename)

    async def notify_admins_about_new_user(self, bot: Bot, summary: AdminUserSummarySchema) -> None:
        notification = NewUserNotificationSchema(
            bot_user_id=summary.bot_user_id,
            telegram_id=summary.telegram_id,
            username=summary.username,
        )

        for admin_id in settings.admin_ids:
            try:
                admin_language = await self.get_language_by_telegram_id(admin_id)
                await bot.send_message(
                    chat_id=admin_id,
                    text=render_new_user_notification_text(admin_language, notification),
                )
            except TelegramAPIError:
                logger.warning(
                    "Failed to notify admin telegram_id=%s about new user bot_user_id=%s",
                    admin_id,
                    notification.bot_user_id,
                )

    async def get_language_by_telegram_id(self, telegram_id: int) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_by_telegram_id(telegram_id)
            await session.commit()

        if user is None:
            return Language.RU

        return Language(user.language)

    @staticmethod
    def _to_summary(
        user,
        purchases_count: int,
        total_spent: Decimal,
        *,
        language: Language | None = None,
    ) -> AdminUserSummarySchema:
        username = f"@{user.username}" if user.username else "-"
        return AdminUserSummarySchema(
            language=language or Language(user.language),
            bot_user_id=user.id,
            telegram_id=user.telegram_id,
            username=username,
            first_name=user.first_name,
            last_name=user.last_name,
            balance=user.balance,
            purchases_count=purchases_count,
            total_spent=total_spent,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


def render_new_user_notification_text(language: Language, notification: NewUserNotificationSchema) -> str:
    return "\n".join(
        (
            translate(language, "admin_new_user_title"),
            "",
            translate(language, "admin_user_bot_id", bot_user_id=notification.bot_user_id),
            translate(language, "admin_user_tg_id", telegram_id=notification.telegram_id),
            translate(language, "admin_user_username", username=escape(notification.username)),
        )
    )


def render_admin_users_menu_text(language: Language, total_users: int) -> str:
    return "\n".join(
        (
            translate(language, "admin_users_menu_title"),
            "",
            translate(language, "admin_users_total_count", count=total_users),
            "",
            translate(language, "admin_users_menu_choice"),
        )
    )


def render_broadcast_prompt_text(language: Language) -> str:
    return translate(language, "admin_broadcast_prompt")


def render_broadcast_confirmation_text(language: Language, draft: BroadcastDraftSchema) -> str:
    return "\n".join(
        (
            translate(language, "admin_broadcast_confirm_title"),
            "",
            translate(language, "admin_broadcast_confirm_text_present"),
            translate(
                language,
                "admin_broadcast_confirm_image_present",
                has_image=translate(language, "yes") if draft.photo_file_id else translate(language, "no"),
            ),
        )
    )


def render_broadcast_result_text(result: BroadcastResultSchema) -> str:
    return "\n".join(
        (
            translate(result.language, "admin_broadcast_result_title"),
            "",
            translate(result.language, "admin_broadcast_total_users", count=result.total_users),
            translate(result.language, "admin_broadcast_sent_count", count=result.sent_count),
            translate(result.language, "admin_broadcast_failed_count", count=result.failed_count),
        )
    )


def render_user_lookup_type_text(language: Language) -> str:
    return translate(language, "admin_user_lookup_type_title")


def render_user_lookup_prompt_text(language: Language, identifier_type: str) -> str:
    identifier_label_key = (
        "admin_user_identifier_bot_id"
        if identifier_type == "bot_id"
        else "admin_user_identifier_tg_id"
    )
    return translate(
        language,
        "admin_user_lookup_prompt",
        identifier=translate(language, identifier_label_key),
    )


def render_user_detail_text(user: AdminUserSummarySchema) -> str:
    return "\n".join(
        (
            translate(user.language, "admin_user_detail_title"),
            "",
            translate(user.language, "admin_user_bot_id", bot_user_id=user.bot_user_id),
            translate(user.language, "admin_user_tg_id", telegram_id=user.telegram_id),
            translate(user.language, "admin_user_username", username=escape(user.username)),
            translate(user.language, "admin_user_first_name", value=escape(user.first_name or "-")),
            translate(user.language, "admin_user_last_name", value=escape(user.last_name or "-")),
            translate(user.language, "admin_user_language_value", value=user.language.value),
            translate(user.language, "admin_user_balance_value", balance=_format_money(user.balance)),
            translate(user.language, "admin_user_orders_count_value", count=user.purchases_count),
            translate(user.language, "admin_user_total_spent_value", amount=_format_money(user.total_spent)),
            "",
            translate(user.language, "admin_user_message_edit"),
        )
    )


def render_balance_prompt_text(language: Language, user: AdminUserSummarySchema) -> str:
    return "\n".join(
        (
            translate(language, "admin_user_balance_prompt"),
            "",
            translate(language, "admin_user_bot_id", bot_user_id=user.bot_user_id),
            translate(language, "admin_user_balance_value", balance=_format_money(user.balance)),
        )
    )


def render_balance_updated_text(user: AdminUserSummarySchema) -> str:
    return translate(
        user.language,
        "admin_user_balance_updated",
        balance=_format_money(user.balance),
    )


def _format_money(amount: Decimal) -> str:
    normalized = amount.quantize(Decimal("0.01"))
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{normalized:.2f}"


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")


def _build_users_xlsx(rows: list[tuple[str, ...]]) -> bytes:
    headers = (
        "Bot User ID",
        "Telegram ID",
        "Username",
        "First Name",
        "Last Name",
        "Language",
        "Balance",
        "Purchases Count",
        "Total Spent",
        "Created At",
        "Updated At",
    )
    sheet_rows = [headers, *rows]
    worksheet_xml = _build_worksheet_xml(sheet_rows)

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", _ROOT_RELS_XML)
        archive.writestr("docProps/app.xml", _APP_XML)
        archive.writestr("docProps/core.xml", _CORE_XML)
        archive.writestr("xl/workbook.xml", _WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS_XML)
        archive.writestr("xl/styles.xml", _STYLES_XML)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)

    return buffer.getvalue()


def _build_worksheet_xml(rows: list[tuple[str, ...]]) -> str:
    row_chunks: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cell_chunks = []
        for column_index, value in enumerate(row, start=1):
            cell_reference = f"{_column_name(column_index)}{row_index}"
            safe_value = escape(value)
            cell_chunks.append(
                f'<c r="{cell_reference}" t="inlineStr"><is><t xml:space="preserve">{safe_value}</t></is></c>'
            )
        row_chunks.append(f'<row r="{row_index}">{"".join(cell_chunks)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_chunks)}</sheetData>'
        "</worksheet>"
    )


def _column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


_CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""


_ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


_WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Users" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""


_WORKBOOK_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""


_STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf/></cellStyleXfs>
  <cellXfs count="1"><xf xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


_APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>WotShop Bot</Application>
</Properties>
"""


_CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>WotShop Bot</dc:creator>
  <cp:lastModifiedBy>WotShop Bot</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2026-01-01T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-01T00:00:00Z</dcterms:modified>
</cp:coreProperties>
"""

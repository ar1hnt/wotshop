import logging

from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile
from aiogram.types import User as TelegramUser

from src.config import settings
from src.db import async_session_factory
from src.db.models.catalog_account import CatalogAccount, GameAccountType
from src.db.models.transaction import TransactionStatus, TransactionType
from src.db.repositories import CatalogAccountRepository, TransactionRepository, UserRepository
from src.i18n import Language, translate
from src.schemas.admin import (
    AdminTransactionDetailSchema,
    AdminTransactionListItemSchema,
    AdminTransactionPageSchema,
)

logger = logging.getLogger(__name__)

TRANSACTIONS_PAGE_SIZE = 10


class TransactionNotFoundError(Exception):
    pass


class TransactionService:
    async def notify_admins_about_purchase_fulfillment_error(
        self,
        bot: Bot,
        *,
        transaction_id: int,
        error: Exception,
    ) -> None:
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            users = UserRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            if transaction is None:
                await session.commit()
                return
            account = await CatalogAccountRepository(session).get_by_id(transaction.catalog_account_id or 0)
            admin_languages = {
                admin_id: await _get_admin_language(users, admin_id)
                for admin_id in settings.admin_ids
            }
            await session.commit()

        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    render_admin_account_operation_error_text(
                        admin_languages.get(admin_id, Language.RU),
                        user_id=transaction.user.id,
                        telegram_id=transaction.user.telegram_id,
                        username=_normalize_username(transaction.user.username),
                        account_id=transaction.catalog_account_id or 0,
                        supplier_item_id=account.supplier_item_id if account is not None else None,
                        game_type=account.game_type if account is not None else None,
                        sale_price=account.sale_price if account is not None else None,
                        supplier_price=account.supplier_price if account is not None else None,
                        operation="purchase",
                        error=error,
                    ),
                )
            except TelegramAPIError:
                logger.warning("Failed to notify admin about purchase fulfillment error transaction_id=%s", transaction_id)

    async def notify_admins_about_account_operation_error(
        self,
        bot: Bot,
        *,
        telegram_user: TelegramUser,
        account_id: int,
        operation: str,
        error: Exception,
    ) -> None:
        async with async_session_factory() as session:
            users = UserRepository(session)
            accounts = CatalogAccountRepository(session)
            user = await users.get_or_create_from_telegram(telegram_user)
            account = await accounts.get_by_id(account_id)
            supplier_item_id = account.supplier_item_id if account is not None else None
            game_type = account.game_type if account is not None else None
            sale_price = account.sale_price if account is not None else None
            supplier_price = account.supplier_price if account is not None else None
            bot_user_id = user.id
            user_telegram_id = user.telegram_id
            username = _normalize_username(user.username)
            admin_languages = {
                admin_id: await _get_admin_language(users, admin_id)
                for admin_id in settings.admin_ids
            }
            await session.commit()

        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    render_admin_account_operation_error_text(
                        admin_languages.get(admin_id, Language.RU),
                        user_id=bot_user_id,
                        telegram_id=user_telegram_id,
                        username=username,
                        account_id=account_id,
                        supplier_item_id=supplier_item_id,
                        game_type=game_type,
                        sale_price=sale_price,
                        supplier_price=supplier_price,
                        operation=operation,
                        error=error,
                    ),
                )
            except TelegramAPIError:
                logger.warning("Failed to notify admin telegram_id=%s about account operation error", admin_id)

    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await session.commit()
        return Language(user.language)

    async def get_transactions_menu_context(self, admin_user: TelegramUser) -> tuple[Language, int, int]:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            transaction_repository = TransactionRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            completed_count = await transaction_repository.count_by_status(TransactionStatus.COMPLETED)
            pending_count = await transaction_repository.count_by_status(TransactionStatus.PENDING)
            await session.commit()
        return Language(admin.language), completed_count, pending_count

    async def get_page(
        self,
        admin_user: TelegramUser,
        *,
        status: TransactionStatus,
        page: int,
    ) -> AdminTransactionPageSchema:
        safe_page = max(page, 1)
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            transaction_repository = TransactionRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            transactions, total_count = await transaction_repository.get_page_by_status(
                status=status,
                page=safe_page,
                page_size=TRANSACTIONS_PAGE_SIZE,
            )
            await session.commit()

        total_pages = max(1, (total_count + TRANSACTIONS_PAGE_SIZE - 1) // TRANSACTIONS_PAGE_SIZE)
        normalized_page = min(safe_page, total_pages)
        if normalized_page != safe_page:
            return await self.get_page(admin_user, status=status, page=normalized_page)

        return AdminTransactionPageSchema(
            language=Language(admin.language),
            status=status,
            page=normalized_page,
            total_pages=total_pages,
            total_count=total_count,
            items=[
                AdminTransactionListItemSchema(
                    id=transaction.id,
                    user_id=transaction.user.id,
                    telegram_id=transaction.user.telegram_id,
                    username=_normalize_username(transaction.user.username),
                    transaction_type=TransactionType(transaction.type),
                    status=TransactionStatus(transaction.status),
                    amount=_to_decimal(transaction.amount),
                    currency=transaction.currency,
                    description=transaction.description,
                    created_at=transaction.created_at,
                )
                for transaction in transactions
            ],
        )

    async def get_detail(
        self,
        admin_user: TelegramUser,
        *,
        transaction_id: int,
        expected_status: TransactionStatus | None = None,
    ) -> AdminTransactionDetailSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            transaction_repository = TransactionRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            transaction = await transaction_repository.get_by_id(transaction_id)
            await session.commit()

        if transaction is None:
            raise TransactionNotFoundError

        status = TransactionStatus(transaction.status)
        if expected_status is not None and status != expected_status:
            if not (
                expected_status == TransactionStatus.PENDING
                and status in {TransactionStatus.PROCESSING, TransactionStatus.FAILED}
            ):
                raise TransactionNotFoundError

        return AdminTransactionDetailSchema(
            language=Language(admin.language),
            id=transaction.id,
            catalog_account_id=transaction.catalog_account_id,
            user_id=transaction.user.id,
            telegram_id=transaction.user.telegram_id,
            username=_normalize_username(transaction.user.username),
            order_id=transaction.order_id,
            transaction_type=TransactionType(transaction.type),
            status=status,
            amount=_to_decimal(transaction.amount),
            currency=transaction.currency,
            description=transaction.description,
            provider_name=transaction.provider_name,
            provider_transaction_id=transaction.provider_transaction_id,
            failure_reason=transaction.failure_reason,
            created_at=transaction.created_at,
            updated_at=transaction.updated_at,
            completed_at=transaction.completed_at,
            canceled_at=transaction.canceled_at,
        )

    async def export_completed_xlsx(self, admin_user: TelegramUser) -> tuple[Language, BufferedInputFile]:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            transaction_repository = TransactionRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            transactions = await transaction_repository.list_all_by_status(TransactionStatus.COMPLETED)
            await session.commit()

        rows = [
            (
                str(transaction.id),
                str(transaction.user.id),
                str(transaction.user.telegram_id),
                _normalize_username(transaction.user.username),
                _transaction_type_label(Language(admin.language), TransactionType(transaction.type)),
                _transaction_status_label(Language(admin.language), TransactionStatus(transaction.status)),
                _format_money(_to_decimal(transaction.amount)),
                transaction.currency,
                str(transaction.order_id or ""),
                transaction.provider_name or "",
                transaction.provider_transaction_id or "",
                transaction.description or "",
                _format_datetime(transaction.created_at),
                _format_datetime(transaction.completed_at),
                _format_datetime(transaction.updated_at),
            )
            for transaction in transactions
        ]

        workbook_bytes = _build_transactions_xlsx(rows)
        filename = f"wotshop-transactions-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.xlsx"
        return Language(admin.language), BufferedInputFile(workbook_bytes, filename=filename)

    async def notify_admins_about_started_transaction(self, bot: Bot, transaction_id: int) -> None:
        await self._notify_admins_about_transaction(bot, transaction_id, event="started")

    async def notify_admins_about_canceled_transaction(self, bot: Bot, transaction_id: int) -> None:
        await self._notify_admins_about_transaction(bot, transaction_id, event="canceled")

    async def notify_admins_about_failed_transaction(self, bot: Bot, transaction_id: int) -> None:
        await self._notify_admins_about_transaction(bot, transaction_id, event="failed")

    async def notify_admins_about_completed_transaction(self, bot: Bot, transaction_id: int) -> None:
        await self._notify_admins_about_transaction(bot, transaction_id, event="completed")

    async def _notify_admins_about_transaction(self, bot: Bot, transaction_id: int, *, event: str) -> None:
        async with async_session_factory() as session:
            transaction_repository = TransactionRepository(session)
            user_repository = UserRepository(session)
            transaction = await transaction_repository.get_by_id(transaction_id)
            if transaction is None:
                await session.commit()
                return
            notification = _to_detail_schema(transaction)
            account = await CatalogAccountRepository(session).get_by_id(transaction.catalog_account_id or 0)
            supplier_item_id = account.supplier_item_id if account is not None else None
            admin_languages = {
                admin_id: await _get_admin_language(user_repository, admin_id)
                for admin_id in settings.admin_ids
            }
            await session.commit()

        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=render_admin_completed_transaction_notification_text(
                        admin_languages.get(admin_id, Language.RU),
                        notification,
                        event=event,
                        supplier_item_id=supplier_item_id,
                    ),
                )
            except TelegramAPIError:
                logger.warning(
                    "Failed to notify admin telegram_id=%s about %s transaction_id=%s",
                    admin_id,
                    event,
                    transaction_id,
                )


def render_admin_transactions_menu_text(language: Language, *, completed_count: int, pending_count: int) -> str:
    return "\n".join(
        (
            translate(language, "admin_transactions_menu_title"),
            "",
            translate(language, "admin_transactions_completed_count", count=completed_count),
            translate(language, "admin_transactions_pending_count", count=pending_count),
        )
    )


def render_admin_transactions_page_text(page_data: AdminTransactionPageSchema) -> str:
    title_key = (
        "admin_transactions_completed_title"
        if page_data.status == TransactionStatus.COMPLETED
        else "admin_transactions_pending_title"
    )
    lines = [
        translate(page_data.language, title_key),
        "",
        translate(page_data.language, "admin_transactions_total_count", count=page_data.total_count),
        translate(
            page_data.language,
            "admin_transactions_page_meta",
            page=page_data.page,
            total_pages=page_data.total_pages,
        ),
    ]
    if not page_data.items:
        lines.extend(("", translate(page_data.language, "admin_transactions_empty")))
    return "\n".join(lines)


def render_admin_transaction_lookup_prompt_text(language: Language) -> str:
    return translate(language, "admin_transaction_lookup_prompt")


def render_admin_transaction_detail_text(detail: AdminTransactionDetailSchema) -> str:
    return "\n".join(
        (
            translate(detail.language, "admin_transaction_detail_title", transaction_id=detail.id),
            "",
            translate(
                detail.language,
                "admin_transaction_type",
                value=_transaction_type_label(detail.language, detail.transaction_type),
            ),
            translate(
                detail.language,
                "admin_transaction_status",
                value=_transaction_status_label(detail.language, detail.status),
            ),
            translate(
                detail.language,
                "admin_transaction_amount",
                value=_format_money(detail.amount),
                currency=detail.currency,
            ),
            # translate(detail.language, "admin_transaction_order_id", value=detail.order_id or "-"),
            "",
            translate(detail.language, "admin_transaction_user_bot_id", value=detail.user_id),
            translate(detail.language, "admin_transaction_user_tg_id", value=detail.telegram_id),
            translate(detail.language, "admin_transaction_user_username", value=escape(detail.username)),
            "",
            translate(detail.language, "admin_transaction_provider_name", value=escape(detail.provider_name or "-")),
            translate(
                detail.language,
                "admin_transaction_provider_id",
                value=escape(detail.provider_transaction_id or "-"),
            ),
            translate(detail.language, "admin_transaction_description", value=escape(detail.description or "-")),
            translate(detail.language, "admin_transaction_failure_reason", value=escape(detail.failure_reason or "-")),
            "",
            translate(detail.language, "admin_transaction_created_at", value=_format_datetime(detail.created_at)),
            translate(detail.language, "admin_transaction_completed_at", value=_format_datetime(detail.completed_at)),
            translate(detail.language, "admin_transaction_canceled_at", value=_format_datetime(detail.canceled_at)),
            translate(detail.language, "admin_transaction_updated_at", value=_format_datetime(detail.updated_at)),
        )
    )


def render_admin_transaction_cancel_placeholder_text(language: Language) -> str:
    return translate(language, "admin_transaction_cancel_placeholder")


def render_admin_completed_transaction_notification_text(
    language: Language,
    detail: AdminTransactionDetailSchema,
    *,
    event: str = "completed",
    supplier_item_id: int | None = None,
) -> str:
    title_key = f"admin_transaction_{event}_title"
    lines = [
        translate(language, title_key, transaction_id=detail.id),
        "",
        translate(language, "admin_transaction_type", value=_transaction_type_label(language, detail.transaction_type)),
        translate(language, "admin_transaction_amount", value=_format_money(detail.amount), currency=detail.currency),
    ]
    if detail.provider_transaction_id:
        lines.append(translate(language, "admin_transaction_provider_transaction_id", value=detail.provider_transaction_id))
    lines.extend(
        (
            "",
            translate(language, "admin_transaction_user_name", value=escape(detail.username)),
            translate(language, "admin_transaction_user_telegram_id", value=detail.telegram_id),
            translate(language, "admin_transaction_user_id", value=detail.user_id),
        )
    )
    if detail.catalog_account_id is not None:
        lines.append(translate(language, "admin_transaction_product", value=detail.catalog_account_id))
    if supplier_item_id is not None:
        lines.append(translate(language, "admin_transaction_supplier_link", value=supplier_item_id))
    if event == "canceled":
        lines.extend(("", translate(language, "admin_transaction_canceled_reason")))
    elif event == "failed":
        lines.extend(
            (
                "",
                translate(
                    language,
                    "admin_transaction_failed_reason",
                    reason=escape(detail.failure_reason or "-"),
                ),
            )
        )
    return "\n".join(lines)


def render_admin_account_operation_error_text(
    language: Language,
    *,
    user_id: int,
    telegram_id: int,
    username: str,
    account_id: int,
    supplier_item_id: int | None,
    game_type: str | None,
    sale_price: Decimal | None,
    supplier_price: Decimal | None,
    operation: str,
    error: Exception,
) -> str:
    operation_key = "admin_account_operation_purchase" if operation == "purchase" else "admin_account_operation_refresh"
    lines = [
        translate(language, "admin_account_operation_error_title"),
        "",
        translate(language, "admin_account_operation", value=translate(language, operation_key)),
        "",
        translate(language, "admin_transaction_user_name", value=escape(username)),
        translate(language, "admin_transaction_user_telegram_id", value=telegram_id),
        translate(language, "admin_transaction_user_id", value=user_id),
        "",
        translate(language, "admin_transaction_product", value=account_id),
    ]
    if supplier_item_id is not None:
        lines.append(translate(language, "admin_transaction_supplier_link", value=supplier_item_id))
    if game_type is not None:
        lines.append(
            translate(
                language,
                "admin_transaction_game_type",
                value=_game_type_label(language, game_type),
            )
        )
    if sale_price is not None:
        lines.append(translate(language, "admin_product_sale_price", value=_format_money(_to_decimal(sale_price))))
    if supplier_price is not None:
        lines.append(translate(language, "admin_product_supplier_price", value=_format_money(_to_decimal(supplier_price))))
    lines.extend(
        (
            "",
            translate(language, "admin_account_error_type", value=type(_root_error(error)).__name__),
            translate(language, "admin_account_error_reason", value=escape(str(_root_error(error))[:1000] or "-")),
        )
    )
    return "\n".join(lines)


def _root_error(error: Exception) -> Exception:
    current = error
    while isinstance(current.__cause__, Exception):
        current = current.__cause__
    return current


def _game_type_label(language: Language, game_type: str) -> str:
    key_by_type = {
        GameAccountType.MIR_TANKOV.value: "catalog_game_type_mir_tankov",
        GameAccountType.TANKS_BLITZ.value: "catalog_game_type_tanks_blitz",
        GameAccountType.WORLD_OF_TANKS.value: "catalog_game_type_world_of_tanks",
        GameAccountType.WOT_BLITZ.value: "catalog_game_type_wot_blitz",
    }
    return translate(language, key_by_type.get(game_type, "catalog_game_type_mir_tankov"))


def _to_detail_schema(transaction) -> AdminTransactionDetailSchema:
    return AdminTransactionDetailSchema(
        language=Language.RU,
        id=transaction.id,
        catalog_account_id=transaction.catalog_account_id,
        user_id=transaction.user.id,
        telegram_id=transaction.user.telegram_id,
        username=_normalize_username(transaction.user.username),
        order_id=transaction.order_id,
        transaction_type=TransactionType(transaction.type),
        status=TransactionStatus(transaction.status),
        amount=_to_decimal(transaction.amount),
        currency=transaction.currency,
        description=transaction.description,
        provider_name=transaction.provider_name,
        provider_transaction_id=transaction.provider_transaction_id,
        failure_reason=transaction.failure_reason,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
        completed_at=transaction.completed_at,
        canceled_at=transaction.canceled_at,
    )


def build_admin_transaction_button_text(item: AdminTransactionListItemSchema, language: Language) -> str:
    return (
        f"#{item.id} | {_transaction_type_label(language, item.transaction_type)} | "
        f"{_format_money(item.amount)} {item.currency} | ID {item.user_id}"
    )


async def _get_admin_language(user_repository: UserRepository, telegram_id: int) -> Language:
    admin = await user_repository.get_by_telegram_id(telegram_id)
    if admin is None:
        return Language.RU
    return Language(admin.language)


def _transaction_type_label(language: Language, transaction_type: TransactionType) -> str:
    key_map = {
        TransactionType.PURCHASE: "admin_transaction_type_purchase",
        TransactionType.TOP_UP: "admin_transaction_type_top_up",
    }
    return translate(language, key_map[transaction_type])


def _transaction_status_label(language: Language, status: TransactionStatus) -> str:
    key_map = {
        TransactionStatus.PENDING: "admin_transaction_status_pending",
        TransactionStatus.PROCESSING: "admin_transaction_status_pending",
        TransactionStatus.COMPLETED: "admin_transaction_status_completed",
        TransactionStatus.CANCELED: "admin_transaction_status_canceled",
        TransactionStatus.FAILED: "admin_transaction_status_failed",
    }
    return translate(language, key_map[status])


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _format_money(amount: Decimal) -> str:
    normalized = amount.quantize(Decimal("0.01"))
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{normalized:.2f}"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")


def _normalize_username(username: str | None) -> str:
    return f"@{username}" if username else translate(Language.RU, "unknown_username")


def _build_transactions_xlsx(rows: list[tuple[str, ...]]) -> bytes:
    headers = (
        "ID",
        "Bot User ID",
        "Telegram ID",
        "Username",
        "Type",
        "Status",
        "Amount",
        "Currency",
        "Order ID",
        "Provider Name",
        "Provider Transaction ID",
        "Description",
        "Created At",
        "Completed At",
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

_APP_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
    <Application>Codex</Application>
</Properties>
"""

_CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <dc:creator>Codex</dc:creator>
    <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
</cp:coreProperties>
"""

_WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <sheets>
        <sheet name="Transactions" sheetId="1" r:id="rId1"/>
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
    <fonts count="1">
        <font>
            <sz val="11"/>
            <name val="Calibri"/>
        </font>
    </fonts>
    <fills count="1">
        <fill><patternFill patternType="none"/></fill>
    </fills>
    <borders count="1">
        <border/>
    </borders>
    <cellStyleXfs count="1">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
    </cellStyleXfs>
    <cellXfs count="1">
        <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    </cellXfs>
</styleSheet>
"""

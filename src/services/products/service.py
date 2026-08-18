from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from aiogram.types import BufferedInputFile
from aiogram.types import User as TelegramUser

from src.config import settings
from src.db import async_session_factory
from src.db.repositories import CatalogAccountRepository, UserRepository
from src.i18n import Language, translate
from src.schemas.admin.products import AdminProductDetailSchema


class ProductNotFoundError(Exception):
    pass


class ProductValidationError(Exception):
    pass


class ProductService:
    async def get_user_language(self, telegram_user: TelegramUser) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            user = await user_repository.get_or_create_from_telegram(telegram_user)
            await session.commit()
        return Language(user.language)

    async def get_total_products_count(self) -> int:
        async with async_session_factory() as session:
            account_repository = CatalogAccountRepository(session)
            count = await account_repository.count_all()
            await session.commit()
        return count

    async def get_product_detail(
        self,
        admin_user: TelegramUser,
        *,
        product_id: int,
        detail_page: int = 1,
    ) -> AdminProductDetailSchema:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            account_repository = CatalogAccountRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            account = await account_repository.get_by_id(product_id)
            await session.commit()

        if account is None:
            raise ProductNotFoundError

        detail = AdminProductDetailSchema(
            language=Language(admin.language),
            id=account.id,
            supplier_item_id=account.supplier_item_id,
            supplier_category_slug=account.supplier_category_slug,
            supplier_item_state=account.supplier_item_state,
            game_type=account.game_type,
            status=account.status,
            top_tank_count=account.top_tank_count,
            premium_tank_count=account.premium_tank_count,
            total_tank_count=account.total_tank_count,
            silver_amount=account.silver_amount,
            gold_amount=account.gold_amount,
            battles_count=account.battles_count,
            wins_count=account.wins_count,
            win_rate_percent=Decimal(str(account.win_rate_percent)),
            last_active_at=account.last_active_at,
            has_tier_11=account.has_tier_11,
            supplier_price=Decimal(str(account.supplier_price)),
            sale_price=Decimal(str(account.sale_price)),
            registered_at=account.registered_at,
            is_phone_bound=account.is_phone_bound,
            is_in_clan=account.is_in_clan,
            tanks_text=account.tanks_text,
            region=account.region,
            supplier_loaded_at=account.supplier_loaded_at,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )
        total_detail_pages = len(_build_admin_product_detail_pages(detail))
        safe_detail_page = min(max(detail_page, 1), total_detail_pages)
        return detail.model_copy(update={"detail_page": safe_detail_page, "total_detail_pages": total_detail_pages})

    async def delete_product(self, admin_user: TelegramUser, *, product_id: int) -> Language:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            account_repository = CatalogAccountRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            account = await account_repository.get_by_id(product_id)
            if account is None:
                await session.commit()
                raise ProductNotFoundError
            await account_repository.delete(account)
            await session.commit()
        return Language(admin.language)

    async def export_products_xlsx(self, admin_user: TelegramUser) -> tuple[Language, BufferedInputFile]:
        async with async_session_factory() as session:
            user_repository = UserRepository(session)
            account_repository = CatalogAccountRepository(session)
            admin = await user_repository.get_or_create_from_telegram(admin_user)
            accounts = await account_repository.list_all()
            await session.commit()

        rows: list[tuple[str, ...]] = []
        for account in accounts:
            rows.append(
                (
                    str(account.id),
                    str(account.supplier_item_id),
                    account.supplier_category_slug,
                    account.supplier_item_state,
                    account.game_type,
                    account.status,
                    str(account.top_tank_count),
                    str(account.premium_tank_count),
                    str(account.total_tank_count),
                    str(account.silver_amount),
                    str(account.gold_amount),
                    str(account.battles_count),
                    str(account.wins_count),
                    _format_money(Decimal(str(account.win_rate_percent))),
                    _format_money(Decimal(str(account.supplier_price))),
                    _format_money(Decimal(str(account.sale_price))),
                    _bool_label(account.has_tier_11, language=Language(admin.language)),
                    _bool_label(account.is_phone_bound, language=Language(admin.language)),
                    _bool_label(account.is_in_clan, language=Language(admin.language)),
                    account.region or "",
                    _format_datetime(account.last_active_at),
                    _format_datetime(account.registered_at),
                    _format_datetime(account.supplier_loaded_at),
                    _format_datetime(account.created_at),
                    _format_datetime(account.updated_at),
                    account.tanks_text,
                )
            )

        workbook_bytes = _build_products_xlsx(rows)
        filename = f"wotshop-products-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.xlsx"
        return Language(admin.language), BufferedInputFile(workbook_bytes, filename=filename)


def render_admin_products_menu_text(language: Language, total_products: int) -> str:
    return "\n".join(
        (
            translate(language, "admin_products_menu_title"),
            "",
            translate(language, "admin_products_total_count", count=total_products),
        )
    )


def render_admin_product_lookup_prompt_text(language: Language) -> str:
    return translate(language, "admin_product_lookup_prompt")


def render_admin_product_detail_text(product: AdminProductDetailSchema) -> str:
    pages = _build_admin_product_detail_pages(product)
    body = pages[product.detail_page - 1]
    if product.total_detail_pages <= 1:
        return body
    return "\n\n".join(
        (
            body,
            translate(
                product.language,
                "catalog_detail_page_meta",
                page=product.detail_page,
                total_pages=product.total_detail_pages,
            ),
        )
    )


def render_admin_product_delete_confirmation_text(language: Language, *, product_id: int) -> str:
    return translate(language, "admin_product_delete_confirmation", product_id=product_id)


def _format_money(amount: Decimal) -> str:
    normalized = amount.quantize(Decimal("0.01"))
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{normalized:.2f}"


def _bool_label(value: bool, *, language: Language) -> str:
    return translate(language, "yes") if value else translate(language, "no")


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")


def _build_admin_product_detail_pages(product: AdminProductDetailSchema) -> tuple[str, ...]:
    max_page_length = 900
    summary_page = "\n".join(
        (
            translate(product.language, "admin_product_detail_title", product_id=product.id),
            "",
            translate(product.language, "admin_product_supplier_item_id", value=product.supplier_item_id),
            translate(product.language, "admin_product_supplier_item_link", value=product.supplier_item_id),
            translate(product.language, "admin_product_supplier_category", value=escape(product.supplier_category_slug)),
            translate(product.language, "admin_product_supplier_state", value=escape(product.supplier_item_state)),
            "",
            translate(product.language, "admin_product_game_type", value=escape(product.game_type)),
            translate(product.language, "admin_product_status", value=escape(product.status)),
            translate(product.language, "admin_product_region", value=escape(product.region or "-")),
            "",
            translate(product.language, "admin_product_sale_price", value=_format_money(product.sale_price)),
            translate(product.language, "admin_product_supplier_price", value=_format_money(product.supplier_price)),
            "",
            translate(product.language, "admin_product_top_count", value=product.top_tank_count),
            translate(product.language, "admin_product_premium_count", value=product.premium_tank_count),
            translate(product.language, "admin_product_total_tanks", value=product.total_tank_count),
            translate(product.language, "admin_product_silver", value=f"{product.silver_amount:,}".replace(",", " ")),
            translate(product.language, "admin_product_gold", value=f"{product.gold_amount:,}".replace(",", " ")),
            translate(product.language, "admin_product_battles", value=product.battles_count),
            translate(product.language, "admin_product_wins", value=product.wins_count),
            translate(product.language, "admin_product_win_rate", value=_format_money(product.win_rate_percent)),
            translate(product.language, "admin_product_has_tier_11", value=_bool_label(product.has_tier_11, language=product.language)),
            translate(product.language, "admin_product_phone_bound", value=_bool_label(product.is_phone_bound, language=product.language)),
            translate(product.language, "admin_product_in_clan", value=_bool_label(product.is_in_clan, language=product.language)),
            "",
            translate(product.language, "admin_product_last_active", value=_format_datetime(product.last_active_at)),
            translate(product.language, "admin_product_registered_at", value=_format_datetime(product.registered_at)),
            translate(product.language, "admin_product_supplier_loaded_at", value=_format_datetime(product.supplier_loaded_at)),
            translate(product.language, "admin_product_created_at", value=_format_datetime(product.created_at)),
            translate(product.language, "admin_product_updated_at", value=_format_datetime(product.updated_at)),
        )
    )
    if not product.tanks_text.strip():
        return (summary_page,)

    tank_pages = _build_admin_product_tank_pages(
        language=product.language,
        tanks_text=product.tanks_text,
        max_page_length=max_page_length,
    )
    if len(tank_pages) == 1 and len(summary_page) + 2 + len(tank_pages[0]) <= max_page_length:
        return ("\n\n".join((summary_page, tank_pages[0])),)
    return (summary_page, *tank_pages)


def _build_admin_product_tank_pages(
    *,
    language: Language,
    tanks_text: str,
    max_page_length: int,
) -> tuple[str, ...]:
    tank_lines = [escape(line.strip()) for line in tanks_text.splitlines() if line.strip()]
    if not tank_lines:
        return (f"{translate(language, 'admin_product_tanks')}\n<blockquote>-</blockquote>",)

    pages: list[str] = []
    remaining_lines = list(tank_lines)
    is_first_page = True

    while remaining_lines:
        heading = (
            translate(language, "admin_product_tanks")
            if is_first_page
            else translate(language, "catalog_detail_tanks_continued")
        )
        chunk: list[str] = []
        for line in remaining_lines:
            candidate = chunk + [line]
            block = f"{heading}\n<blockquote>{'\n'.join(candidate)}</blockquote>"
            if len(block) <= max_page_length:
                chunk = candidate
                continue
            break

        if not chunk:
            chunk = [remaining_lines[0]]

        pages.append(f"{heading}\n<blockquote>{'\n'.join(chunk)}</blockquote>")
        remaining_lines = remaining_lines[len(chunk):]
        is_first_page = False

    return tuple(pages)


def _build_products_xlsx(rows: list[tuple[str, ...]]) -> bytes:
    headers = (
        "ID",
        "Supplier Item ID",
        "Supplier Category Slug",
        "Supplier Item State",
        "Game Type",
        "Status",
        "Top Tank Count",
        "Premium Tank Count",
        "Total Tank Count",
        "Silver Amount",
        "Gold Amount",
        "Battles Count",
        "Wins Count",
        "Win Rate Percent",
        "Supplier Price",
        "Sale Price",
        "Has Tier 11",
        "Phone Bound",
        "In Clan",
        "Region",
        "Last Active At",
        "Registered At",
        "Supplier Loaded At",
        "Created At",
        "Updated At",
        "Tanks Text",
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
  <Application>WotShop</Application>
</Properties>
"""

_CORE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>WotShop</dc:creator>
  <cp:lastModifiedBy>WotShop</cp:lastModifiedBy>
</cp:coreProperties>
"""

_WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Products" sheetId="1" r:id="rId1"/>
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
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
  </cellXfs>
</styleSheet>
"""

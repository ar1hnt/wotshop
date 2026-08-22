from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Select, Text, and_, cast, delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.catalog_account import (
    CatalogAccount,
    CatalogAccountStatus,
    CatalogSortField,
    GameAccountType,
    SortDirection,
)
from src.db.models.user_catalog_filter import UserCatalogFilter


# Common player names are mapped to the canonical spelling found in the LZT
# tank payload. The raw query is still searched too, so any tank not listed
# here retains partial-name search support.
TANK_SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "WT E 100": (
        "вафля", "ваф", "ваффля", "ваффентрагер", "ваффентраггер", "waffle",
        "waffentrager", "waffenträger", "waffentrager e 100", "waffenträger e 100",
        "wte100", "wt e100", "wt-e-100",
    ),
    "Оруженосец": ("оруженосец", "оруж", "wt e 100 оруженосец"),
    "T95/FV4201": (
        "чиф", "чифтейн", "чифтен", "chieftain", "chieftan", "chief", "t95fv4201", "fv4201",
    ),
    "Gendarme": ("жандарм", "жандар", "gendarme", "gendarm"),
    "Об. 279 (р)": (
        "279р", "279 р", "об279р", "об 279р", "об279 ранний", "279ранний", "object279e", "obj279e",
    ),
    "Об. 279": ("об279", "об 279", "object279", "obj279"),
    "Об. 780": ("780", "об780", "об 780", "object780", "obj780"),
    "BZT-70": ("bzt70", "bzt 70", "бзт70", "бзт 70"),
    "MBT-B": ("mbtb", "mbt b", "мбтб", "мбт б"),
    "116-F3": ("116f3", "116 f3", "116-ф3", "116 ф3"),
    "VK 72.01 K": ("vk7201", "vk 7201", "вк7201", "вк 72"),
    "XM57": ("xm57", "xm 57", "хм57", "хм 57"),
    "FV215b (183)": ("бабаха", "бабах", "fv183", "fv 183", "fv215b183", "фв183"),
    "Об. 260": ("об260", "об 260", "object260", "obj260"),
    "Об. 907": ("об907", "об 907", "object907", "obj907"),
    "T-22 ср.": ("т22", "т 22", "t22", "t 22"),
    "M60": ("м60", "m 60"),
    "Kpz. 07 P(E)": ("kpz07", "kpz 07", "кпз07", "кпз 07"),
    "IS-7": ("ис7", "ис 7", "is7", "is 7", "иссемь", "семерка"),
    "Об. 277": ("об277", "об 277", "obj277", "object277", "объект277"),
    "Об. 140": ("об140", "об 140", "obj140", "object140"),
    "Об. 430У": ("об430у", "об 430у", "obj430u", "object430u", "430у", "430u"),
    "Об. 268/4": ("об2684", "об 268 4", "obj2684", "object2684", "птшка", "птшк"),
    "E 100": ("е100", "е 100", "e100", "e 100", "сотка"),
    "Maus": ("маус", "мышь", "mouse"),
    "Super Conqueror": ("суперконь", "супер конь", "sconq", "s conq", "суперконкерор"),
    "60TP Lewandowskiego": ("60тп", "60 тп", "60tp", "60 tp", "шестидесятка"),
    "Grille 15": ("гриль", "grille15", "grille 15"),
    "Leopard 1": ("лео", "леопард", "leopard1", "leopard 1"),
    "Bat.-Châtillon 25 t": (
        "батчат", "бат чат", "bat chat", "batchat", "batchat25t", "bat chat 25t",
    ),
    "AMX 50 Foch B": ("фоч", "фош", "fochb", "foch b"),
    "Strv 103B": ("стрв", "strv103b", "strv 103b"),
    "UDES 15/16": ("удес", "udes1516", "udes 15 16"),
    "EBR 105": ("ебр", "ebr105", "ebr 105"),
    "Т-100 ЛТ": ("т100лт", "т100 лт", "t100lt", "t 100 lt", "сотый лт"),
    "Sheridan": ("шарик", "sheridan"),
    "Manticore": ("мантикора", "мантикор", "manticore"),
    "Progetto 65": ("проект", "progetto65", "progetto 65"),
    "TVP T 50/51": ("твп", "tvp", "tvpt5051", "tvp t 50 51"),
    "Kranvagn": ("кран", "kranvagn"),
    "Minotauro": ("минотавр", "minotauro"),
    "Rinoceronte": ("рино", "rinoceronte"),
    "Ho-Ri 3": ("хори", "hori3", "ho ri 3"),
    "FV4005": ("fv4005", "fv 4005", "фв4005", "фв 4005", "бабаха4005"),
    "FV217 Badger": ("баджер", "badger", "fv217", "fv 217"),
    "T110E3": ("т110е3", "т110 е3", "t110e3", "t110 e3"),
    "T110E4": ("т110е4", "т110 е4", "t110e4", "t110 e4"),
    "T57 Heavy": ("т57", "т 57", "t57", "t 57", "т57 хэви"),
    "WZ-111 5A": ("5а", "5a", "wz1115a", "wz 111 5a", "китайский277"),
    "Concept 1B": ("концепт", "concept1b", "concept 1b"),
    "AE Phase I": ("ае", "аешка", "ae phase", "ae phase i"),
    "Cobra": ("кобра", "cobra"),
    "Char Futur 4": ("чар", "char futur", "char futur 4"),
    "Skoda T 56": ("шкода", "skodat56", "skoda t56", "skoda t 56"),
    "BZ-176": ("бз176", "бз 176", "bz176", "bz 176"),
    "Bourrasque": ("бурасик", "bourrasque"),
    "ELC EVEN 90": ("елка", "ёлка", "elc90", "elc even 90"),
    "LT-432": ("лт432", "лт 432", "lt432", "lt 432"),
    "Об. 252У": ("об252у", "об 252у", "obj252u", "object252u", "defender", "дефендер"),
    "ИС-3А": ("ис3а", "ис 3а", "is3a", "is 3a"),
    "Cromwell B": ("кромб", "кромвель б", "crom b", "cromwell b"),
}


def _normalize_tank_search_value(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _tank_search_terms(raw_query: str) -> tuple[str, ...]:
    normalized_query = _normalize_tank_search_value(raw_query)
    if not normalized_query:
        return ()

    terms = {normalized_query}
    for canonical_name, aliases in TANK_SEARCH_SYNONYMS.items():
        normalized_aliases = tuple(_normalize_tank_search_value(alias) for alias in (*aliases, canonical_name))
        if any(
            normalized_query == alias
            or (len(normalized_query) >= 3 and alias.startswith(normalized_query))
            for alias in normalized_aliases
        ):
            terms.add(_normalize_tank_search_value(canonical_name))
    return tuple(sorted(terms))


class CatalogAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, account_id: int) -> CatalogAccount | None:
        query = select(CatalogAccount).where(CatalogAccount.id == account_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, account_id: int) -> CatalogAccount | None:
        query = select(CatalogAccount).where(CatalogAccount.id == account_id).with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def reserve(self, account: CatalogAccount, *, user_id: int) -> bool:
        if account.status != CatalogAccountStatus.AVAILABLE.value:
            return False
        account.status = CatalogAccountStatus.RESERVED.value
        account.reserved_for_user_id = user_id
        account.reserved_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def release_reservation(self, account: CatalogAccount, *, user_id: int | None = None) -> bool:
        if account.status != CatalogAccountStatus.RESERVED.value:
            return False
        if user_id is not None and account.reserved_for_user_id != user_id:
            return False
        account.status = CatalogAccountStatus.AVAILABLE.value
        account.reserved_for_user_id = None
        account.reserved_at = None
        await self.session.flush()
        return True

    async def mark_sold(self, account: CatalogAccount) -> None:
        account.status = CatalogAccountStatus.SOLD.value
        account.reserved_for_user_id = None
        account.reserved_at = None
        await self.session.flush()

    async def release_expired_reservations(self, *, before: datetime) -> int:
        result = await self.session.execute(
            update(CatalogAccount)
            .where(
                and_(
                    CatalogAccount.status == CatalogAccountStatus.RESERVED.value,
                    CatalogAccount.reserved_at.is_not(None),
                    CatalogAccount.reserved_at < before,
                )
            )
            .values(
                status=CatalogAccountStatus.AVAILABLE.value,
                reserved_for_user_id=None,
                reserved_at=None,
            )
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def get_by_supplier_item_id(self, supplier_item_id: int) -> CatalogAccount | None:
        query = select(CatalogAccount).where(CatalogAccount.supplier_item_id == supplier_item_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_supplier_item_ids(self, supplier_item_ids: list[int]) -> list[CatalogAccount]:
        if not supplier_item_ids:
            return []
        query = select(CatalogAccount).where(CatalogAccount.supplier_item_id.in_(supplier_item_ids))
        result = await self.session.execute(query)
        return list(result.scalars())

    async def list_all(self) -> list[CatalogAccount]:
        query = select(CatalogAccount).order_by(CatalogAccount.id.asc())
        result = await self.session.execute(query)
        return list(result.scalars())

    async def count_all(self) -> int:
        query = select(func.count(CatalogAccount.id))
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def delete(self, account: CatalogAccount) -> None:
        await self.session.delete(account)
        await self.session.flush()

    async def delete_all(self) -> None:
        await self.session.execute(delete(CatalogAccount))
        await self.session.flush()

    async def replace_all(self, rows: list[dict[str, object]]) -> None:
        protected_statuses = (
            CatalogAccountStatus.RESERVED.value,
            CatalogAccountStatus.SOLD.value,
        )
        protected_result = await self.session.execute(
            select(CatalogAccount.supplier_item_id).where(CatalogAccount.status.in_(protected_statuses))
        )
        protected_supplier_ids = set(protected_result.scalars())
        await self.session.execute(
            delete(CatalogAccount).where(CatalogAccount.status.not_in(protected_statuses))
        )
        fresh_rows = [row for row in rows if row["supplier_item_id"] not in protected_supplier_ids]
        if fresh_rows:
            await self.session.execute(insert(CatalogAccount), fresh_rows)
        await self.session.flush()

    async def search_page(
        self,
        catalog_filter: UserCatalogFilter,
        *,
        page: int,
        page_size: int,
    ) -> tuple[int, list[CatalogAccount]]:
        base_query = self._build_filtered_query(catalog_filter)

        total_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.session.execute(total_query)
        total_count = int(total_result.scalar_one())

        query = (
            self._apply_sort(base_query, catalog_filter)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        return total_count, list(result.scalars())

    def _build_filtered_query(self, catalog_filter: UserCatalogFilter) -> Select[tuple[CatalogAccount]]:
        query = select(CatalogAccount).where(
            CatalogAccount.game_type == catalog_filter.game_type,
            CatalogAccount.status == CatalogAccountStatus.AVAILABLE.value,
        )

        numeric_filters = (
            (CatalogAccount.sale_price, catalog_filter.sale_price_min, catalog_filter.sale_price_max),
            (CatalogAccount.top_tank_count, catalog_filter.top_tank_count_min, catalog_filter.top_tank_count_max),
            (CatalogAccount.premium_tank_count, catalog_filter.premium_tank_count_min, catalog_filter.premium_tank_count_max),
            (CatalogAccount.total_tank_count, catalog_filter.total_tank_count_min, catalog_filter.total_tank_count_max),
            (CatalogAccount.silver_amount, catalog_filter.silver_amount_min, catalog_filter.silver_amount_max),
            (CatalogAccount.gold_amount, catalog_filter.gold_amount_min, catalog_filter.gold_amount_max),
            (CatalogAccount.battles_count, catalog_filter.battles_count_min, catalog_filter.battles_count_max),
            (CatalogAccount.wins_count, catalog_filter.wins_count_min, catalog_filter.wins_count_max),
            (CatalogAccount.win_rate_percent, catalog_filter.win_rate_percent_min, catalog_filter.win_rate_percent_max),
        )
        for column, min_value, max_value in numeric_filters:
            if min_value is not None:
                query = query.where(column >= min_value)
            if max_value is not None:
                query = query.where(column <= max_value)

        date_filters = (
            (CatalogAccount.last_active_at, catalog_filter.last_active_from, catalog_filter.last_active_to),
            (CatalogAccount.registered_at, catalog_filter.registered_from, catalog_filter.registered_to),
            (CatalogAccount.supplier_loaded_at, catalog_filter.supplier_loaded_from, catalog_filter.supplier_loaded_to),
        )
        for column, start_at, end_at in date_filters:
            if start_at is not None:
                query = query.where(column >= start_at)
            if end_at is not None:
                query = query.where(column <= end_at)

        if catalog_filter.has_tier_11 is not None:
            query = query.where(CatalogAccount.has_tier_11 == catalog_filter.has_tier_11)
        if catalog_filter.is_phone_bound is not None:
            query = query.where(CatalogAccount.is_phone_bound == catalog_filter.is_phone_bound)
        if catalog_filter.is_in_clan is not None:
            query = query.where(CatalogAccount.is_in_clan == catalog_filter.is_in_clan)
        if catalog_filter.region and catalog_filter.game_type not in {
            GameAccountType.MIR_TANKOV.value,
            GameAccountType.TANKS_BLITZ.value,
        }:
            query = query.where(CatalogAccount.region.ilike(f"%{catalog_filter.region}%"))
        if catalog_filter.tank_query:
            terms = _tank_search_terms(catalog_filter.tank_query)
            if terms:
                normalized_tanks_payload = func.regexp_replace(
                    func.lower(cast(CatalogAccount.tanks_payload, Text)),
                    "[^[:alnum:]]",
                    "",
                    "g",
                )
                normalized_tanks_text = func.regexp_replace(
                    func.lower(CatalogAccount.tanks_text),
                    "[^[:alnum:]]",
                    "",
                    "g",
                )
                query = query.where(
                    or_(
                        *(
                            or_(
                                normalized_tanks_payload.contains(term),
                                normalized_tanks_text.contains(term),
                            )
                            for term in terms
                        )
                    )
                )

        return query

    @staticmethod
    def _apply_sort(query: Select[tuple[CatalogAccount]], catalog_filter: UserCatalogFilter) -> Select[tuple[CatalogAccount]]:
        sort_columns = {
            CatalogSortField.PRICE: CatalogAccount.sale_price,
            CatalogSortField.LAST_ACTIVITY: CatalogAccount.last_active_at,
            CatalogSortField.NEWEST: CatalogAccount.supplier_loaded_at,
        }
        direction_fields = {
            CatalogSortField.PRICE: "price_sort_direction",
            CatalogSortField.LAST_ACTIVITY: "last_activity_sort_direction",
            CatalogSortField.NEWEST: "newest_sort_direction",
        }
        sort_field = CatalogSortField(catalog_filter.active_sort_field)
        direction = SortDirection(getattr(catalog_filter, direction_fields[sort_field]))
        sort_column = sort_columns[sort_field]
        sort_expression = sort_column.asc() if direction == SortDirection.ASC else sort_column.desc()

        if sort_field in {CatalogSortField.LAST_ACTIVITY, CatalogSortField.NEWEST}:
            sort_expression = sort_expression.nulls_last()

        return query.order_by(
            sort_expression,
            CatalogAccount.id.desc(),
        )

    @staticmethod
    def to_decimal(value: Decimal | int | float | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

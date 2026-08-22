from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Select, Text, and_, cast, delete, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.catalog_account import CatalogAccount, CatalogAccountStatus, GameAccountType, SortDirection
from src.db.models.user_catalog_filter import UserCatalogFilter


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
            search_pattern = f"%{catalog_filter.tank_query.strip()}%"
            query = query.where(
                or_(
                    cast(CatalogAccount.tanks_payload, Text).ilike(search_pattern),
                    CatalogAccount.tanks_text.ilike(search_pattern),
                )
            )

        return query

    @staticmethod
    def _apply_sort(query: Select[tuple[CatalogAccount]], catalog_filter: UserCatalogFilter) -> Select[tuple[CatalogAccount]]:
        return query.order_by(
            CatalogAccount.sale_price.asc(),
            CatalogAccount.id.desc(),
        )

    @staticmethod
    def to_decimal(value: Decimal | int | float | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

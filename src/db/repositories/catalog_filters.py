from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.catalog_account import CatalogSortField, GameAccountType, SortDirection
from src.db.models.user_catalog_filter import UserCatalogFilter


class UserCatalogFilterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_and_game_type(self, *, user_id: int, game_type: GameAccountType) -> UserCatalogFilter | None:
        query = select(UserCatalogFilter).where(
            UserCatalogFilter.user_id == user_id,
            UserCatalogFilter.game_type == game_type.value,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create(self, *, user_id: int, game_type: GameAccountType) -> UserCatalogFilter:
        catalog_filter = await self.get_by_user_and_game_type(user_id=user_id, game_type=game_type)
        if catalog_filter is not None:
            return catalog_filter

        catalog_filter = UserCatalogFilter(user_id=user_id, game_type=game_type.value)
        self.session.add(catalog_filter)
        await self.session.flush()
        return catalog_filter

    async def set_range(self, catalog_filter: UserCatalogFilter, *, min_field: str, max_field: str, min_value: int | Decimal | None, max_value: int | Decimal | None) -> None:
        setattr(catalog_filter, min_field, min_value)
        setattr(catalog_filter, max_field, max_value)
        await self.session.flush()

    async def set_datetime_range(
        self,
        catalog_filter: UserCatalogFilter,
        *,
        from_field: str,
        to_field: str,
        from_value: datetime | None,
        to_value: datetime | None,
    ) -> None:
        setattr(catalog_filter, from_field, from_value)
        setattr(catalog_filter, to_field, to_value)
        await self.session.flush()

    async def set_boolean(self, catalog_filter: UserCatalogFilter, *, field_name: str, value: bool | None) -> None:
        setattr(catalog_filter, field_name, value)
        await self.session.flush()

    async def set_text(self, catalog_filter: UserCatalogFilter, *, field_name: str, value: str | None) -> None:
        setattr(catalog_filter, field_name, value)
        await self.session.flush()

    async def reset(self, catalog_filter: UserCatalogFilter) -> None:
        catalog_filter.sale_price_min = None
        catalog_filter.sale_price_max = None
        catalog_filter.top_tank_count_min = None
        catalog_filter.top_tank_count_max = None
        catalog_filter.premium_tank_count_min = None
        catalog_filter.premium_tank_count_max = None
        catalog_filter.total_tank_count_min = None
        catalog_filter.total_tank_count_max = None
        catalog_filter.silver_amount_min = None
        catalog_filter.silver_amount_max = None
        catalog_filter.gold_amount_min = None
        catalog_filter.gold_amount_max = None
        catalog_filter.battles_count_min = None
        catalog_filter.battles_count_max = None
        catalog_filter.wins_count_min = None
        catalog_filter.wins_count_max = None
        catalog_filter.win_rate_percent_min = None
        catalog_filter.win_rate_percent_max = None
        catalog_filter.last_active_from = None
        catalog_filter.last_active_to = None
        catalog_filter.has_tier_11 = None
        catalog_filter.registered_from = None
        catalog_filter.registered_to = None
        catalog_filter.is_phone_bound = None
        catalog_filter.is_in_clan = None
        catalog_filter.tank_query = None
        catalog_filter.region = None
        catalog_filter.supplier_loaded_from = None
        catalog_filter.supplier_loaded_to = None
        catalog_filter.active_sort_field = CatalogSortField.PRICE.value
        catalog_filter.price_sort_direction = SortDirection.ASC.value
        catalog_filter.last_activity_sort_direction = SortDirection.ASC.value
        catalog_filter.newest_sort_direction = SortDirection.DESC.value
        await self.session.flush()

    async def set_sort(self, catalog_filter: UserCatalogFilter, *, field: CatalogSortField, direction: SortDirection) -> None:
        field_name_map = {
            CatalogSortField.PRICE: "price_sort_direction",
            CatalogSortField.LAST_ACTIVITY: "last_activity_sort_direction",
            CatalogSortField.NEWEST: "newest_sort_direction",
        }
        catalog_filter.active_sort_field = field.value
        setattr(catalog_filter, field_name_map[field], direction.value)
        await self.session.flush()

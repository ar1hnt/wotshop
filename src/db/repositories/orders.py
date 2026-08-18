from decimal import Decimal

from datetime import datetime

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.financial import CARD_WITHDRAWAL_LOSS_RATIO
from src.db.models import Order


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        sale_amount: Decimal,
        supplier_amount: Decimal,
        catalog_account_id: int | None,
        supplier_item_id: int | None,
        account_snapshot: dict[str, object] | None,
        fulfillment_payload: dict[str, object] | None,
        description: str | None,
        delivery_data: dict[str, str] | None = None,
        payout_fee_percent: Decimal = Decimal("3.92"),
        currency: str = "RUB",
    ) -> Order:
        order = Order(
            user_id=user_id,
            catalog_account_id=catalog_account_id,
            supplier_item_id=supplier_item_id,
            account_snapshot=account_snapshot,
            fulfillment_payload=fulfillment_payload,
            delivery_data=delivery_data,
            sale_amount=sale_amount,
            supplier_amount=supplier_amount,
            payout_fee_percent=payout_fee_percent,
            currency=currency,
            status="paid",
            description=description,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_user_stats(self, user_id: int) -> tuple[int, Decimal]:
        query = select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.sale_amount), 0),
        ).where(Order.user_id == user_id)
        result = await self.session.execute(query)
        orders_count, total_spent = result.one()
        total_decimal = total_spent if isinstance(total_spent, Decimal) else Decimal(str(total_spent))
        return int(orders_count), total_decimal

    async def get_recent_by_user(self, user_id: int, limit: int = 10) -> list[Order]:
        query = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars())

    async def count_by_user(self, user_id: int) -> int:
        query = select(func.count(Order.id)).where(Order.user_id == user_id)
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def get_page_by_user(
        self,
        user_id: int,
        *,
        page: int,
        page_size: int,
    ) -> list[Order]:
        offset = max(page - 1, 0) * page_size
        query = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        return list(result.scalars())

    async def get_financial_summary(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> tuple[int, Decimal, Decimal, Decimal]:
        card_withdrawal_loss_expression = Order.sale_amount * literal(CARD_WITHDRAWAL_LOSS_RATIO)
        query = select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.sale_amount), 0),
            func.coalesce(func.sum(Order.supplier_amount), 0),
            func.coalesce(func.sum(card_withdrawal_loss_expression), 0),
        )

        if start_at is not None:
            query = query.where(Order.created_at >= start_at)
        if end_at is not None:
            query = query.where(Order.created_at <= end_at)

        result = await self.session.execute(query)
        orders_count, revenue, supplier_expense, card_withdrawal_loss = result.one()
        return (
            int(orders_count),
            self._to_decimal(revenue),
            self._to_decimal(supplier_expense),
            self._to_decimal(card_withdrawal_loss),
        )

    @staticmethod
    def _to_decimal(value: Decimal | int | float | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

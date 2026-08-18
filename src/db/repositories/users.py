from datetime import datetime
from decimal import Decimal

from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from src.i18n import Language


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        query = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_telegram_id_for_update(self, telegram_id: int) -> User | None:
        query = select(User).where(User.telegram_id == telegram_id).with_for_update()
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_from_telegram(self, telegram_user: TelegramUser) -> User:
        user, _ = await self.get_or_create_from_telegram_with_flag(telegram_user)
        return user

    async def get_or_create_from_telegram_with_flag(self, telegram_user: TelegramUser) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_user.id)

        if user is None:
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language=Language.RU.value, # type: ignore
            )
            self.session.add(user)
            await self.session.flush()
            return user, True

        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        await self.session.flush()
        return user, False

    async def update_language(self, user: User, language: Language) -> None:
        user.language = language.value  # type: ignore
        await self.session.flush()

    async def update_balance(self, user: User, balance: Decimal) -> None:
        user.balance = balance
        await self.session.flush()

    async def debit_balance(self, user: User, amount: Decimal) -> bool:
        if user.balance < amount:
            return False
        user.balance -= amount
        await self.session.flush()
        return True

    async def credit_balance(self, user: User, amount: Decimal) -> None:
        user.balance += amount
        await self.session.flush()

    async def count_all(self) -> int:
        query = select(func.count(User.id))
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def list_all(self) -> list[User]:
        query = select(User).order_by(User.id.asc())
        result = await self.session.execute(query)
        return list(result.scalars())

    async def list_telegram_ids(self) -> list[int]:
        query = select(User.telegram_id).order_by(User.id.asc())
        result = await self.session.execute(query)
        return [int(value) for value in result.scalars()]

    async def search_by_bot_or_telegram_id(self, *, identifier_type: str, identifier_value: int) -> User | None:
        if identifier_type == "bot_id":
            return await self.get_by_id(identifier_value)

        return await self.get_by_telegram_id(identifier_value)

    async def get_user_stats_summary(self, user_id: int) -> tuple[int, Decimal]:
        from src.db.models.order import Order

        query = select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.sale_amount), 0),
        ).where(Order.user_id == user_id)
        result = await self.session.execute(query)
        orders_count, total_spent = result.one()
        total_decimal = total_spent if isinstance(total_spent, Decimal) else Decimal(str(total_spent))
        return int(orders_count), total_decimal

    async def count_created_in_period(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> int:
        query = select(func.count(User.id))

        if start_at is not None:
            query = query.where(User.created_at >= start_at)
        if end_at is not None:
            query = query.where(User.created_at <= end_at)

        result = await self.session.execute(query)
        return int(result.scalar_one())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.favorite import Favorite


class FavoriteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user_and_code(self, *, user_id: int, product_code: str) -> Favorite | None:
        query = select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.product_code == product_code,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def exists(self, *, user_id: int, product_code: str) -> bool:
        return await self.get_by_user_and_code(user_id=user_id, product_code=product_code) is not None

    async def add(self, *, user_id: int, product_code: str) -> Favorite:
        favorite = Favorite(user_id=user_id, product_code=product_code)
        self.session.add(favorite)
        await self.session.flush()
        return favorite

    async def list_by_user_and_prefix(self, *, user_id: int, prefix: str) -> list[Favorite]:
        query = (
            select(Favorite)
            .where(
                Favorite.user_id == user_id,
                Favorite.product_code.like(f"{prefix}%"),
            )
            .order_by(Favorite.created_at.desc(), Favorite.id.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars())

    async def remove(self, favorite: Favorite) -> None:
        await self.session.delete(favorite)
        await self.session.flush()

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.faq_entry import FaqEntry

FAQ_LOCALIZED_FIELDS = frozenset({"question_ru", "question_en", "answer_ru", "answer_en"})


class FaqEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_all(self) -> int:
        query = select(func.count(FaqEntry.id))
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def get_page(self, *, offset: int, limit: int) -> list[FaqEntry]:
        query = (
            select(FaqEntry)
            .order_by(FaqEntry.sort_order.asc(), FaqEntry.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars())

    async def get_by_id(self, faq_id: int) -> FaqEntry | None:
        query = select(FaqEntry).where(FaqEntry.id == faq_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_next_sort_order(self) -> int:
        query = select(func.coalesce(func.max(FaqEntry.sort_order), 0))
        result = await self.session.execute(query)
        return int(result.scalar_one()) + 1

    async def add(
        self,
        *,
        question_ru: str,
        question_en: str,
        answer_ru: str,
        answer_en: str,
    ) -> FaqEntry:
        entry = FaqEntry(
            question_ru=question_ru,
            question_en=question_en,
            answer_ru=answer_ru,
            answer_en=answer_en,
            sort_order=await self.get_next_sort_order(),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def update_localized_field(self, entry: FaqEntry, field_name: str, value: str) -> None:
        if field_name not in FAQ_LOCALIZED_FIELDS:
            raise ValueError(f"Unsupported FAQ field: {field_name}")
        setattr(entry, field_name, value)
        await self.session.flush()

    async def delete(self, entry: FaqEntry) -> None:
        await self.session.delete(entry)
        await self.session.flush()

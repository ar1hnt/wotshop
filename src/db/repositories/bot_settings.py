from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.bot_settings import BotSettings


class BotSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self) -> BotSettings | None:
        query = select(BotSettings).where(BotSettings.id == 1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create(self) -> BotSettings:
        settings = await self.get()
        if settings is not None:
            return settings

        settings = BotSettings(id=1)
        self.session.add(settings)
        await self.session.flush()
        return settings

    async def set_sales_enabled(self, settings: BotSettings, enabled: bool) -> None:
        settings.sales_enabled = enabled
        await self.session.flush()

    async def set_game_sales_enabled(self, settings: BotSettings, field_name: str, enabled: bool) -> None:
        setattr(settings, field_name, enabled)
        await self.session.flush()

from dataclasses import dataclass

from aiogram.types import User as TelegramUser

from src.db import async_session_factory
from src.db.models.catalog_account import GameAccountType
from src.db.repositories import BotSettingsRepository, UserRepository
from src.i18n import Language, translate


_GAME_SALES_FIELDS: dict[GameAccountType, str] = {
    GameAccountType.MIR_TANKOV: "mir_tankov_sales_enabled",
    GameAccountType.TANKS_BLITZ: "tanks_blitz_sales_enabled",
    GameAccountType.WORLD_OF_TANKS: "world_of_tanks_sales_enabled",
    GameAccountType.WOT_BLITZ: "wot_blitz_sales_enabled",
}


@dataclass(frozen=True)
class SalesSettingsContext:
    language: Language
    global_enabled: bool
    game_enabled: dict[GameAccountType, bool]


class BotSettingsService:
    async def is_sales_enabled(self, game_type: GameAccountType | None = None) -> bool:
        async with async_session_factory() as session:
            repository = BotSettingsRepository(session)
            settings = await repository.get_or_create()
            await session.commit()
        if not settings.sales_enabled or _are_sales_blocked_by_sync():
            return False
        if game_type is None:
            return True
        return bool(getattr(settings, _GAME_SALES_FIELDS[game_type]))

    async def get_admin_context(self, telegram_user: TelegramUser) -> tuple[Language, bool]:
        context = await self.get_sales_context(telegram_user)
        return context.language, context.global_enabled and not _are_sales_blocked_by_sync()

    async def get_sales_context(self, telegram_user: TelegramUser) -> SalesSettingsContext:
        async with async_session_factory() as session:
            users = UserRepository(session)
            settings_repository = BotSettingsRepository(session)
            admin = await users.get_or_create_from_telegram(telegram_user)
            settings = await settings_repository.get_or_create()
            context = SalesSettingsContext(
                language=Language(admin.language),
                global_enabled=bool(settings.sales_enabled),
                game_enabled={
                    game_type: bool(getattr(settings, field_name))
                    for game_type, field_name in _GAME_SALES_FIELDS.items()
                },
            )
            await session.commit()
        return context

    async def toggle_global_sales(self, telegram_user: TelegramUser) -> SalesSettingsContext:
        async with async_session_factory() as session:
            users = UserRepository(session)
            repository = BotSettingsRepository(session)
            admin = await users.get_or_create_from_telegram(telegram_user)
            settings = await repository.get_or_create()
            await repository.set_sales_enabled(settings, not settings.sales_enabled)
            context = SalesSettingsContext(
                language=Language(admin.language),
                global_enabled=bool(settings.sales_enabled),
                game_enabled={
                    game_type: bool(getattr(settings, field_name))
                    for game_type, field_name in _GAME_SALES_FIELDS.items()
                },
            )
            await session.commit()
        return context

    async def toggle_game_sales(self, telegram_user: TelegramUser, game_type: GameAccountType) -> SalesSettingsContext:
        async with async_session_factory() as session:
            users = UserRepository(session)
            repository = BotSettingsRepository(session)
            admin = await users.get_or_create_from_telegram(telegram_user)
            settings = await repository.get_or_create()
            field_name = _GAME_SALES_FIELDS[game_type]
            await repository.set_game_sales_enabled(settings, field_name, not bool(getattr(settings, field_name)))
            context = SalesSettingsContext(
                language=Language(admin.language),
                global_enabled=bool(settings.sales_enabled),
                game_enabled={
                    item_type: bool(getattr(settings, item_field))
                    for item_type, item_field in _GAME_SALES_FIELDS.items()
                },
            )
            await session.commit()
        return context


def render_sales_disabled_alert(language: Language, game_type: GameAccountType | None = None) -> str:
    if game_type is None:
        return translate(language, "sales_disabled_alert")
    return translate(language, "sales_game_disabled_alert", game_type=_game_type_label(language, game_type))


def render_sales_management_text(context: SalesSettingsContext) -> str:
    status = lambda enabled: translate(context.language, "sales_status_enabled" if enabled else "sales_status_disabled")
    return "\n".join(
        (
            translate(context.language, "admin_sales_management_title"),
            "",
            translate(context.language, "admin_sales_all_status", value=status(context.global_enabled)),
            "",
            translate(context.language, "admin_sales_game_status", game_type=_game_type_label(context.language, GameAccountType.MIR_TANKOV), value=status(context.game_enabled[GameAccountType.MIR_TANKOV])),
            translate(context.language, "admin_sales_game_status", game_type=_game_type_label(context.language, GameAccountType.TANKS_BLITZ), value=status(context.game_enabled[GameAccountType.TANKS_BLITZ])),
            translate(context.language, "admin_sales_game_status", game_type=_game_type_label(context.language, GameAccountType.WORLD_OF_TANKS), value=status(context.game_enabled[GameAccountType.WORLD_OF_TANKS])),
            translate(context.language, "admin_sales_game_status", game_type=_game_type_label(context.language, GameAccountType.WOT_BLITZ), value=status(context.game_enabled[GameAccountType.WOT_BLITZ])),
        )
    )


def _game_type_label(language: Language, game_type: GameAccountType) -> str:
    key = {
        GameAccountType.MIR_TANKOV: "catalog_game_type_mir_tankov",
        GameAccountType.TANKS_BLITZ: "catalog_game_type_tanks_blitz",
        GameAccountType.WORLD_OF_TANKS: "catalog_game_type_world_of_tanks",
        GameAccountType.WOT_BLITZ: "catalog_game_type_wot_blitz",
    }[game_type]
    return translate(language, key)


def render_force_refresh_placeholder_text(language: Language) -> str:
    return translate(language, "admin_force_refresh_placeholder")


def _are_sales_blocked_by_sync() -> bool:
    from src.services.sync import catalog_sync_service

    return catalog_sync_service.are_sales_temporarily_blocked()

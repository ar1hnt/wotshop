from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from src.config import settings


def is_admin_telegram_id(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


class IsAdminFilter(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = _extract_user(event)
        return user is not None and is_admin_telegram_id(user.id)


def _extract_user(event: TelegramObject) -> User | None:
    if isinstance(event, Message):
        return event.from_user
    if isinstance(event, CallbackQuery):
        return event.from_user
    return getattr(event, "from_user", None)

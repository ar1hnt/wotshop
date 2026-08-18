from aiogram.types import FSInputFile, Message

from src.schemas.common.menu import ScreenMediaSchema


_PHOTO_FILE_IDS: dict[str, str] = {}


def resolve_photo_input(media: ScreenMediaSchema) -> str | FSInputFile:
    cached_file_id = _PHOTO_FILE_IDS.get(media.cache_key)

    if cached_file_id is not None:
        return cached_file_id

    return FSInputFile(media.path)


def remember_photo_file_id(media: ScreenMediaSchema, message: Message) -> None:
    if not message.photo:
        return

    _PHOTO_FILE_IDS[media.cache_key] = message.photo[-1].file_id

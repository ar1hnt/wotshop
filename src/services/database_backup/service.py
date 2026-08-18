import asyncio
import hmac
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile

from src.config import settings
from src.i18n import Language, translate

logger = logging.getLogger(__name__)


class DatabaseBackupService:
    """Creates one PostgreSQL custom-format dump and delivers it to admins."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    def is_configured(self) -> bool:
        return bool(settings.db_dump_password and settings.admin_ids)

    def password_matches(self, value: str) -> bool:
        password = settings.db_dump_password
        return password is not None and hmac.compare_digest(value, password)

    async def create_and_notify(self, bot: Bot, *, language: Language) -> Path:
        if not self.is_configured():
            raise RuntimeError("DB_DUMP_PASSWORD or ADMIN_IDS is not configured.")

        async with self._lock:
            dump_path = await asyncio.to_thread(self._create_dump)
            try:
                await self._notify_admins(bot, dump_path, language)
            except Exception:
                logger.exception("Database backup delivery failed; keeping previous dumps for safety.")
                raise
            else:
                await asyncio.to_thread(self._remove_old_dumps, dump_path)
            return dump_path

    def _create_dump(self) -> Path:
        backups_dir = settings.database_backups_dir
        backups_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(settings.default_timezone)
        dump_path = backups_dir / f"wotshop_{created_at:%Y-%m-%d_%H-%M-%S}_MSK.dump"

        parts = urlsplit(settings.database_url)
        if not parts.hostname or not parts.username:
            raise RuntimeError("DATABASE_URL must contain database host and user.")
        database_name = parts.path.lstrip("/")
        if not database_name:
            raise RuntimeError("DATABASE_URL must contain database name.")

        environment = os.environ.copy()
        if parts.password:
            environment["PGPASSWORD"] = unquote(parts.password)

        command = [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--host", parts.hostname,
            "--port", str(parts.port or 5432),
            "--username", unquote(parts.username),
            "--file", str(dump_path),
            database_name,
        ]
        logger.info("Creating PostgreSQL database backup path=%s", dump_path)
        try:
            subprocess.run(command, check=True, env=environment, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            dump_path.unlink(missing_ok=True)
            logger.error("PostgreSQL backup failed stderr=%s", error.stderr.strip())
            raise RuntimeError("pg_dump failed") from error
        return dump_path

    async def _notify_admins(self, bot: Bot, dump_path: Path, language: Language) -> None:
        created_at = datetime.now(settings.default_timezone).strftime("%d.%m.%Y %H:%M:%S")
        caption = translate(language, "admin_database_backup_document_caption", created_at=created_at)
        delivered_count = 0
        for admin_id in settings.admin_ids:
            try:
                await bot.send_document(
                    chat_id=admin_id,
                    document=FSInputFile(dump_path, filename=dump_path.name),
                    caption=caption,
                )
                delivered_count += 1
            except TelegramAPIError:
                logger.exception("Failed to deliver database backup admin_telegram_id=%s", admin_id)
        if delivered_count == 0:
            raise RuntimeError("The backup was not delivered to any administrator.")
        logger.info("PostgreSQL backup delivered admins=%s path=%s", delivered_count, dump_path)

    @staticmethod
    def _remove_old_dumps(current_dump: Path) -> None:
        for old_dump in settings.database_backups_dir.glob("*.dump"):
            if old_dump != current_dump:
                old_dump.unlink(missing_ok=True)
                logger.info("Removed expired PostgreSQL backup path=%s", old_dump)


class DatabaseBackupScheduler:
    def __init__(self, backup_service: DatabaseBackupService, bot: Bot) -> None:
        self._backup_service = backup_service
        self._bot = bot
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if not self._backup_service.is_configured():
            logger.warning("Database backup scheduler is disabled: DB_DUMP_PASSWORD or ADMIN_IDS is missing.")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            delay = _seconds_until_next_moscow_backup_time()
            logger.info("Next database backup is scheduled in %.2f seconds.", delay)
            await asyncio.sleep(delay)
            try:
                await self._backup_service.create_and_notify(self._bot, language=Language.RU)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled database backup failed.")


def _seconds_until_next_moscow_backup_time() -> float:
    now = datetime.now(settings.default_timezone)
    target = now.replace(hour=23, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()

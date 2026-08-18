import asyncio
import logging
import os
import subprocess
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config.settings import settings
from src.logging import setup_logging
from src.routers import setup_routers
from src.services.payments import payment_service
from src.services.payments.webhook import create_payment_webhook_app
from src.services.sync import CatalogSyncScheduler, catalog_sync_service


logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Apply pending schema changes before the bot opens database sessions."""
    logger.info("Running Alembic migrations to head")
    # Alembic must migrate exactly the same database that is used by the
    # SQLAlchemy session factory.  In particular, this avoids a mismatch
    # between DATABASE_URL from a PyCharm/shell environment and `.env`.
    environment = os.environ.copy()
    environment["DATABASE_URL"] = settings.database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=environment,
    )
    logger.info("Alembic migrations completed")


async def main() -> None:
    scheduler = CatalogSyncScheduler(catalog_sync_service)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(setup_routers())
    webhook_runner = await _start_payment_webhook_server(bot)
    payment_service.start(bot)
    scheduler.start()
    logger.info("Catalog sync scheduler started")
    try:
        await dispatcher.start_polling(bot, settings=settings)
    finally:
        await scheduler.stop()
        await payment_service.shutdown()
        await webhook_runner.cleanup()
        logger.info("Catalog sync scheduler stopped")


async def _start_payment_webhook_server(bot: Bot):
    from aiohttp import web

    app = create_payment_webhook_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.payment_webhook_host, settings.payment_webhook_port)
    await site.start()
    logger.info(
        "Payment webhook server started host=%s port=%s path=/webhooks/platega",
        settings.payment_webhook_host,
        settings.payment_webhook_port,
    )
    return runner


def run() -> None:
    setup_logging()
    _run_migrations()
    asyncio.run(main())

import json
import logging

from aiohttp import web
from aiogram import Bot
from pydantic import ValidationError

from src.services.payments import PlategaCallbackPayload, payment_service

logger = logging.getLogger(__name__)


def create_payment_webhook_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post("/webhooks/platega", handle_platega_webhook)
    return app


async def handle_platega_webhook(request: web.Request) -> web.Response:
    # Platega validates a callback URL with an empty POST request.
    raw_body = await request.read()
    if not raw_body:
        return web.Response(status=200)

    if not payment_service.is_webhook_authorized(
        request.headers.get("X-MerchantId"),
        request.headers.get("X-Secret"),
    ):
        logger.warning("Rejected unauthorized Platega webhook remote=%s", request.remote)
        return web.Response(status=401)

    try:
        raw_payload = json.loads(raw_body)
        payload = PlategaCallbackPayload.model_validate(raw_payload)
    except (ValidationError, ValueError, TypeError):
        logger.warning("Rejected malformed Platega webhook remote=%s", request.remote)
        return web.Response(status=400)

    try:
        await payment_service.handle_callback(request.app["bot"], payload)
    except Exception:
        logger.exception("Failed to process Platega webhook transaction=%s", payload.transaction_id)
        return web.Response(status=500)
    return web.Response(status=200)

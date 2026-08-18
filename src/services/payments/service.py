import asyncio
import hmac
import logging
import re

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html import escape

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InputMediaPhoto, User as TelegramUser
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.config import settings
from src.db import async_session_factory
from src.db.models.catalog_account import CatalogAccount, CatalogAccountStatus, GameAccountType
from src.db.models.transaction import Transaction, TransactionStatus, TransactionType
from src.db.repositories import CatalogAccountRepository, OrderRepository, TransactionRepository, UserRepository
from src.i18n import Language, translate
from src.keyboards.inline import build_payment_purchase_failed_markup, build_purchase_completed_markup
from src.schemas.common.menu import CATALOG_ACCOUNT_SCREEN_MEDIA
from src.services.sync import (
    CatalogRefreshResult,
    LztApiResponseError,
    LztConfigurationError,
    LztSyncError,
    catalog_sync_service,
    render_catalog_refresh_result_text,
)
from src.services.system import BotSettingsService
from src.services.transactions import TransactionService
from src.services.media.media_cache import resolve_photo_input

logger = logging.getLogger(__name__)

PLATEGA_API_URL = "https://app.platega.io/v2/transaction/process"
PLATEGA_TIMEOUT_SECONDS = 30


class PaymentError(Exception):
    pass


class PaymentUnavailableError(PaymentError):
    pass


class AccountValidationError(PaymentError):
    """The supplier-side account validation could not be completed."""


class AccountUnavailableError(PaymentError):
    pass


class AccountPurchaseFulfillmentError(AccountUnavailableError):
    """A balance-only fulfillment failure that was already reported to admins."""


class AccountPriceChangedError(AccountValidationError):
    def __init__(self, refresh_result: CatalogRefreshResult) -> None:
        self.refresh_result = refresh_result
        super().__init__("Supplier price changed during purchase confirmation.")


class PlategaCreateTransactionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transaction_id: str = Field(validation_alias="transactionId")
    payment_url: str = Field(validation_alias="url")
    status: str


class PlategaCallbackPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transaction_id: str = Field(validation_alias="id")
    amount: Decimal
    currency: str
    status: str
    payment_method: int | None = Field(default=None, validation_alias="paymentMethod")


@dataclass(frozen=True)
class PaymentLinkResult:
    transaction_id: int
    payment_url: str
    amount: Decimal
    language: Language


@dataclass(frozen=True)
class PurchaseResult:
    completed: bool
    transaction_id: int
    payment_url: str | None
    language: Language
    payment_amount: Decimal
    balance_amount: Decimal
    delivery_text: str | None = None


class PlategaClient:
    def is_configured(self) -> bool:
        return bool(
            settings.platega_merchant_id
            and settings.platega_secret
            and settings.platega_return_url
            and settings.platega_failed_url
        )

    async def create_payment_link(
        self,
        *,
        amount: Decimal,
        description: str,
        payload: str,
        telegram_user: TelegramUser,
    ) -> PlategaCreateTransactionResponse:
        if not self.is_configured():
            raise PaymentUnavailableError("Platega is not configured.")

        request_payload = {
            "paymentDetails": {"amount": float(amount), "currency": "RUB"},
            "description": description[:255],
            "return": settings.platega_return_url,
            "failedUrl": settings.platega_failed_url,
            "payload": payload,
            "metadata": {
                "userId": str(telegram_user.id),
                "userName": f"@{telegram_user.username}" if telegram_user.username else telegram_user.full_name,
            },
        }
        headers = {
            "X-MerchantId": settings.platega_merchant_id or "",
            "X-Secret": settings.platega_secret or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=PLATEGA_TIMEOUT_SECONDS)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(PLATEGA_API_URL, json=request_payload, headers=headers) as response:
                    response_payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            raise PaymentUnavailableError("Failed to create Platega payment link.") from error

        if not 200 <= response.status < 300:
            logger.warning("Platega create payment failed status=%s payload=%s", response.status, response_payload)
            raise PaymentUnavailableError("Platega rejected payment creation request.")
        try:
            return PlategaCreateTransactionResponse.model_validate(response_payload)
        except ValidationError as error:
            logger.error("Unexpected Platega payment response payload=%s", response_payload)
            raise PaymentUnavailableError("Unexpected Platega response.") from error


class PaymentService:
    def __init__(self) -> None:
        self._platega_client = PlategaClient()
        self._bot_settings_service = BotSettingsService()
        self._transaction_service = TransactionService()
        self._fulfillment_tasks: dict[int, asyncio.Task[None]] = {}
        self._recovery_task: asyncio.Task[None] | None = None
        self._bot: Bot | None = None

    def start(self, bot: Bot) -> None:
        self._bot = bot
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = asyncio.create_task(self._resume_processing_purchases(bot))

    def is_webhook_authorized(self, merchant_id: str | None, secret: str | None) -> bool:
        if not settings.platega_merchant_id or not settings.platega_secret:
            return False
        return bool(
            merchant_id
            and secret
            and hmac.compare_digest(merchant_id, settings.platega_merchant_id)
            and hmac.compare_digest(secret, settings.platega_secret)
        )

    async def create_top_up_payment(self, bot: Bot, telegram_user: TelegramUser, raw_amount: str) -> PaymentLinkResult:
        amount = _parse_amount(raw_amount)
        if amount <= 0:
            raise PaymentError("Amount must be positive.")
        language, transaction = await self._create_pending_transaction(
            telegram_user,
            transaction_type=TransactionType.TOP_UP,
            amount=amount,
            description=f"Balance top-up for user #{telegram_user.id}",
        )
        try:
            provider_response = await self._platega_client.create_payment_link(
                amount=amount,
                description=f"Пополнение баланса WOT SHOP на {amount} RUB",
                payload=f"top_up:{transaction.id}",
                telegram_user=telegram_user,
            )
            await self._set_provider_data(transaction.id, provider_response.transaction_id, str(provider_response.payment_url))
            await self._transaction_service.notify_admins_about_started_transaction(bot, transaction.id)
        except Exception as error:
            await self._fail_transaction(transaction.id, str(error))
            raise
        return PaymentLinkResult(transaction.id, str(provider_response.payment_url), amount, language)

    async def purchase_account(
        self,
        bot: Bot,
        telegram_user: TelegramUser,
        *,
        account_id: int,
        checkout_chat_id: int | None = None,
        checkout_message_id: int | None = None,
    ) -> PurchaseResult:
        if catalog_sync_service.are_sales_temporarily_blocked():
            raise PaymentUnavailableError("Catalog synchronization is in progress.")
        if not catalog_sync_service.is_configured():
            raise PaymentUnavailableError("LZT integration is not configured.")

        async with async_session_factory() as session:
            account = await CatalogAccountRepository(session).get_by_id(account_id)
            await session.commit()
        if account is None:
            raise AccountUnavailableError("Account is no longer available.")
        if not await self._bot_settings_service.is_sales_enabled(GameAccountType(account.game_type)):
            raise PaymentUnavailableError("Sales are disabled for this game category.")

        try:
            refreshed = await catalog_sync_service.refresh_account(local_account_id=account_id)
        except (LztConfigurationError, LztSyncError) as error:
            raise AccountValidationError("Unable to validate account.") from error
        if refreshed.deleted:
            raise AccountValidationError("Account is no longer available.")

        language, transaction, use_balance = await self._reserve_purchase(
            telegram_user,
            account_id=account_id,
            checkout_chat_id=checkout_chat_id,
            checkout_message_id=checkout_message_id,
        )
        if use_balance:
            try:
                delivery_text = await self._fulfill_purchase(transaction.id)
            except Exception as error:
                logger.exception("Balance purchase fulfillment failed transaction_id=%s", transaction.id)
                await self._rollback_balance_purchase(transaction.id, str(error))
                await self._transaction_service.notify_admins_about_failed_transaction(bot, transaction.id)
                await self._transaction_service.notify_admins_about_purchase_fulfillment_error(
                    bot,
                    transaction_id=transaction.id,
                    error=error,
                )
                if isinstance(error, AccountPriceChangedError):
                    raise
                raise AccountPurchaseFulfillmentError("Unable to complete purchase.") from error
            await self._transaction_service.notify_admins_about_completed_transaction(bot, transaction.id)
            return PurchaseResult(
                completed=True,
                transaction_id=transaction.id,
                payment_url=None,
                language=language,
                payment_amount=Decimal("0.00"),
                balance_amount=_to_money(transaction.balance_amount),
                delivery_text=delivery_text,
            )

        try:
            provider_response = await self._platega_client.create_payment_link(
                amount=_transaction_payment_amount(transaction),
                description=f"Покупка аккаунта WOT SHOP #{account_id}",
                payload=f"purchase:{transaction.id}",
                telegram_user=telegram_user,
            )
            await self._set_provider_data(transaction.id, provider_response.transaction_id, str(provider_response.payment_url))
            await self._transaction_service.notify_admins_about_started_transaction(bot, transaction.id)
        except Exception as error:
            await self._release_purchase_transaction(transaction.id, reason=str(error))
            raise
        return PurchaseResult(
            completed=False,
            transaction_id=transaction.id,
            payment_url=str(provider_response.payment_url),
            language=language,
            payment_amount=_transaction_payment_amount(transaction),
            balance_amount=_to_money(transaction.balance_amount),
        )

    async def handle_callback(self, bot: Bot, payload: PlategaCallbackPayload) -> None:
        if payload.currency.upper() != "RUB":
            logger.warning("Ignoring Platega callback with unsupported currency=%s", payload.currency)
            return
        async with async_session_factory() as session:
            users = UserRepository(session)
            transactions = TransactionRepository(session)
            transaction = await transactions.get_by_provider_transaction_id(payload.transaction_id)
            if transaction is None:
                await session.commit()
                logger.warning("Platega callback transaction not found provider_transaction_id=%s", payload.transaction_id)
                return
            if transaction.status == TransactionStatus.COMPLETED.value:
                await session.commit()
                return
            expected_amount = _transaction_payment_amount(transaction)
            received_amount = _to_money(payload.amount)
            # Platega can include a payment-method fee in callback.amount when
            # the fee is paid by the customer. The bot credits only the local
            # invoice amount requested by the user; a lower payment is invalid.
            if received_amount < expected_amount:
                failure_reason = (
                    "Platega callback amount is lower than the invoice: "
                    f"expected={expected_amount}, received={received_amount}."
                )
                await transactions.mark_failed(transaction, reason=failure_reason)
                await self._refund_balance_contribution(session, transaction, users=users)
                account_id = transaction.catalog_account_id
                user_id = transaction.user_id
                await session.commit()
                await self._release_account_reservation(account_id, user_id)
                logger.error(
                    "Platega payment amount is lower than invoice transaction_id=%s provider_transaction_id=%s "
                    "expected_amount=%s received_amount=%s currency=%s status=%s",
                    transaction.id,
                    payload.transaction_id,
                    expected_amount,
                    received_amount,
                    payload.currency,
                    payload.status,
                )
                return
            status = payload.status.upper()
            if status == "CONFIRMED":
                if transaction.type == TransactionType.TOP_UP.value:
                    users = UserRepository(session)
                    user = await users.get_by_id(transaction.user_id)
                    if user is None:
                        await transactions.mark_failed(transaction, reason="User not found.")
                        await session.commit()
                        return
                    await users.credit_balance(user, _to_money(transaction.amount))
                    await transactions.mark_completed(transaction)
                    transaction_id = transaction.id
                    user_telegram_id = user.telegram_id
                    language = Language(user.language)
                    amount = _to_money(transaction.amount)
                    await session.commit()
                    await self._transaction_service.notify_admins_about_completed_transaction(bot, transaction_id)
                    await self._notify_user_top_up(bot, user_telegram_id, amount, language)
                    return
                started = await transactions.mark_processing(transaction, payment_method=payload.payment_method)
                transaction_id = transaction.id
                provider_transaction_id = transaction.provider_transaction_id
                await session.commit()
                if started:
                    self._start_fulfillment_task(bot, transaction_id)
                return
            if status in {"CANCELED", "CHARGEBACKED"}:
                if transaction.status in {
                    TransactionStatus.COMPLETED.value,
                    TransactionStatus.PROCESSING.value,
                    TransactionStatus.CANCELED.value,
                }:
                    logger.warning("Received late Platega status=%s for transaction_id=%s", status, transaction.id)
                    await session.commit()
                    return
                await transactions.mark_canceled(transaction)
                await self._refund_balance_contribution(session, transaction, users=users)
                account_id = transaction.catalog_account_id
                user_id = transaction.user_id
                telegram_id = transaction.user.telegram_id
                language = Language(transaction.user.language)
                transaction_id = transaction.id
                provider_transaction_id = transaction.provider_transaction_id
                await session.commit()
                await self._release_account_reservation(account_id, user_id)
                await self._transaction_service.notify_admins_about_canceled_transaction(bot, transaction_id)
                await self._notify_user_payment_canceled(
                    bot,
                    telegram_id,
                    language,
                    provider_transaction_id or str(transaction_id),
                )

    async def shutdown(self) -> None:
        if self._recovery_task is not None:
            self._recovery_task.cancel()
            await asyncio.gather(self._recovery_task, return_exceptions=True)
            self._recovery_task = None
        tasks = tuple(self._fulfillment_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._fulfillment_tasks.clear()

    async def _create_pending_transaction(self, telegram_user: TelegramUser, *, transaction_type: TransactionType, amount: Decimal, description: str) -> tuple[Language, Transaction]:
        async with async_session_factory() as session:
            users = UserRepository(session)
            transactions = TransactionRepository(session)
            user = await users.get_by_telegram_id_for_update(telegram_user.id)
            if user is None:
                user = await users.get_or_create_from_telegram(telegram_user)
            transaction = await transactions.create(
                user_id=user.id,
                transaction_type=transaction_type,
                status=TransactionStatus.PENDING,
                amount=amount,
                description=description,
                provider_name="platega",
            )
            await session.commit()
        return Language(user.language), transaction

    async def _reserve_purchase(
        self,
        telegram_user: TelegramUser,
        *,
        account_id: int,
        checkout_chat_id: int | None = None,
        checkout_message_id: int | None = None,
    ) -> tuple[Language, Transaction, bool]:
        async with async_session_factory() as session:
            users = UserRepository(session)
            accounts = CatalogAccountRepository(session)
            transactions = TransactionRepository(session)
            user = await users.get_by_telegram_id_for_update(telegram_user.id)
            if user is None:
                user = await users.get_or_create_from_telegram(telegram_user)
            account = await accounts.get_by_id_for_update(account_id)
            if account is None or account.status != CatalogAccountStatus.AVAILABLE.value:
                await session.rollback()
                raise AccountUnavailableError("Account is no longer available.")
            if not await accounts.reserve(account, user_id=user.id):
                await session.rollback()
                raise AccountUnavailableError("Account is no longer available.")
            total_amount = _to_money(account.sale_price)
            balance_amount = min(_to_money(user.balance), total_amount)
            external_amount = total_amount - balance_amount
            use_balance = external_amount == Decimal("0.00")
            if balance_amount > 0 and not await users.debit_balance(user, balance_amount):
                await session.rollback()
                raise PaymentError("Insufficient balance.")
            transaction = await transactions.create(
                user_id=user.id,
                transaction_type=TransactionType.PURCHASE,
                status=TransactionStatus.PENDING,
                amount=total_amount,
                balance_amount=balance_amount,
                payment_amount=external_amount,
                catalog_account_id=account.id,
                description=f"Purchase account #{account.id}",
                provider_name="balance" if use_balance else "platega",
                checkout_chat_id=checkout_chat_id,
                checkout_message_id=checkout_message_id,
            )
            await session.commit()
        if use_balance and self._bot is not None:
            await self._transaction_service.notify_admins_about_started_transaction(self._bot, transaction.id)
        return Language(user.language), transaction, use_balance

    async def _resume_processing_purchases(self, bot: Bot) -> None:
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            processing_transactions = await transactions.list_all_by_status(TransactionStatus.PROCESSING)
            transaction_ids = [
                transaction.id
                for transaction in processing_transactions
                if transaction.type == TransactionType.PURCHASE.value
            ]
            await session.commit()
        for transaction_id in transaction_ids:
            self._start_fulfillment_task(bot, transaction_id)
        if transaction_ids:
            logger.info("Resumed %s processing purchases after startup", len(transaction_ids))

    async def _set_provider_data(self, transaction_id: int, provider_transaction_id: str, payment_url: str) -> None:
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            if transaction is None:
                await session.rollback()
                raise PaymentError("Local transaction not found.")
            await transactions.set_provider_data(transaction, provider_transaction_id=provider_transaction_id, payment_url=payment_url)
            await session.commit()

    def _start_fulfillment_task(self, bot: Bot, transaction_id: int) -> None:
        task = self._fulfillment_tasks.get(transaction_id)
        if task is not None and not task.done():
            return
        task = asyncio.create_task(self._run_fulfillment(bot, transaction_id))
        self._fulfillment_tasks[transaction_id] = task
        task.add_done_callback(lambda _: self._fulfillment_tasks.pop(transaction_id, None))

    async def _run_fulfillment(self, bot: Bot, transaction_id: int) -> None:
        try:
            delivery_text = await self._fulfill_purchase(transaction_id)
        except Exception as error:
            logger.exception("Purchase fulfillment failed transaction_id=%s", transaction_id)
            await self._release_purchase_transaction(
                transaction_id,
                reason=str(error),
                refund_external_payment=True,
            )
            await self._transaction_service.notify_admins_about_failed_transaction(bot, transaction_id)
            await self._transaction_service.notify_admins_about_purchase_fulfillment_error(
                bot,
                transaction_id=transaction_id,
                error=error,
            )
            refresh_result = error.refresh_result if isinstance(error, AccountPriceChangedError) else None
            await self._notify_user_purchase_failed(bot, transaction_id, refresh_result=refresh_result)
            return
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            if transaction is None:
                return
            telegram_id = transaction.user.telegram_id
            language = Language(transaction.user.language)
            checkout_chat_id = transaction.checkout_chat_id
            checkout_message_id = transaction.checkout_message_id
            await session.commit()
        await self._transaction_service.notify_admins_about_completed_transaction(bot, transaction_id)
        await self._notify_user_purchase(
            bot,
            telegram_id,
            language,
            transaction_id,
            delivery_text,
            checkout_chat_id=checkout_chat_id,
            checkout_message_id=checkout_message_id,
        )

    async def _fulfill_purchase(self, transaction_id: int) -> str | None:
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            accounts = CatalogAccountRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            account = await accounts.get_by_id_for_update(transaction.catalog_account_id or 0) if transaction else None
            if transaction is None or account is None or account.status != CatalogAccountStatus.RESERVED.value:
                await session.rollback()
                raise AccountUnavailableError("Reserved account not found.")
            supplier_item_id = account.supplier_item_id
            supplier_price = _to_money(account.supplier_price)
            snapshot = _account_snapshot(account)
            await session.commit()
        client = catalog_sync_service.create_client()
        try:
            confirm_buy_payload = await client.confirm_buy(
                supplier_item_id,
                price=supplier_price,
            )
        except (LztApiResponseError, LztConfigurationError, LztSyncError) as error:
            if isinstance(error, LztApiResponseError) and _is_supplier_price_changed_error(error):
                new_supplier_price = _extract_supplier_price_from_error(error)
                if new_supplier_price is None:
                    raise AccountUnavailableError("Unable to read updated supplier price.") from error
                refresh_result = await catalog_sync_service.refresh_account_supplier_price(
                    local_account_id=transaction.catalog_account_id or 0,
                    supplier_price=new_supplier_price,
                )
                if not refresh_result.deleted and not refresh_result.changed:
                    logger.info(
                        "Supplier price changed without public price change; retrying confirm-buy "
                        "transaction_id=%s supplier_item_id=%s price=%s",
                        transaction_id,
                        supplier_item_id,
                        new_supplier_price,
                    )
                    try:
                        confirm_buy_payload = await client.confirm_buy(
                            supplier_item_id,
                            price=new_supplier_price,
                        )
                    except (LztApiResponseError, LztConfigurationError, LztSyncError) as retry_error:
                        raise AccountUnavailableError("LZT Fast Buy retry failed.") from retry_error
                else:
                    # If the recalculated selling price no longer covers the new
                    # supplier price, refresh removes the item. Keep the actual
                    # supplier reason private and show the established safe text.
                    if refresh_result.deleted:
                        refresh_result = replace(refresh_result, deletion_reason="invalid_credentials")
                    raise AccountPriceChangedError(refresh_result) from error
            else:
                raise AccountUnavailableError("LZT Fast Buy failed.") from error
        try:
            managed_item_payload = await client.get_managed_item(supplier_item_id)
        except (LztApiResponseError, LztConfigurationError, LztSyncError):
            # Fast Buy already succeeded. A follow-up read must not turn it into a failed order.
            logger.warning("Unable to load purchased LZT item transaction_id=%s", transaction_id, exc_info=True)
            managed_item_payload = {}
        fulfillment_payload = {
            "confirm_buy": confirm_buy_payload,
            "managed_item": managed_item_payload,
        }
        delivery_data = _extract_delivery_data(managed_item_payload, confirm_buy_payload)
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            accounts = CatalogAccountRepository(session)
            orders = OrderRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            account = await accounts.get_by_id_for_update(transaction.catalog_account_id or 0) if transaction else None
            if transaction is None or account is None:
                await session.rollback()
                raise PaymentError("Purchase state disappeared.")
            if transaction.status == TransactionStatus.COMPLETED.value:
                await session.commit()
                return _render_delivery_text(delivery_data, Language(transaction.user.language))
            delivery_text = _render_delivery_text(delivery_data, Language(transaction.user.language))
            order = await orders.create(
                user_id=transaction.user_id,
                sale_amount=_to_money(transaction.amount),
                supplier_amount=supplier_price,
                catalog_account_id=account.id,
                supplier_item_id=supplier_item_id,
                account_snapshot=snapshot,
                fulfillment_payload=fulfillment_payload,
                delivery_data=delivery_data,
                description=transaction.description,
            )
            await accounts.mark_sold(account)
            await transactions.mark_completed(transaction, order_id=order.id)
            await session.commit()
        return delivery_text

    async def _rollback_balance_purchase(self, transaction_id: int, reason: str) -> None:
        async with async_session_factory() as session:
            users = UserRepository(session)
            transactions = TransactionRepository(session)
            accounts = CatalogAccountRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            if transaction is None:
                await session.commit()
                return
            await self._refund_balance_contribution(session, transaction, users=users)
            account = await accounts.get_by_id_for_update(transaction.catalog_account_id or 0)
            if account is not None:
                await accounts.release_reservation(account, user_id=transaction.user_id)
            await transactions.mark_failed(transaction, reason=reason)
            await session.commit()

    async def _release_purchase_transaction(
        self,
        transaction_id: int,
        *,
        reason: str,
        refund_external_payment: bool = False,
    ) -> None:
        async with async_session_factory() as session:
            users = UserRepository(session)
            transactions = TransactionRepository(session)
            accounts = CatalogAccountRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            if transaction is None:
                await session.commit()
                return
            account = await accounts.get_by_id_for_update(transaction.catalog_account_id or 0)
            if account is not None:
                await accounts.release_reservation(account, user_id=transaction.user_id)
            await self._refund_balance_contribution(session, transaction, users=users)
            if refund_external_payment:
                await self._refund_external_payment(session, transaction, users=users)
            await transactions.mark_failed(transaction, reason=reason)
            await session.commit()

    async def _release_account_reservation(self, account_id: int | None, user_id: int) -> None:
        if account_id is None:
            return
        async with async_session_factory() as session:
            accounts = CatalogAccountRepository(session)
            account = await accounts.get_by_id_for_update(account_id)
            if account is not None:
                await accounts.release_reservation(account, user_id=user_id)
            await session.commit()

    async def _refund_balance_contribution(
        self,
        session,
        transaction: Transaction,
        *,
        users: UserRepository | None = None,
    ) -> None:
        if transaction.balance_amount <= 0 or transaction.balance_refunded_at is not None:
            return

        users = users or UserRepository(session)
        user = await users.get_by_id(transaction.user_id)
        if user is not None:
            await users.credit_balance(user, _to_money(transaction.balance_amount))
        transaction.balance_refunded_at = datetime.now(UTC)
        await session.flush()

    async def _refund_external_payment(
        self,
        session,
        transaction: Transaction,
        *,
        users: UserRepository | None = None,
    ) -> None:
        """Credit a confirmed Platega payment exactly once after failed delivery."""
        if transaction.payment_amount <= 0 or transaction.payment_refunded_at is not None:
            return

        users = users or UserRepository(session)
        user = await users.get_by_id(transaction.user_id)
        if user is not None:
            await users.credit_balance(user, _to_money(transaction.payment_amount))
        transaction.payment_refunded_at = datetime.now(UTC)
        await session.flush()

    async def _fail_transaction(self, transaction_id: int, reason: str) -> None:
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            if transaction is not None:
                await transactions.mark_failed(transaction, reason=reason)
            await session.commit()

    async def _notify_user_top_up(self, bot: Bot, telegram_id: int, amount: Decimal, language: Language) -> None:
        try:
            await bot.send_message(telegram_id, translate(language, "payment_top_up_completed", amount=_format_money(amount)))
        except TelegramAPIError:
            logger.warning("Failed to notify user telegram_id=%s about top-up", telegram_id)

    async def _notify_user_payment_canceled(
        self,
        bot: Bot,
        telegram_id: int,
        language: Language,
        provider_transaction_id: str,
    ) -> None:
        try:
            await bot.send_message(
                telegram_id,
                translate(language, "payment_canceled", transaction_id=provider_transaction_id),
            )
        except TelegramAPIError:
            logger.warning("Failed to notify user telegram_id=%s about canceled payment", telegram_id)

    async def _notify_user_purchase(
        self,
        bot: Bot,
        telegram_id: int,
        language: Language,
        transaction_id: int,
        delivery_text: str | None,
        *,
        checkout_chat_id: int | None,
        checkout_message_id: int | None,
    ) -> None:
        try:
            text = translate(language, "payment_purchase_completed", transaction_id=transaction_id)
            if delivery_text:
                text = f"{text}\n\n{delivery_text}"
            if checkout_chat_id is not None and checkout_message_id is not None:
                await bot.edit_message_media(
                    chat_id=checkout_chat_id,
                    message_id=checkout_message_id,
                    media=InputMediaPhoto(
                        media=resolve_photo_input(CATALOG_ACCOUNT_SCREEN_MEDIA),
                        caption=text,
                    ),
                    reply_markup=build_purchase_completed_markup(language),
                )
                return
            await bot.send_message(
                telegram_id,
                text,
                reply_markup=build_purchase_completed_markup(language),
            )
        except TelegramAPIError:
            logger.warning("Failed to notify user telegram_id=%s about purchase", telegram_id)

    async def _notify_user_purchase_failed(
        self,
        bot: Bot,
        transaction_id: int,
        *,
        refresh_result: CatalogRefreshResult | None = None,
    ) -> None:
        async with async_session_factory() as session:
            transactions = TransactionRepository(session)
            transaction = await transactions.get_by_id(transaction_id)
            if transaction is None:
                return
            telegram_id = transaction.user.telegram_id
            language = Language(transaction.user.language)
            checkout_chat_id = transaction.checkout_chat_id
            checkout_message_id = transaction.checkout_message_id
            await session.commit()
        try:
            text = (
                render_catalog_refresh_result_text(language, refresh_result)
                if refresh_result is not None
                else translate(language, "payment_purchase_fulfillment_failed")
            )
            if checkout_chat_id is not None and checkout_message_id is not None:
                await bot.edit_message_media(
                    chat_id=checkout_chat_id,
                    message_id=checkout_message_id,
                    media=InputMediaPhoto(
                        media=resolve_photo_input(CATALOG_ACCOUNT_SCREEN_MEDIA),
                        caption=text,
                    ),
                    reply_markup=build_payment_purchase_failed_markup(language),
                )
                return
            await bot.send_message(
                telegram_id,
                text,
                reply_markup=build_payment_purchase_failed_markup(language),
            )
        except TelegramAPIError:
            logger.warning("Failed to notify user telegram_id=%s about purchase failure", telegram_id)


def _parse_amount(raw_value: str) -> Decimal:
    try:
        normalized_value = raw_value.strip().replace(",", ".")
        amount = Decimal(normalized_value)
    except (InvalidOperation, AttributeError) as error:
        raise PaymentError("Invalid amount.") from error
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise PaymentError("Top-up amount must be an integer.")
    return amount.to_integral_value()


def _to_money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _transaction_payment_amount(transaction: Transaction) -> Decimal:
    return _to_money(transaction.payment_amount)


def _format_money(value: Decimal) -> str:
    value = _to_money(value)
    return str(int(value)) if value == value.to_integral() else f"{value:.2f}"


def _is_supplier_price_changed_error(error: LztApiResponseError) -> bool:
    raw_errors = error.payload.get("errors")
    return isinstance(raw_errors, list) and any(
        isinstance(item, str) and "цена на аккаунт изменилась" in item.lower()
        for item in raw_errors
    )


def _extract_supplier_price_from_error(error: LztApiResponseError) -> Decimal | None:
    raw_errors = error.payload.get("errors")
    if not isinstance(raw_errors, list):
        return None
    for item in raw_errors:
        if not isinstance(item, str):
            continue
        match = re.search(r"сейчас\s+аккаунт\s+стоит\s+([\d.,]+)", item, flags=re.IGNORECASE)
        if match is None:
            continue
        try:
            return _to_money(Decimal(match.group(1).rstrip(".,").replace(",", ".")))
        except InvalidOperation:
            continue
    return None


def _account_snapshot(account: CatalogAccount) -> dict[str, object]:
    return {
        "account_id": account.id,
        "game_type": account.game_type,
        "region": account.region or "",
        "supplier_item_id": account.supplier_item_id,
        "sale_price": str(account.sale_price),
        "created_at": datetime.now(UTC).isoformat(),
    }


def _extract_delivery_data(*payloads: dict[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    key_aliases = {
        "login": "login",
        "username": "login",
        "account_login": "login",
        "password": "password",
        "account_password": "password",
        "email": "email",
        "email_password": "email_password",
    }
    for payload in payloads:
        for source in _delivery_sources(payload):
            for key, field in key_aliases.items():
                value = source.get(key)
                if isinstance(value, str) and value.strip() and field not in values:
                    values[field] = value.strip()
    return values


def _render_delivery_text(delivery_data: dict[str, str], language: Language) -> str | None:
    if not delivery_data:
        return None
    labels = {
        "login": "payment_credentials_login",
        "password": "payment_credentials_password",
        "email": "payment_credentials_email",
        "email_password": "payment_credentials_email_password",
    }
    return "\n".join(
        translate(language, labels[field], value=escape(value))
        for field, value in delivery_data.items()
        if field in labels
    )


def _delivery_sources(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    sources = [payload]
    item = payload.get("item")
    if isinstance(item, dict):
        sources.append(item)
    for source in tuple(sources):
        for nested_key in ("data", "account", "loginData"):
            nested = source.get(nested_key)
            if isinstance(nested, dict):
                sources.append(nested)
    return tuple(sources)

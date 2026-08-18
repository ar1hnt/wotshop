from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models.transaction import Transaction, TransactionStatus, TransactionType


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        transaction_type: TransactionType,
        status: TransactionStatus,
        amount: Decimal,
        balance_amount: Decimal = Decimal("0.00"),
        payment_amount: Decimal | None = None,
        currency: str = "RUB",
        order_id: int | None = None,
        catalog_account_id: int | None = None,
        description: str | None = None,
        provider_name: str | None = None,
        provider_transaction_id: str | None = None,
        payment_url: str | None = None,
        provider_payment_method: int | None = None,
        completed_at: datetime | None = None,
        canceled_at: datetime | None = None,
        checkout_chat_id: int | None = None,
        checkout_message_id: int | None = None,
    ) -> Transaction:
        transaction = Transaction(
            user_id=user_id,
            order_id=order_id,
            catalog_account_id=catalog_account_id,
            type=transaction_type.value,
            status=status.value,
            balance_amount=balance_amount,
            amount=amount,
            payment_amount=amount if payment_amount is None else payment_amount,
            currency=currency,
            description=description,
            provider_name=provider_name,
            provider_transaction_id=provider_transaction_id,
            payment_url=payment_url,
            provider_payment_method=provider_payment_method,
            completed_at=completed_at,
            canceled_at=canceled_at,
            checkout_chat_id=checkout_chat_id,
            checkout_message_id=checkout_message_id,
        )
        self.session.add(transaction)
        await self.session.flush()
        return transaction

    async def get_by_provider_transaction_id(self, provider_transaction_id: str) -> Transaction | None:
        query = (
            select(Transaction)
            .options(selectinload(Transaction.user), selectinload(Transaction.order))
            .where(Transaction.provider_transaction_id == provider_transaction_id)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def set_provider_data(
        self,
        transaction: Transaction,
        *,
        provider_transaction_id: str,
        payment_url: str,
    ) -> None:
        transaction.provider_transaction_id = provider_transaction_id
        transaction.payment_url = payment_url
        await self.session.flush()

    async def set_checkout_message(
        self,
        transaction: Transaction,
        *,
        chat_id: int,
        message_id: int,
    ) -> None:
        transaction.checkout_chat_id = chat_id
        transaction.checkout_message_id = message_id
        await self.session.flush()

    async def mark_completed(self, transaction: Transaction, *, order_id: int | None = None) -> Transaction:
        transaction.status = TransactionStatus.COMPLETED.value
        transaction.order_id = order_id
        transaction.completed_at = datetime.now(UTC)
        transaction.failure_reason = None
        await self.session.flush()
        return transaction

    async def mark_processing(self, transaction: Transaction, *, payment_method: int | None = None) -> bool:
        if transaction.status != TransactionStatus.PENDING.value:
            return False
        transaction.status = TransactionStatus.PROCESSING.value
        transaction.provider_payment_method = payment_method
        await self.session.flush()
        return True

    async def mark_failed(self, transaction: Transaction, *, reason: str) -> Transaction:
        transaction.status = TransactionStatus.FAILED.value
        transaction.failure_reason = reason[:4000]
        await self.session.flush()
        return transaction

    async def get_by_id(self, transaction_id: int) -> Transaction | None:
        query = (
            select(Transaction)
            .options(
                selectinload(Transaction.user),
                selectinload(Transaction.order),
            )
            .where(Transaction.id == transaction_id)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_by_status(self, status: TransactionStatus) -> int:
        query = select(func.count(Transaction.id)).where(self._status_condition(status))
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def get_page_by_status(
        self,
        *,
        status: TransactionStatus,
        page: int,
        page_size: int,
    ) -> tuple[list[Transaction], int]:
        total_query = select(func.count(Transaction.id)).where(self._status_condition(status))
        total_result = await self.session.execute(total_query)
        total_count = int(total_result.scalar_one())

        query = (
            select(Transaction)
            .options(
                selectinload(Transaction.user),
                selectinload(Transaction.order),
            )
            .where(self._status_condition(status))
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        return list(result.scalars()), total_count

    async def list_all_by_status(self, status: TransactionStatus) -> list[Transaction]:
        query = (
            select(Transaction)
            .options(
                selectinload(Transaction.user),
                selectinload(Transaction.order),
            )
            .where(Transaction.status == status.value)
            .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars())

    async def list_expired_pending(self, *, before: datetime) -> list[Transaction]:
        query = (
            select(Transaction)
            .options(selectinload(Transaction.user), selectinload(Transaction.order))
            .where(Transaction.status == TransactionStatus.PENDING.value)
            .where(Transaction.created_at < before)
            .order_by(Transaction.id.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars())

    @staticmethod
    def _status_condition(status: TransactionStatus):
        if status == TransactionStatus.PENDING:
            # "Pending" in the admin panel is an operational queue: it includes
            # transactions that require a manual check after a failed callback.
            return Transaction.status.in_(
                (
                    TransactionStatus.PENDING.value,
                    TransactionStatus.PROCESSING.value,
                    TransactionStatus.FAILED.value,
                )
            )
        return Transaction.status == status.value

    async def mark_canceled(self, transaction: Transaction) -> Transaction:
        transaction.status = TransactionStatus.CANCELED.value
        transaction.canceled_at = datetime.now(UTC)
        await self.session.flush()
        return transaction

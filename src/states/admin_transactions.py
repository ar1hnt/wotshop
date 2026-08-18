from aiogram.fsm.state import State, StatesGroup


class AdminTransactionState(StatesGroup):
    waiting_for_completed_transaction_id = State()

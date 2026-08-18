from aiogram.fsm.state import State, StatesGroup


class CatalogFilterState(StatesGroup):
    waiting_for_value = State()


class PaymentState(StatesGroup):
    waiting_for_top_up_amount = State()

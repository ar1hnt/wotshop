from aiogram.fsm.state import State, StatesGroup


class AdminProductState(StatesGroup):
    waiting_for_product_id = State()

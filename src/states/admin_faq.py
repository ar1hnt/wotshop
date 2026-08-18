from aiogram.fsm.state import State, StatesGroup


class AdminFaqState(StatesGroup):
    waiting_for_text = State()

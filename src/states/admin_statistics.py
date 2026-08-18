from aiogram.fsm.state import State, StatesGroup


class AdminStatisticsState(StatesGroup):
    waiting_for_custom_period = State()

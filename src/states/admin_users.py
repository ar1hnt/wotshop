from aiogram.fsm.state import State, StatesGroup


class AdminBroadcastState(StatesGroup):
    waiting_for_content = State()
    waiting_for_confirmation = State()


class AdminUserLookupState(StatesGroup):
    waiting_for_identifier_value = State()
    waiting_for_balance = State()


class AdminDatabaseBackupState(StatesGroup):
    waiting_for_password = State()

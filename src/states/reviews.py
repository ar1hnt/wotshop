from aiogram.fsm.state import State, StatesGroup


class ReviewCreationState(StatesGroup):
    waiting_for_text = State()


class AdminReviewModerationState(StatesGroup):
    waiting_for_rejection_reason = State()

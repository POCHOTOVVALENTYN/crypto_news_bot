from aiogram.fsm.state import State, StatesGroup


class UserState(StatesGroup):
    """Состояния пользовательских взаимодействий"""
    chatting_with_ai = State()  # Активный разговор с AI
    waiting_for_payment = State()  # Ожидание подтверждения оплаты

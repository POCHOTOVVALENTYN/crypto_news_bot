from aiogram.fsm.state import State, StatesGroup


class UserState(StatesGroup):
    """Состояния пользовательских взаимодействий"""
    chatting_with_ai = State()  # Активный разговор с AI
    waiting_for_payment = State()  # Ожидание подтверждения оплаты
    uploading_story = State()  # Загрузка скриншота Instagram Stories


class SupportState(StatesGroup):
    """Состояния поддержки (Relay Mode)"""
    waiting_for_message = State()  # Ожидает сообщение пользователя
    active_session = State()  # Активная сессия с админом
    admin_responding = State()  # Админ печатает ответ


class ConsultationState(StatesGroup):
    """Состояния планирования консультации"""
    viewing_offer = State()  # Просмотр предложения
    confirming_payment = State()  # Подтверждение оплаты
    awaiting_payment = State()  # Ожидание оплаты
    discussing_with_admin = State()  # Обсуждение с админом (Relay Mode)
    selecting_date = State()  # Выбор даты
    selecting_time = State()  # Выбор времени
    confirming_meeting = State()  # Подтверждение встречи


class PriceNegotiationState(StatesGroup):
    """Состояния переговоров о цене Premium"""
    viewing_base_offer = State()  # Просмотр базового предложения
    checking_subscriptions = State()  # Проверка подписок
    viewing_discount_offer = State()  # Просмотр предложения со скидкой
    requesting_custom_price = State()  # Запрос индивидуальной цены
    discussing_with_admin = State()  # Обсуждение цены (Relay Mode)
    admin_setting_price = State()  # Админ устанавливает цену
    admin_entering_price = State()  # Админ вводит сумму (новое)
    awaiting_custom_payment = State()  # Ожидание оплаты кастомной суммы

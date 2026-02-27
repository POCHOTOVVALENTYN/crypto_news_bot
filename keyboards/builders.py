from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_premium_offer_keyboard(price: int = 500):
    """Первичный оффер с воронкой продаж"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💳 Оплатить {price} ⭐️",
            callback_data=f"pay_premium:{price}"
        )],
        [InlineKeyboardButton(
            text="💭 Для меня дороговато. Что делать?",
            callback_data="price_too_high"
        )]
    ])


def build_discount_offer_keyboard():
    """Скидочный оффер (после возражения)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Оплатить 400 ⭐️",
            callback_data="pay_premium:400"
        )],
        [InlineKeyboardButton(
            text="❌ Всё равно дорого",
            callback_data="reject_premium"
        )]
    ])


def build_exit_ai_keyboard():
    """Кнопка выхода из AI-чата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Выйти из AI-чата",
            callback_data="exit_ai_chat"
        )]
    ])


def build_dismiss_keyboard(label: str = "✅ Понятно, спасибо!") -> InlineKeyboardMarkup:
    """
    Универсальная кнопка закрытия инфо-сообщения.
    Единый callback dismiss_info_msg используется одним хендлером для всех экранов.
    """
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data="dismiss_info_msg")
    ]])


def build_cta_dismiss_keyboard(
    cta_text: str,
    cta_data: str,
    dismiss_label: str = "✅ Понятно!"
) -> InlineKeyboardMarkup:
    """
    Клавиатура: CTA-кнопка (действие) + кнопка закрытия.
    Используется на экранах где важно предложить следующий шаг.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=cta_text, callback_data=cta_data)],
        [InlineKeyboardButton(text=dismiss_label, callback_data="dismiss_info_msg")]
    ])


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

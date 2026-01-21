from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_free_menu():
    """Клавиатура для бесплатных пользователей"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌟 Получить Premium-доступ")],
            [
                KeyboardButton(text="🎁 Что внутри Premium?"),
                KeyboardButton(text="📚 Наши ресурсы")
            ],
            [
                KeyboardButton(text="👨‍💻 Об Авторе"),
                KeyboardButton(text="📞 Поддержка")
            ]
        ],
        resize_keyboard=True
    )


def get_premium_menu():
    """Клавиатура для Premium пользователей"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🤖 Мой AI-клон-Аналитик")],
            [KeyboardButton(text="🚀 Сигналы (Futures)")],
            [KeyboardButton(text="🎓 Обучающий Курс")],
            [KeyboardButton(text="⚙️ Мой Аккаунт")],
            [KeyboardButton(text="👑 Поддержка")]
        ],
        resize_keyboard=True
    )

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import ADMIN_IDS


def get_free_menu(user_id: int = None) -> ReplyKeyboardMarkup:
    """Клавиатура для обычных пользователей"""
    keyboard = [
        [KeyboardButton(text="🌟 Получить Premium-доступ")],
        [
            KeyboardButton(text="🎁 Что внутри Premium?"),
            KeyboardButton(text="📚 Наши ресурсы")
        ],
        [
            KeyboardButton(text="💰 Разбор Кошелька"),
            KeyboardButton(text="💎 VIP-консультация")
        ],
        [
            KeyboardButton(text="👨‍💻 Об Авторе"),
            KeyboardButton(text="📞 Поддержка")
        ],
        [
            KeyboardButton(text="📎 Пригласить друга"),
            KeyboardButton(text="🎁 Розыгрыш BLEXLER")
        ]
    ]
    
    # Если админ - добавляем кнопку админ-меню
    if user_id and user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="🔙 Админ Меню")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )


def get_giveaway_menu():
    """Клавиатура подменю розыгрыша"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❓ Как участвовать?")],
            [
                KeyboardButton(text="🌳 Мои Рефералы"),
                KeyboardButton(text="📎 Пригласить друга")
            ],
            [
                KeyboardButton(text="📸 Проверить Stories"),
                KeyboardButton(text="📜 История Проверок")
            ],
            [
                KeyboardButton(text="🏆 Топ Участников"),
                KeyboardButton(text="🏅 Мои Достижения")
            ],
            [KeyboardButton(text="🔙 Главное Меню")]
        ],
        resize_keyboard=True
    )


def get_premium_menu(user_id: int = None):
    """Клавиатура для Premium пользователей"""
    keyboard = [
        [KeyboardButton(text="🤖 Мой AI-клон-Аналитик")],
        [KeyboardButton(text="📊 Premium-сигналы")],  # Было: 🚀 Сигналы (Futures)
        [
            KeyboardButton(text="⚙️ Мой Аккаунт"),
            KeyboardButton(text="🆘 Premium-поддержка")  # Было: 👑 Поддержка
        ],
        [
            KeyboardButton(text="💰 Разбор Кошелька"),  # НОВАЯ
            KeyboardButton(text="💎 VIP-консультация")  # Было: 💼 Консультация
        ],
        [
            KeyboardButton(text="📎 Пригласить друга"),
            KeyboardButton(text="🎁 Розыгрыш BLEXLER")
        ]
    ]
    
    # Добавляем кнопку "Админ меню" только для админов
    if user_id and user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="🔙 Админ Меню")])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )


"""
Клавиатуры для иерархического админ-меню
"""
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


# === ГЛАВНОЕ АДМИН МЕНЮ ===

def get_admin_main_menu():
    """Главное админ меню с режимами"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📰 Режим Постинга")],
            [
                KeyboardButton(text="👤 Режим Free User"),
                KeyboardButton(text="👑 Режим Premium User")
            ],
            [
                KeyboardButton(text="🧪 Тестирование Фич"),
                KeyboardButton(text="📊 Dashboard")
            ],
            [
                KeyboardButton(text="📊 Сессии Поддержки"),
                KeyboardButton(text="📅 Консультации")
            ],
            [KeyboardButton(text="⚙️ Настройки Бота")]
        ],
        resize_keyboard=True
    )


# === РЕЖИМ ПОСТИНГА ===

def get_posting_menu():
    """Меню режима постинга"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Создать публикацию")],
            [KeyboardButton(text="📚 Дайджесты")],
            [
                KeyboardButton(text="⚙️ Настройки буфера"),
                KeyboardButton(text="📊 Статистика публикаций")
            ],
            [KeyboardButton(text="🔙 Главное Меню")]
        ],
        resize_keyboard=True
    )


# === МЕНЮ ТЕСТИРОВАНИЯ ===

def get_testing_menu():
    """Меню тестирования фич"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎮 Геймификация"),
                KeyboardButton(text="🌳 MLM Тест")
            ],
            [
                KeyboardButton(text="📸 Stories Тест"),
                KeyboardButton(text="💳 Платежи Тест")
            ],
            [
                KeyboardButton(text="🏅 Бейджи"),
                KeyboardButton(text="📜 История")
            ],
            [KeyboardButton(text="🔙 Главное Меню")]
        ],
        resize_keyboard=True
    )


# === СТАРЫЕ МЕНЮ (для обратной совместимости) ===

def get_main_menu_keyboard():
    """Старое меню постинга (для совместимости)"""
    return get_posting_menu()


def get_cancel_keyboard():
    """Клавиатура отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏠 Главное Меню"),
                KeyboardButton(text="🔙 Назад")
            ]
        ],
        resize_keyboard=True
    )


# === INLINE КНОПКИ ===

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_publication_type_keyboard():
    """Inline кнопки типа публикации"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 С фото", callback_data="pub_type_photo"),
             InlineKeyboardButton(text="📝 Без фото", callback_data="pub_type_text")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ]
    )

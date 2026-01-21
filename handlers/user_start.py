from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
import logging

from database import db
from keyboards.reply import get_free_menu, get_premium_menu

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start - регистрация и выдача меню"""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # Очищаем любые активные состояния
    await state.clear()
    
    # Проверяем/регистрируем пользователя
    user = await db.get_user(user_id)
    if not user:
        # Новый пользователь - регистрируем
        await db.add_user(user_id, username, full_name)
        user = await db.get_user(user_id)
        logger.info(f"🆕 Новый пользователь: {user_id} (@{username})")
    
    # Проверяем подписку
    is_premium = await db.check_subscription(user_id)
    
    if is_premium:
        # Premium пользователь
        await message.answer(
            f"👑 <b>Добро пожаловать, {full_name}!</b>\n\n"
            f"У вас активна <b>Premium-подписка</b>.\n"
            f"Используйте меню ниже для доступа ко всем функциям. 👇",
            parse_mode="HTML",
            reply_markup=get_premium_menu()
        )
    else:
        # Бесплатный пользователь
        await message.answer(
            f"👋 <b>Привет, {full_name}!</b>\n\n"
            f"Добро пожаловать в крипто-бот BLEXLER!\n\n"
            f"📰 Здесь вы можете  подключить Premium-доступ💎 с эксклюзивными функциями\n\n"
            f"Используйте меню ниже 👇",
            parse_mode="HTML",
            reply_markup=get_free_menu()
        )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Помощь"""
    await message.answer(
        "ℹ️ <b>Помощь</b>\n\n"
        "<b>Команды:</b>\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n\n"
        "<b>Для Premium подписчиков:</b>\n"
        "🤖 AI-клон аналитика BLEXLER\n"
        "🚀 Сигналы по фьючерсам\n"
        "📊 Премиум-аналитика\n"
        "💡 Авторские рекомендации\n"
        "🎓 Обучающие материалы",
        parse_mode="HTML"
    )

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import asyncio
import logging

from database import db
from loader import bot
from utils.states import UserState
from utils.message_cleaner import auto_delete, safe_delete
from keyboards.reply import get_premium_menu
from keyboards.builders import build_exit_ai_keyboard
from services.ai.manager import AIProviderManager

router = Router()
logger = logging.getLogger(__name__)

# Инициализация AI Manager
ai_manager = AIProviderManager()

# Системный промпт для клона Валентина
SYSTEM_PROMPT_VALENTIN = """
Ты — цифровой клон трейдера Валентина.

Твоя роль:
- Профессиональный криптотрейдер и аналитик
- Помогаешь анализировать рынок, объясняешь термины
- Даёшь краткие, чёткие ответы (стиль: ёмко, по делу)

Стиль общения:
- Используй профессиональные термины: лонг, шорт, RSI, MACD, уровни поддержки/сопротивления
- Не раздувай ответы, будь конкретен (макс. 3-4 абзаца)
- Всегда добавляй дисклеймер при финансовых рекомендациях: "⚠️ Не финансовый совет, DYOR"
- Общайся на русском языке

Твои принципы:
- Образование важнее быстрой прибыли
- Риск-менеджмент — основа успеха
- Эмоции — враг трейдера

Запрещено:
- Давать гарантии по прибыли ("100% пойдёт вверх")
- Рекомендовать конкретные монеты без анализа
- Быть слишком многословным
- Использовать сленг и мемы (кроме крипто-терминов)
"""


# === ВХОД В AI-ЧАТ ===

@router.message(F.text == "🤖 Мой AI-клон-Аналитик")
async def start_ai_chat(message: Message, state: FSMContext):
    """Запуск AI-чата (только для Premium)"""
    user_id = message.from_user.id
    
    # Проверка Premium
    is_premium = await db.check_subscription(user_id)
    if not is_premium:
        await message.answer(
            "⛔️ <b>Доступ закрыт</b>\n\n"
            "AI-клон аналитика доступен только для Premium подписчиков.\n"
            "Нажмите <b>\"🌟 Получить Premium-доступ\"</b> для подключения",
            parse_mode="HTML"
        )
        return
    
    # Устанавливаем состояние AI-чата
    await state.set_state(UserState.chatting_with_ai)
    
    await message.answer(
        "🤖 <b>AI-клон аналитика Валентина активирован!</b>\n\n"
        "Задавайте мне любые вопросы по криптовалютам, техническому анализу, "
        "стратегиям торговли и рынку в целом.\n\n"
        "Я постараюсь дать вам чёткий и профессиональный ответ.\n\n"
        "💡 <i>Примеры вопросов:</i>\n"
        "• Объясни что такое RSI и как его использовать\n"
        "• Как определить уровни поддержки и сопротивления?\n"
        "• Какие риски при торговле фьючерсами?\n"
        "• Что такое ликвидация в лонг-позиции?\n\n"
        "Для выхода нажмите кнопку ниже 👇",
        parse_mode="HTML",
        reply_markup=build_exit_ai_keyboard()
    )
    
    logger.info(f"🤖 AI-чат запущен: {user_id}")


# === ОБРАБОТКА СООБЩЕНИЙ В AI-ЧАТЕ ===

# Rate limiting для AI-запросов
from collections import defaultdict
from datetime import datetime, timedelta

user_last_requests = defaultdict(list)

@router.message(UserState.chatting_with_ai)
async def handle_ai_message(message: Message, state: FSMContext):
    """Обработка сообщений пользователя в AI-чате"""
    user_id = message.from_user.id
    user_message = message.text
    
    # Проверяем что Premium всё ещё активен
    is_premium = await db.check_subscription(user_id)
    if not is_premium:
        await state.clear()
        await message.answer(
            "⛔️ Ваша Premium-подписка истекла.\n"
            "Продлите подписку для доступа к AI-клону.",
            reply_markup=get_premium_menu()
        )
        return
    
    # 🔒 RATE LIMITING: макс 10 запросов в минуту
    now = datetime.now()
    user_requests = user_last_requests[user_id]
    
    # Удаляем старые запросы (>1 мин)
    user_requests = [t for t in user_requests if now - t < timedelta(minutes=1)]
    
    if len(user_requests) >= 10:
        rate_msg = await message.answer(
            "⏳ Пожалуйста, подождите немного перед следующим вопросом.\n"
            "Лимит: 10 запросов в минуту.",
            reply_markup=build_exit_ai_keyboard()
        )
        asyncio.create_task(auto_delete(bot, rate_msg.chat.id, rate_msg.message_id, delay=20))
        logger.warning(f"⚠️ Rate limit hit for user {user_id}")
        return
    
    user_requests.append(now)
    user_last_requests[user_id] = user_requests
    
    # Показываем индикатор "Думаю..."
    await message.bot.send_chat_action(user_id, "typing")
    thinking_msg = await message.answer("🤔 Анализирую...", reply_markup=None)
    
    try:
        # 💾 Получаем историю разговора
        data = await state.get_data()
        history = data.get('chat_history', [])
        
        # Добавляем сообщение пользователя
        history.append({"role": "user", "content": user_message})
        
        # Формируем контекст из последних 5 сообщений
        context_messages = history[-5:]
        context_prompt = "\n\n".join([
            f"{'User' if msg['role']=='user' else 'Assistant'}: {msg['content']}"
            for msg in context_messages[:-1]  # Все кроме последнего
        ])
        
        # Полный промпт с контекстом
        full_prompt = f"История разговора:\n{context_prompt}\n\nТекущий вопрос User: {user_message}" if context_prompt else user_message
        
        # Отправляем запрос в AI
        response = await ai_manager.generate_text(
            prompt=full_prompt,
            system_prompt=SYSTEM_PROMPT_VALENTIN,
            max_tokens=800  # Ограничиваем длину ответа
        )
        
        if response:
            # Удаляем индикатор "Думаю..." перед самим ответом
            await safe_delete(bot, message.chat.id, thinking_msg.message_id)
            # Добавляем ответ в историю
            history.append({"role": "assistant", "content": response})
            await state.update_data(chat_history=history)
            
            # Отправляем ответ пользователю
            await message.answer(
                response,
                reply_markup=build_exit_ai_keyboard()
            )
            logger.debug(f"🤖 AI ответ отправлен: {user_id} (история: {len(history)} сообщений)")
        else:
            # AI не смог ответить
            await safe_delete(bot, message.chat.id, thinking_msg.message_id)
            err_msg = await message.answer(
                "⚠️ <b>AI временно недоступен</b>\n\n"
                "Все провайдеры сейчас перегружены или недоступны.\n"
                "Попробуйте задать вопрос чуть позже.",
                parse_mode="HTML",
                reply_markup=build_exit_ai_keyboard()
            )
            asyncio.create_task(auto_delete(bot, err_msg.chat.id, err_msg.message_id, delay=20))
            logger.warning(f"⚠️ AI не смог ответить: {user_id}")
            
    except Exception as e:
        logger.error(f"Ошибка AI-чата для {user_id}: {e}", exc_info=True)
        await message.answer(
            "⚠️ Произошла ошибка при обработке вашего запроса.\n"
            "Попробуйте ещё раз или обратитесь в поддержку.",
            reply_markup=build_exit_ai_keyboard()
        )


# === ВЫХОД ИЗ AI-ЧАТА ===

@router.callback_query(F.data == "exit_ai_chat")
async def exit_ai_chat(callback: CallbackQuery, state: FSMContext):
    """Выход из AI-чата"""
    await state.clear()
    
    await callback.message.edit_text(
        "✅ Вы вышли из AI-чата.\n\n"
        "Используйте меню для доступа к другим функциям."
    )
    
    # Отправляем Premium-меню заново
    await callback.message.answer(
        "👑 <b>Premium-меню</b>\n\n"
        "Выберите функцию:",
        parse_mode="HTML",
        reply_markup=get_premium_menu()
    )
    
    await callback.answer()
    logger.info(f"🚪 Выход из AI-чата: {callback.from_user.id}")

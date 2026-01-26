"""
Обработчики Premium-услуг:
- Premium-поддержка (Relay Mode)
- Разбор кошелька (300$)
- VIP-консультация (350$)
- Premium-сигналы
"""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import db
from loader import bot
from config import CONSULTATION_PRICES, ADMIN_NAMES
from services.relay_manager import relay_manager
from utils.states import SupportState, ConsultationState

router = Router()
logger = logging.getLogger(__name__)


# === PREMIUM-ПОДДЕРЖКА ===

@router.message(F.text == "🆘 Premium-поддержка")
async def premium_support(message: Message, state: FSMContext):
    """Запрос Premium-поддержки через Relay Mode"""
    user_id = message.from_user.id
    
    # Проверяем Premium статус
    user = await db.get_user(user_id)
    if not user or user.get('status') != 'premium':
        await message.answer(
            "⚠️ Эта функция доступна только Premium-подписчикам.\n\n"
            "Нажмите \"🌟 Получить Premium-доступ\" для подключения."
        )
        return
    
    # Проверяем, нет ли уже активной сессии
    active_session = await relay_manager.get_active_session(user_id)
    if active_session:
        await message.answer(
            "💬 У вас уже есть активный диалог с поддержкой.\n"
            "Просто продолжайте писать сообщения."
        )
        await state.set_state(SupportState.active_session)
        await state.update_data(session_id=active_session['id'])
        return
    
    # Создаём новую сессию
    await message.answer(
        "🆘 <b>Premium-поддержка</b>\n\n"
        "Подключаем вас к команде BLEXLER...\n"
        "Опишите вашу проблему, и мы ответим в течение 30 минут!",
        parse_mode="HTML"
    )
    
    # Создать Relay сессию
    session_id = await relay_manager.create_session(
        user_id=user_id,
        session_type='premium_support',
        initial_admin_id=304050247  # Основатель
    )
    
    # Установить FSM состояние
    await state.set_state(SupportState.active_session)
    await state.update_data(session_id=session_id)
    
    logger.info(f"🆘 Premium-поддержка запущена для user {user_id}, session {session_id}")


# === РАЗБОР КОШЕЛЬКА ===

@router.message(F.text == "💰 Разбор Кошелька")
async def wallet_review_offer(message: Message, state: FSMContext):
    """Предложение услуги Разбор кошелька - доступно всем"""
    user_id = message.from_user.id
    
    price_info = CONSULTATION_PRICES['wallet_review']
    
    await message.answer(
        "💰 <b>РАЗБОР ВАШЕГО КОШЕЛЬКА</b>\n\n"
        "🔍 <b>Что входит:</b>\n"
        "• Детальный анализ вашего портфеля\n"
        "• Оценка рисков и потенциала каждой монеты\n"
        "• Анализ вашей торговой стратегии\n"
        "• Рекомендации по ребалансировке\n"
        "• Перспективы роста портфеля\n"
        "• Персональный план действий\n\n"
        "👨‍🏫 <b>Кто проводит:</b> BLEXLER лично\n"
        "⏱️ <b>Продолжительность:</b> 1-1.5 часа онлайн\n"
        f"💰 <b>Стоимость:</b> {price_info['usd']}$ ({price_info['stars']:,}⭐)\n\n"
        "Получите экспертный взгляд на ваши инвестиции!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💳 Оплатить {price_info['usd']}$ ({price_info['stars']:,}⭐)",
                callback_data=f"pay_consultation_wallet_{price_info['stars']}"
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_consultation")]
        ])
    )
    
    await state.set_state(ConsultationState.viewing_offer)
    await state.update_data(consultation_type='wallet_review')


# === VIP-КОНСУЛЬТАЦИЯ ===

@router.message(F.text == "💎 VIP-консультация")
async def vip_consultation_offer(message: Message, state: FSMContext):
    """Предложение VIP-консультации - доступно всем"""
    user_id = message.from_user.id
    
    price_info = CONSULTATION_PRICES['vip_consultation']
    
    await message.answer(
        "💎 <b>VIP-КОНСУЛЬТАЦИЯ</b>\n\n"
        "🎯 <b>Индивидуальная работа с BLEXLER:</b>\n"
        "• Персональная стратегия торговли\n"
        "• Психология трейдинга\n"
        "• Разбор ваших ошибок\n"
        "• Построение торгового плана\n"
        "• Управление рисками\n"
        "• Доступ к приватным инсайтам\n\n"
        "👨‍🏫 <b>Формат:</b> Онлайн-встреча 1-на-1\n"
        "⏱️ <b>Продолжительность:</b> 2-3 часа\n"
        f"💰 <b>Стоимость:</b> {price_info['usd']}$ ({price_info['stars']:,}⭐)\n\n"
        "Трансформация вашего подхода к крипто!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💳 Оплатить {price_info['usd']}$ ({price_info['stars']:,}⭐)",
                callback_data=f"pay_consultation_vip_{price_info['stars']}"
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_consultation")]
        ])
    )
    
    await state.set_state(ConsultationState.viewing_offer)
    await state.update_data(consultation_type='vip_consultation')


# === PREMIUM-СИГНАЛЫ ===

@router.message(F.text == "📊 Premium-сигналы")
@router.message(F.text == "🚀 Сигналы (Futures)")  # Обратная совместимость
async def premium_signals(message: Message):
    """Доступ к Premium-сигналам"""
    user_id = message.from_user.id
    
    # Проверяем Premium статус
    user = await db.get_user(user_id)
    if not user or user.get('status') != 'premium':
        await message.answer(
            "⚠️ Доступ к Premium-сигналам только для подписчиков.\n\n"
            "Нажмите \"🌟 Получить Premium-доступ\" для подключения."
        )
        return
    
    await message.answer(
        "📊 <b>Premium-сигналы</b>\n\n"
        "Добро пожаловать в закрытый канал торговых сигналов!\n\n"
        "📈 <b>Что вы получаете:</b>\n"
        "• Futures и Spot сделки\n"
        "• Точные точки входа/выхода\n"
        "• Stop-loss и Take-profit уровни\n"
        "• Реальная статистика профита\n"
        "• Детальный анализ каждой сделки\n\n"
        "🔗 <b>Ссылка на канал:</b>\n"
        "https://t.me/blexler_premium_signals\n\n"
        "💡 Следуйте сигналам и зарабатывайте!",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# === INLINE CALLBACKS ===


@router.callback_query(F.data.startswith("pay_consultation_"))
async def process_consultation_payment(callback: CallbackQuery, state: FSMContext):
    """Обработка оплаты консультации через Telegram Stars"""
    user_id = callback.from_user.id
    
    # Получаем данные из FSM
    data = await state.get_data()
    consultation_type = data.get('consultation_type')
    
    if not consultation_type:
        await callback.answer("Ошибка: тип консультации не определён", show_alert=True)
        return
    
    price_info = CONSULTATION_PRICES.get(consultation_type)
    if not price_info:
        await callback.answer("Ошибка: цена не найдена", show_alert=True)
        return
    
    try:
        # Telegram Stars Payment API
        # Payload ДОЛЖЕН быть коротким! Максимум 128 байт
        # Формат: "wallet_300" или "vip_350" (для обратной совместимости с парсером)
        short_type = 'wallet' if consultation_type == 'wallet_review' else 'vip'
        payload = f"{short_type}_{price_info['usd']}"
        
        # Создаём invoice
        from aiogram.types import LabeledPrice
        
        await bot.send_invoice(
            chat_id=user_id,
            title=price_info['name'],
            description=f"Стоимость: {price_info['usd']}$ ({price_info['stars']:,}⭐)",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="XTR", amount=price_info['stars'])]
        )
        
        await callback.answer("💳 Счёт на оплату отправлен!")
        
        # Сохраняем в FSM для обработки после оплаты
        await state.update_data(
            pending_consultation=consultation_type,
            amount_usd=price_info['usd'],
            amount_stars=price_info['stars']
        )
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания invoice: {e}")
        await callback.answer("Ошибка создания счёта. Попробуйте позже.", show_alert=True)
    
    await callback.answer()


@router.callback_query(F.data == "cancel_consultation")
async def cancel_consultation(callback: CallbackQuery, state: FSMContext):
    """Отмена консультации"""
    await state.clear()
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


# === RELAY MODE - ПЕРЕХВАТ СООБЩЕНИЙ ===

@router.message(SupportState.active_session)
async def handle_support_message(message: Message, state: FSMContext):
    """Обработка сообщений во время активной сессии поддержки"""
    data = await state.get_data()
    session_id = data.get('session_id')
    
    if not session_id:
        await state.clear()
        return
    
    # Пересылаем сообщение админу через Relay
    await relay_manager.relay_to_admin(session_id, message)
    
    # Уведомляем пользователя
    await message.answer(
        "✅ Сообщение отправлено поддержке.\n"
        "Ожидайте ответа...",
        parse_mode="HTML"
    )


# === ADMIN CALLBACKS ===

@router.callback_query(F.data.startswith("relay_connect_"))
async def admin_connect_to_session(callback: CallbackQuery):
    """Админ подключается к сессии"""
    session_id = int(callback.data.split("_")[2])
    admin_id = callback.from_user.id
    
    session = await relay_manager.get_session(session_id)
    if not session:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    
    user_id = session['user_id']
    admin_name = ADMIN_NAMES.get(admin_id, "Поддержка")
    
    # Уведомляем пользователя
    await bot.send_message(
        user_id,
        f"✅ <b>{admin_name} подключился к диалогу!</b>\n\n"
        "Можете писать свои вопросы.",
        parse_mode="HTML"
    )
    
    # Уведомляем админа
    await callback.answer("Вы подключились к диалогу!")
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подключено", callback_data="noop")],
        [InlineKeyboardButton(text="❌ Закрыть сессию", callback_data=f"relay_close_{session_id}")]
    ]))
    
    logger.info(f"✅ Админ {admin_id} подключился к сессии {session_id}")


@router.callback_query(F.data.startswith("relay_close_"))
async def admin_close_session(callback: CallbackQuery):
    """Админ закрывает сессию"""
    session_id = int(callback.data.split("_")[2])
    
    session = await relay_manager.get_session(session_id)
    if not session:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    
    user_id = session['user_id']
    
    # Закрываем сессию
    await relay_manager.close_session(session_id, status='resolved')
    
    # Уведомляем пользователя
    await bot.send_message(
        user_id,
        "✅ <b>Вопрос решён</b>\n\n"
        "Спасибо за обращение! Если возникнут ещё вопросы - обращайтесь!",
        parse_mode="HTML"
    )
    
    # Уведомляем админа
    await callback.answer("Сессия закрыта")
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сессия закрыта", callback_data="noop")]
    ]))
    
    logger.info(f"✅ Сессия {session_id} закрыта админом {callback.from_user.id}")


@router.callback_query(F.data.startswith("relay_forward_"))
async def admin_forward_session(callback: CallbackQuery):
    """Админ переадресует сессию"""
    session_id = int(callback.data.split("_")[2])
    
    # Эскалируем сессию
    await relay_manager.escalate_session(session_id)
    
    await callback.answer("Сессия переадресована следующему админу")
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Переадресовано", callback_data="noop")]
    ]))
    
    logger.info(f"➡️ Сессия {session_id} переадресована админом {callback.from_user.id}")


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    """Пустой callback для отработанных кнопок"""
    await callback.answer()


logger.info("✅ Premium Services handlers зарегистрированы")

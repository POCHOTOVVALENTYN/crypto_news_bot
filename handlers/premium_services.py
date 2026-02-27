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
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.fsm.context import FSMContext

from database import db
from loader import bot
from config import CONSULTATION_PRICES, ADMIN_NAMES, ADMIN_IDS, config
from services.relay_manager import relay_manager
from services.payment_manager import PaymentManager
from utils.states import SupportState, ConsultationState, PriceNegotiationState
from utils.message_cleaner import track_message, delete_tracked_messages, auto_delete, safe_delete

router = Router()
logger = logging.getLogger(__name__)


# === КОНФИГУРАЦИЯ КОНСУЛЬТАЦИЙ ===

CONSULTATION_CONFIG = {
    'wallet_review': {
        'title': "💰 <b>РАЗБОР ВАШЕГО КОШЕЛЬКА</b>",
        'description': (
            "🔍 <b>Что входит:</b>\n"
            "• Детальный анализ вашего портфеля\n"
            "• Оценка рисков и потенциала каждой монеты\n"
            "• Анализ вашей торговой стратегии\n"
            "• Рекомендации по ребалансировке\n"
            "• Перспективы роста портфеля\n"
            "• Персональный план действий\n\n"
            "👨‍🏫 <b>Кто проводит:</b> BLEXLER лично\n"
            "⏱️ <b>Продолжительность:</b> 1-1.5 часа онлайн"
        ),
        'footer': "Получите экспертный взгляд на ваши инвестиции!",
        'price_key': 'wallet_review',
        'short_code': 'wallet'
    },
    'vip_consultation': {
        'title': "💎 <b>VIP-КОНСУЛЬТАЦИЯ</b>",
        'description': (
            "🎯 <b>Индивидуальная работа с BLEXLER:</b>\n"
            "• Персональная стратегия торговли\n"
            "• Психология трейдинга\n"
            "• Разбор ваших ошибок\n"
            "• Построение торгового плана\n"
            "• Управление рисками\n"
            "• Доступ к приватным инсайтам\n\n"
            "👨‍🏫 <b>Формат:</b> Онлайн-встреча 1-на-1\n"
            "⏱️ <b>Продолжительность:</b> 2-3 часа"
        ),
        'footer': "Трансформация вашего подхода к крипто!",
        'price_key': 'vip_consultation',
        'short_code': 'vip'
    }
}


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def send_consultation_offer(message: Message, consultation_type: str):
    """
    Универсальная функция отправки оффера консультации.
    Использует Stateless Callbacks (цена вшита в кнопку).
    """
    config_data = CONSULTATION_CONFIG.get(consultation_type)
    if not config_data:
        logger.error(f"Unknown consultation type: {consultation_type}")
        return

    price_info = CONSULTATION_PRICES.get(config_data['price_key'])
    if not price_info:
        logger.error(f"Price info not found for: {config_data['price_key']}")
        return

    # Формируем текст
    text = (
        f"{config_data['title']}\n\n"
        f"{config_data['description']}\n"
        f"💰 <b>Стоимость:</b> {price_info['usd']}$ ({price_info['stars']:,}⭐)\n\n"
        f"{config_data['footer']}"
    )

    # Формируем callback data с ценой и типом (Stateless)
    # pay_consult:{short_code}:{stars}
    callback_data_stars = f"pay_consult:{config_data['short_code']}:{price_info['stars']}"
    callback_data_usdt = f"pay_consult_usdt:{config_data['short_code']}:{price_info['usd']}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💵 Оплатить {price_info['usd']}$ (USDT)",
            callback_data=callback_data_usdt
        )],
        [InlineKeyboardButton(
            text=f"⭐️ Оплатить Stars ({price_info['stars']:,})",
            callback_data=callback_data_stars
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_consultation")]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


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


# === КОНСУЛЬТАЦИИ (HANDLERS) ===

@router.message(F.text == "💰 Разбор Кошелька")
async def wallet_review_offer(message: Message):
    """Предложение услуги Разбор кошелька"""
    await send_consultation_offer(message, 'wallet_review')


@router.message(F.text == "💎 VIP-консультация")
async def vip_consultation_offer(message: Message):
    """Предложение VIP-консультации"""
    await send_consultation_offer(message, 'vip_consultation')


@router.message(F.text == "💼 Консультация") # Обратная совместимость для старых кнопок меню
async def legacy_consultation_handler(message: Message):
    """Перенаправление старой кнопки на новые услуги"""
    # Предлагаем выбор или показываем VIP (как наиболее близкое)
    await message.answer(
        "💼 <b>Выберите тип консультации:</b>\n\n"
        "💰 <b>Разбор Кошелька</b> - анализ портфеля\n"
        "💎 <b>VIP-консультация</b> - персональная стратегия",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Разбор Кошелька", callback_data="show_offer_wallet")],
            [InlineKeyboardButton(text="💎 VIP-консультация", callback_data="show_offer_vip")]
        ])
    )

# Обработка кнопок выбора из legacy хендлера
@router.callback_query(F.data == "show_offer_wallet")
async def show_offer_wallet_cb(callback: CallbackQuery):
    await send_consultation_offer(callback.message, 'wallet_review')
    await callback.answer()

@router.callback_query(F.data == "show_offer_vip")
async def show_offer_vip_cb(callback: CallbackQuery):
    await send_consultation_offer(callback.message, 'vip_consultation')
    await callback.answer()


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


# === ОБРАБОТКА ОПЛАТЫ (STATELESS) ===

@router.callback_query(F.data.startswith("pay_consult_usdt:"))
async def process_consultation_usdt_payment(callback: CallbackQuery):
    """
    Обработка оплаты консультации USDT.
    Format: pay_consult_usdt:{short_code}:{usd_price}
    """
    try:
        parts = callback.data.split(":")
        short_code = parts[1]
        amount_usd = float(parts[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных кнопки", show_alert=True)
        return

    await callback.answer()
    
    # Determined service type
    service_type = 'premium'
    if short_code == 'wallet':
        service_type = 'wallet_review'
    elif short_code == 'vip':
        service_type = 'vip_consultation'
        
    await PaymentManager.send_invoice(
        callback.message.chat.id, 
        custom_price=amount_usd, 
        service_type=service_type
    )


@router.callback_query(F.data.startswith("pay_consult:"))
async def process_stateless_payment(callback: CallbackQuery):
    """
    Обработка оплаты консультации (Stateless версия).
    Format: pay_consult:{short_code}:{stars}
    """
    try:
        parts = callback.data.split(":")
        short_code = parts[1]
        amount_stars = int(parts[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных кнопки", show_alert=True)
        return

    user_id = callback.from_user.id
    
    # Определяем полные данные по short_code
    consultation_type = None
    usd_price = 0
    title = "Консультация"

    if short_code == 'wallet':
        consultation_type = 'wallet_review'
        title = "💰 Разбор Кошелька"
    elif short_code == 'vip':
        consultation_type = 'vip_consultation'
        title = "💎 VIP-консультация"
    else:
        await callback.answer("❌ Неизвестный тип услуги", show_alert=True)
        return

    # Получаем актуальную цену USD (для логов/статистики)
    # Можно взять из CONSULTATION_PRICES по ключу
    price_info = CONSULTATION_PRICES.get(consultation_type)
    if price_info:
        usd_price = price_info['usd']
        # Можно сверить stars, но доверяем кнопке, если она была сгенерирована нами

    try:
        # Payload для invoices: type_usdAmount (для совместимости)
        # Или можно использовать json.
        # Старый формат был: "wallet_300"
        payload = f"{short_code}_{usd_price}"
        
        await bot.send_invoice(
            chat_id=user_id,
            title=title,
            description=f"Стоимость: {usd_price}$ ({amount_stars:,}⭐)",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="XTR", amount=amount_stars)]
        )
        
        await callback.answer("💳 Счёт на оплату отправлен!")
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания invoice (stateless): {e}")
        await callback.answer("Ошибка создания счёта. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data == "cancel_consultation")
async def cancel_consultation(callback: CallbackQuery, state: FSMContext):
    """Отмена консультации"""
    await state.clear()
    await callback.message.edit_text("❌ Отменено")
    await callback.answer()


# === RELAY MODE - ПЕРЕХВАТ СООБЩЕНИЙ ===

@router.message(SupportState.active_session, ~F.from_user.id.in_(ADMIN_IDS), F.content_type.in_({'text', 'photo', 'voice', 'video', 'document', 'audio', 'sticker'}))
async def handle_support_message(message: Message, state: FSMContext):
    """Обработка сообщений во время активной сессии поддержки"""
    data = await state.get_data()
    session_id = data.get('session_id')
    
    if not session_id:
        await state.clear()
        return
    
    # Отслеживаем сообщение пользователя (при закрытии удалим)
    await track_message(state, message.message_id)
    
    # Пересылаем сообщение админу через Relay
    await relay_manager.relay_to_admin(session_id, message)
    
    # Уведомляем пользователя (удаляем через 10 сек — оно временное)
    sent_msg = await message.answer(
        "✅ Сообщение отправлено поддержке.\n"
        "Ожидайте ответа...",
        parse_mode="HTML"
    )
    import asyncio
    asyncio.create_task(auto_delete(bot, sent_msg.chat.id, sent_msg.message_id, delay=10))


# === PRICE NEGOTIATION RELAY ===

@router.message(F.text == "💬 Обсудить с менеджером")
async def start_price_negotiation_relay(message: Message, state: FSMContext):
    """Начать обсуждение цены с менеджером через relay"""
    pass


@router.message(PriceNegotiationState.discussing_with_admin, ~F.from_user.id.in_(ADMIN_IDS), F.content_type.in_({'text', 'photo', 'voice', 'video', 'document', 'audio', 'sticker'}))
async def handle_price_negotiation_message(message: Message, state: FSMContext):
    """Обработка сообщений клиента во время переговоров о цене"""
    data = await state.get_data()
    session_id = data.get('session_id')
    
    if not session_id:
        await state.clear()
        return
    
    # Отслеживаем сообщение пользователя (при закрытии удалим вместе с сессией)
    await track_message(state, message.message_id)
    
    # Пересылаем сообщение админу через Relay
    await relay_manager.relay_to_admin(session_id, message)
    
    # Уведомляем пользователя (временное — удалим через 10 сек)
    sent_msg = await message.answer(
        "✅ Сообщение отправлено менеджеру.\n"
        "Ожидайте ответа...",
        parse_mode="HTML"
    )
    import asyncio
    asyncio.create_task(auto_delete(bot, sent_msg.chat.id, sent_msg.message_id, delay=10))




# === ADMIN CALLBACKS ===

@router.callback_query(F.data.startswith("relay_connect_"))
async def admin_connect_to_session(callback: CallbackQuery, state: FSMContext):
    """Админ подключается к сессии"""
    session_id = int(callback.data.split("_")[2])
    admin_id = callback.from_user.id
    
    session = await relay_manager.get_session(session_id)
    if not session:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    
    user_id = session['user_id']
    admin_name = ADMIN_NAMES.get(admin_id, "Поддержка")

    # Админ забирает сессию себе
    await relay_manager.claim_session(session_id, admin_id)
    
    # Устанавливаем состояние администратора
    await state.set_state(SupportState.active_session)
    await state.update_data(session_id=session_id)
    
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



@router.callback_query(F.data.startswith("user_close_"))
async def user_close_session(callback: CallbackQuery, state: FSMContext):
    """Пользователь закрывает сессию"""
    try:
        session_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user_id = callback.from_user.id
    
    session = await relay_manager.get_session(session_id)
    if not session:
        await callback.answer("Сессия не найдена", show_alert=True)
        return

    if session.get('status') != 'active':
        await callback.answer("Диалог уже завершен", show_alert=True)
        return
    
    if session['user_id'] != user_id:
        await callback.answer("Это не ваша сессия", show_alert=True)
        return

    admin_id = session.get('current_admin_id')

    # Закрываем сессию
    await relay_manager.close_session(session_id, status='user_closed')
    
    # Очищаем состояние
    await state.clear()
    
    # Уведомляем пользователя
    await callback.answer("Диалог завершен")
    try:
        await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Диалог завершен", callback_data="noop")]
        ]))
        close_msg = await callback.message.answer("✅ Диалог завершен. Спасибо за обращение!", parse_mode="HTML")
        import asyncio
        asyncio.create_task(auto_delete(bot, close_msg.chat.id, close_msg.message_id, delay=15))
    except Exception:
        pass
    
    # Уведомляем админа
    if admin_id:
        try:
             await bot.send_message(
                admin_id,
                f"ℹ️ <b>Пользователь завершил диалог (Сессия {session_id})</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} about user close: {e}")
        
    logger.info(f"✅ Сессия {session_id} закрыта пользователем {user_id}")


@router.callback_query(F.data.startswith("relay_close_"))
async def admin_close_session(callback: CallbackQuery):
    """Админ закрывает сессию"""
    session_id = int(callback.data.split("_")[2])
    
    session = await relay_manager.get_session(session_id)
    if not session:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    
    if session.get('status') != 'active':
        await callback.answer("Сессия уже закрыта", show_alert=True)
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



# === CUSTOM PRICE NEGOTIATION ===

@router.callback_query(F.data.startswith("set_custom_price_"))
async def admin_initiate_custom_price(callback: CallbackQuery, state: FSMContext):
    """Админ нажал кнопку 'Выставить счёт' - запрашиваем сумму"""
    try:
        session_id = int(callback.data.split("_")[3])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных кнопки", show_alert=True)
        return
        
    admin_id = callback.from_user.id
    
    session = await relay_manager.get_session(session_id)
    if not session:
        await callback.answer("Сессия не найдена", show_alert=True)
        return
    
    if session['status'] != 'active':
        await callback.answer("Сессия уже закрыта", show_alert=True)
        return
    
    user_id = session['user_id']
    
    await state.set_state(PriceNegotiationState.admin_entering_price)
    await state.update_data(session_id=session_id, target_user_id=user_id)
    
    await callback.answer()
    await callback.message.answer(
        "💰 <b>Выставление счёта</b>\n\n"
        "Введите сумму в USDT (например: 650).\n"
        "Клиент получит персональное предложение с этой ценой.",
        parse_mode="HTML"
    )


@router.message(PriceNegotiationState.admin_entering_price)
async def admin_enter_custom_price(message: Message, state: FSMContext):
    """Админ ввёл сумму - отправляем оффер"""
    # Проверка на число
    if not message.text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите целое число (например 650).")
        return
        
    amount = int(message.text)
    
    MIN_PRICE = 50
    MAX_PRICE = 5000
    
    if amount < MIN_PRICE or amount > MAX_PRICE:
        await message.answer(f"⚠️ Сумма должна быть от {MIN_PRICE} до {MAX_PRICE} USDT.")
        return
    
    data = await state.get_data()
    session_id = data.get('session_id')
    user_id = data.get('target_user_id')
    
    if not session_id or not user_id:
        await message.answer("⚠️ Ошибка: данные сессии потеряны. Попробуйте снова нажать кнопку.")
        await state.clear()
        return
    
    # Сохраняем цену в сессии (опционально, сейчас просто отправляем)
    # await db.save_custom_price(session_id, user_id, amount)
    
    try:
        # Отправляем оффер пользователю
        callback_data = f"pay_custom_usdt:{amount}:{session_id}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💵 Оплатить {amount}$ (USDT)", callback_data=callback_data)]
        ])
        
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🔥 <b>Персональное предложение!</b>\n\n"
                "Мы согласовали для вас индивидуальные условия подписки.\n"
                f"💎 <b>Premium доступ</b> (1 месяц)\n"
                f"💵 Специальная цена: <b>{amount} USDT</b>\n\n"
                "Нажмите кнопку ниже для оплаты 👇"
            ),
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        # Подтверждение админу
        await message.answer(
            f"✅ <b>Предложение отправлено!</b>\n"
            f"Клиент видит оффер на {amount} USDT.",
            parse_mode="HTML"
        )
        
        # Возвращаем админа в режим переговоров (чтобы мог дальше писать)
        await state.set_state(PriceNegotiationState.discussing_with_admin)
        
    except Exception as e:
        logger.error(f"Ошибка отправки оффера: {e}", exc_info=True)
        await message.answer("⚠️ Ошибка отправки предложения клиенту.")
        # Не сбрасываем стейт полностью, даем повторить
    

@router.callback_query(F.data.startswith("pay_custom_usdt:"))
async def process_custom_offer_payment(callback: CallbackQuery):
    """
    Клиент нажал 'Оплатить Х$' в кастомном оффере.
    Запускаем PaymentManager с кастомной ценой.
    Format: pay_custom_usdt:amount:session_id
    """
    try:
        parts = callback.data.split(":")
        amount = float(parts[1])
        # session_id = parts[2] # Пока не используем, но может пригодиться для метрик
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    await callback.answer()
    
    # Запускаем флоу оплаты с кастомной ценой
    await PaymentManager.send_invoice(callback.message.chat.id, custom_price=amount)


# === CUSTOM PRICE INVOICE ===





@router.callback_query(F.data.startswith("relay_forward_"))
async def admin_forward_session(callback: CallbackQuery):
    """Админ переадресует сессию"""
    session_id = int(callback.data.split("_")[2])
    await relay_manager.escalate_session(session_id)
    await callback.answer("Сессия переадресована")
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Переадресовано", callback_data="noop")]
    ]))


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()


logger.info("✅ Premium Services handlers зарегистрированы (Refactored)")


@router.message(F.from_user.id.in_(ADMIN_IDS), lambda m: not (m.text and m.text.startswith("/")))
async def handle_admin_support_message(message: Message, state: FSMContext):
    """
    Обработка ответов админа.
    Поддерживает восстановление сессии, если бот был перезагружен.
    """
    user_id = message.from_user.id
    
    # 1. Проверяем текущее состояние FSM
    current_state = await state.get_state()
    data = await state.get_data()
    session_id = data.get('session_id')
    
    # 2. Если состояния нет, проверяем БД (восстановление после рестарта)
    if not session_id:
        active_session = await relay_manager.get_admin_active_session(user_id)
        if active_session:
            session_id = active_session['id']
            session_type = active_session['type']
            
            # Восстанавливаем состояние в зависимости от типа сессии
            if session_type == 'price_negotiation':
                await state.set_state(PriceNegotiationState.discussing_with_admin)
            else:
                await state.set_state(SupportState.active_session)
            await state.update_data(session_id=session_id)
            logger.info(f"🔄 Сессия {session_id} восстановлена для админа {user_id}")
        else:
            return
            
    # Пересылаем ответ пользователю
    await relay_manager.relay_to_user(session_id, message)
    
    # Реакция для подтверждения
    try:
        await message.react([type('ReactionTypeEmoji', (object,), {'emoji': '👌'})])
    except:
        pass


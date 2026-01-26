"""
Premium Purchase - Гибкое ценообразование
Флоу: 800$ → Дороговато? → 700$ (скидка) → Всё равно дорого? → Relay переговоры
"""
import logging
import json
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext

from database import db
from loader import bot
from config import PREMIUM_PRICES, ADMIN_NAMES
from services.relay_manager import relay_manager
from utils.states import PriceNegotiationState
from keyboards.reply import get_premium_menu, get_free_menu

router = Router()
logger = logging.getLogger(__name__)


# === ЭТАП 1: БАЗОВОЕ ПРЕДЛОЖЕНИЕ 800$ ===

@router.message(F.text == "🌟 Получить Premium-доступ")
async def premium_offer_base(message: Message, state: FSMContext):
    """Показать базовое предложение Premium за 800$"""
    user_id = message.from_user.id
    
    # Проверяем, не Premium ли уже
    user = await db.get_user(user_id)
    if user and user.get('status') == 'premium':
        await message.answer(
            "✅ У вас уже активирован Premium-доступ!\n\n"
            f"Действителен до: {user.get('premium_until', 'неизвестно')}"
        )
        return
    
    price_base = PREMIUM_PRICES['base']
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💳 Оплатить {price_base['usd']}$ ({price_base['stars']:,}⭐)",
            callback_data=f"pay_premium_base_{price_base['stars']}"
        )],
        [InlineKeyboardButton(
            text="❓ Для меня дороговато. Что делать?",
            callback_data="premium_too_expensive"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="premium_cancel")]
    ])
    
    await message.answer(
        "💎 <b>PREMIUM-ПОДПИСКА</b>\n\n"
        f"💰 <b>Стоимость:</b> {price_base['usd']}$ / месяц\n"
        f"⭐ <b>В звёздах:</b> {price_base['stars']:,}⭐\n\n"
        "🎯 <b>Что входит:</b>\n"
        "• 📊 Premium-сигналы\n"
        "• 🤖 AI-клон Аналитик 24/7\n"
        "• 🆘 Premium-поддержка (до 30 мин)\n"
        "• 📈 Полная статистика\n"
        "• 💎 Доступ к VIP-услугам\n\n"
        "✨ Трансформируйте свой трейдинг!",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await state.set_state(PriceNegotiationState.viewing_base_offer)


# === ЭТАП 2: СКИДКА 700$ ===

@router.callback_query(F.data == "premium_too_expensive")
async def premium_check_discount(callback: CallbackQuery, state: FSMContext):
    """Проверить подписки и предложить скидку"""
    user_id = callback.from_user.id
    
    await callback.answer()
    
    # Проверяем подписки на канал и чат
    is_subscribed_channel = await check_subscription(user_id, "@blexler_invest")
    is_subscribed_chat = await check_subscription(user_id, "-1001234567890")  # ID чата
    
    if is_subscribed_channel and is_subscribed_chat:
        # Предложить скидку
        await show_discount_offer(callback.message, state)
    else:
        # Предложить подписаться
        await show_subscribe_for_discount(callback.message, state)


async def check_subscription(user_id: int, channel_id: str) -> bool:
    """Проверить подписку пользователя на канал"""
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.warning(f"Ошибка проверки подписки {channel_id}: {e}")
        return False


async def show_subscribe_for_discount(message: Message, state: FSMContext):
    """Предложить подписаться для получения скидки"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📰 Подписаться на канал",
            url="https://t.me/blexler_invest"
        )],
        [InlineKeyboardButton(
            text="💬 Вступить в чат",
            url="https://t.me/+514GO2tFjAtkMWRi"
        )],
        [InlineKeyboardButton(
            text="✅ Я подписался!",
            callback_data="premium_recheck_subscription"
        )],
        [InlineKeyboardButton(
            text="❌ Всё равно дорого",
            callback_data="premium_still_expensive"
        )]
    ])
    
    await message.edit_text(
        "🎁 <b>ПОЛУЧИТЕ СКИДКУ 100$!</b>\n\n"
        "Подпишитесь на наши ресурсы и получите Premium всего за 700$/месяц!\n\n"
        "📝 <b>Условия:</b>\n"
        "✅ Подписка на канал @blexler_invest\n"
        "✅ Участие в чате сообщества\n\n"
        "💰 <b>Цена со скидкой:</b> 700$ вместо 800$\n"
        "🎉 <b>Экономия:</b> 100$!",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await state.set_state(PriceNegotiationState.checking_subscriptions)


@router.callback_query(F.data == "premium_recheck_subscription")
async def recheck_subscription(callback: CallbackQuery, state: FSMContext):
    """Повторная проверка подписок"""
    user_id = callback.from_user.id
    
    await callback.answer("Проверяем подписки...")
    
    is_subscribed_channel = await check_subscription(user_id, "@blexler_invest")
    is_subscribed_chat = await check_subscription(user_id, "-1001234567890")
    
    if is_subscribed_channel and is_subscribed_chat:
        await show_discount_offer(callback.message, state)
    else:
        missing = []
        if not is_subscribed_channel:
            missing.append("канал")
        if not is_subscribed_chat:
            missing.append("чат")
        
        await callback.answer(
            f"❌ Вы ещё не подписаны на: {', '.join(missing)}",
            show_alert=True
        )


async def show_discount_offer(message: Message, state: FSMContext):
    """Показать предложение со скидкой 700$"""
    
    price_discount = PREMIUM_PRICES['with_discount']
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💳 Оплатить {price_discount['usd']}$ ({price_discount['stars']:,}⭐)",
            callback_data=f"pay_premium_discount_{price_discount['stars']}"
        )],
        [InlineKeyboardButton(
            text="❌ Всё равно дорого",
            callback_data="premium_still_expensive"
        )]
    ])
    
    await message.edit_text(
        "🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
        "Вы получили скидку 100$!\n\n"
        f"💰 <b>Цена со скидкой:</b> {price_discount['usd']}$ / месяц\n"
        f"⭐ <b>В звёздах:</b> {price_discount['stars']:,}⭐\n"
        f"🎁 <b>Экономия:</b> {price_discount['discount_amount']}$!\n\n"
        "✨ Получите Premium по специальной цене!",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    await state.set_state(PriceNegotiationState.viewing_discount_offer)


# === ЭТАП 3: RELAY ПЕРЕГОВОРЫ ===

@router.callback_query(F.data == "premium_still_expensive")
async def premium_negotiate_price(callback: CallbackQuery, state: FSMContext):
    """Начать переговоры о цене через Relay Mode"""
    user_id = callback.from_user.id
    
    await callback.answer()
    
    # Создать Relay сессию для переговоров о цене
    session_id = await relay_manager.create_session(
        user_id=user_id,
        session_type='price_negotiation',
        initial_admin_id=304050247  # Основатель
    )
    
    await callback.message.edit_text(
        "💬 <b>ИНДИВИДУАЛЬНЫЕ УСЛОВИЯ</b>\n\n"
        "Мы понимаем, что у каждого своя ситуация.\n\n"
        "Сейчас мы подключим вас к основателю BLEXLER для обсуждения индивидуальных условий.\n\n"
        "✍️ Опишите вашу ситуацию, и мы найдём подходящее решение!",
        parse_mode="HTML"
    )
    
    # Установить FSM
    await state.set_state(PriceNegotiationState.discussing_with_admin)
    await state.update_data(session_id=session_id)
    
    logger.info(f"💬 Переговоры о цене Premium начаты для user {user_id}, session {session_id}")


# === TELEGRAM STARS PAYMENT ===

@router.callback_query(F.data.startswith("pay_premium_"))
async def create_premium_invoice(callback: CallbackQuery, state: FSMContext):
    """Создать invoice для оплаты Premium"""
    user_id = callback.from_user.id
    
    # Парсим данные
    parts = callback.data.split("_")
    tier = parts[2]  # 'base' или 'discount'
    amount_stars = int(parts[3])
    
    # Определяем параметры
    if tier == 'base':
        amount_usd = PREMIUM_PRICES['base']['usd']
        title = "💎 Premium-подписка"
        description = f"Premium доступ на 30 дней ({amount_usd}$)"
    else:  # discount
        amount_usd = PREMIUM_PRICES['with_discount']['usd']
        title = "💎 Premium-подписка (скидка)"
        description = f"Premium доступ на 30 дней ({amount_usd}$, скидка 100$)"
    
    # Payload для идентификации платежа
    payload = json.dumps({
        'type': 'premium_subscription',
        'tier': tier,
        'amount_usd': amount_usd,
        'amount_stars': amount_stars,
        'period_days': 30,
        'user_id': user_id,
        'timestamp': datetime.now().isoformat()
    })
    
    # Создаём invoice
    prices = [LabeledPrice(label="XTR", amount=amount_stars)]
    
    try:
        await bot.send_invoice(
            chat_id=user_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Пусто для Telegram Stars
            currency="XTR",
            prices=prices
        )
        
        await callback.answer("💳 Счёт на оплату отправлен!")
        await state.set_state(PriceNegotiationState.awaiting_custom_payment)
        
        logger.info(f"💳 Invoice создан для user {user_id}: {amount_usd}$ ({amount_stars}⭐)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания invoice: {e}")
        await callback.answer("❌ Ошибка создания счёта. Попробуйте позже.", show_alert=True)


# === ADMIN: УСТАНОВКА КАСТОМНОЙ ЦЕНЫ ===

@router.callback_query(F.data == "admin_set_custom_price")
async def admin_request_custom_price(callback: CallbackQuery, state: FSMContext):
    """Админ хочет установить кастомную цену"""
    
    await callback.message.answer(
        "💰 Введите кастомную цену в долларах (например: 500):"
    )
    
    await state.set_state(PriceNegotiationState.admin_setting_price)
    await callback.answer()


@router.message(PriceNegotiationState.admin_setting_price)
async def admin_process_custom_price(message: Message, state: FSMContext):
    """Обработка кастомной цены от админа"""
    
    try:
        amount_usd = int(message.text.strip().replace("$", ""))
        
        if amount_usd < 50 or amount_usd > 2000:
            await message.answer("❌ Цена должна быть от 50$ до 2000$")
            return
        
        # Конвертируем в Stars (примерно 1$ = 68.5⭐)
        amount_stars = int(amount_usd * 68.5)
        
        data = await state.get_data()
        session_id = data.get('session_id')
        
        if not session_id:
            await message.answer("❌ Сессия не найдена")
            return
        
        session = await relay_manager.get_session(session_id)
        user_id = session['user_id']
        
        # Отправляем invoice пользователю
        payload = json.dumps({
            'type': 'premium_subscription',
            'tier': 'custom',
            'amount_usd': amount_usd,
            'amount_stars': amount_stars,
            'period_days': 30,
            'user_id': user_id,
            'negotiated_by': message.from_user.id,
            'timestamp': datetime.now().isoformat()
        })
        
        prices = [LabeledPrice(label="XTR", amount=amount_stars)]
        
        await bot.send_invoice(
            chat_id=user_id,
            title="💎 Premium-подписка (индивидуальные условия)",
            description=f"Premium доступ на 30 дней ({amount_usd}$)",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=prices
        )
        
        await message.answer(
            f"✅ Счёт на {amount_usd}$ ({amount_stars:,}⭐) отправлен пользователю!"
        )
        
        # Уведомляем пользователя
        await bot.send_message(
            user_id,
            f"💰 Мы установили для вас специальную цену: {amount_usd}$/месяц!\n\n"
            f"Оплатите счёт выше для активации Premium."
        )
        
        logger.info(f"💰 Кастомная цена {amount_usd}$ установлена для user {user_id} админом {message.from_user.id}")
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введите корректную сумму (только цифры)")


# === PRE-CHECKOUT & SUCCESSFUL PAYMENT ===

@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout: PreCheckoutQuery):
    """Валидация перед оплатой"""
    
    try:
        payload = json.loads(pre_checkout.invoice_payload)
        
        # Проверяем тип платежа
        if payload['type'] not in ['premium_subscription', 'consultation']:
            await pre_checkout.answer(ok=False, error_message="Неверный тип платежа")
            return
        
        # Всё ОК
        await pre_checkout.answer(ok=True)
        logger.info(f"✅ Pre-checkout OK для user {pre_checkout.from_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка pre-checkout: {e}")
        await pre_checkout.answer(ok=False, error_message="Ошибка валидации платежа")


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    """Обработка успешной оплаты"""
    user_id = message.from_user.id
    payment = message.successful_payment
    
    try:
        # Парсим payload
        payload_str = payment.invoice_payload
        
        # Проверяем формат payload
        if payload_str.startswith('{'):
            # Старый формат JSON
            payload = json.loads(payload_str)
        else:
            # Новый короткий формат: "consultation_type_amount" или "premium_amount"
            parts = payload_str.split('_')
            if parts[0] in ['wallet', 'vip']:
                # Консультация
                consultation_type = 'wallet_review' if parts[0] == 'wallet' else 'vip_consultation'
                payload = {
                    'type': 'consultation',
                    'consultation_type': consultation_type,
                    'amount_usd': int(parts[1]) if len(parts) > 1 else CONSULTATION_PRICES[consultation_type]['usd'],
                    'amount_stars': payment.total_amount
                }
            else:
                # Premium
                payload = {
                    'type': 'premium_subscription',
                    'amount_usd': int(parts[1]) if len(parts) > 1 else PREMIUM_PRICES['base']['usd'],
                    'amount_stars': payment.total_amount
                }
        
        if payload['type'] == 'premium_subscription':
            # Активировать Premium
            amount_usd = payload['amount_usd']
            amount_stars = payload['amount_stars']
            period_days = payload.get('period_days', 30)
            
            # Сохранить платёж в БД
            payment_id = await db.save_payment(
                user_id=user_id,
                amount_stars=amount_stars,
                amount_usd=amount_usd,
                payment_type='premium_subscription',
                telegram_payment_id=payment.telegram_payment_charge_id,
                status='completed'
            )
            
            # Активировать Premium
            premium_until = (datetime.now() + timedelta(days=period_days)).isoformat()
            await db.update_user(user_id, status='premium', premium_until=premium_until)
            
            # Начислить XP за Premium
            await db.add_xp(user_id, 100, 'premium_purchase')
            
            await message.answer(
                "🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                "✅ Premium-подписка успешно активирована!\n\n"
                f"💎 Действует до: {premium_until[:10]}\n"
                f"⚡ +100 XP за покупку\n\n"
                "Добро пожаловать в Premium! 🚀",
                reply_markup=get_premium_menu(user_id),
                parse_mode="HTML"
            )
            
            logger.info(f"✅ Premium активирован для user {user_id}: {amount_usd}$ ({amount_stars}⭐)")
            
        elif payload['type'] == 'consultation':
            # Обработка оплаты консультации
            amount_usd = payload.get('amount_usd')
            amount_stars = payload.get('amount_stars', payment.total_amount)
            consultation_type = payload.get('consultation_type')
            
            # Получаем правильное название из config
            price_info = CONSULTATION_PRICES.get(consultation_type, {})
            type_name = price_info.get('name', consultation_type)
            
            # Сохранить платёж
            payment_id = await db.save_payment(
                user_id=user_id,
                amount_stars=amount_stars,
                amount_usd=amount_usd,
                payment_type='consultation',
                telegram_payment_id=payment.telegram_payment_charge_id,
                status='completed'
            )
            
            # Создать консультацию
            consultation_id = await db.create_consultation(
                user_id=user_id,
                consultation_type=consultation_type,
                amount_paid=amount_stars,
                amount_usd=amount_usd,
                payment_id=payment_id
            )
            
            # Начислить XP
            await db.add_xp(user_id, 50, 'consultation_purchase')
            
            # Отправляем с кнопкой планирования
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            from config import CONSULTATION_PRICES
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📅 Запланировать встречу",
                    callback_data="schedule_meeting"
                )]
            ])
            
            await message.answer(
                "🎉 <b>ОПЛАТА ПРОШЛА УСПЕШНО!</b>\n\n"
                f"✅ {type_name} оплачена\n"
                f"💰 Сумма: {amount_usd}$\n"
                f"⚡ +50 XP за покупку\n\n"
                "📅 Теперь выберите удобное время для встречи:",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            # Сохраняем consultation_id в FSM для планирования
            from aiogram.fsm.context import FSMContext
            from aiogram.fsm.storage.base import StorageKey
            from loader import dp
            
            storage_key = StorageKey(
                bot_id=bot.id,
                chat_id=user_id,
                user_id=user_id
            )
            
            await dp.fsm.storage.set_data(
                key=storage_key,
                data={'consultation_id': consultation_id}
            )
            
            logger.info(f"✅ Консультация оплачена: {consultation_type} для user {user_id}, ID {consultation_id}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки оплаты: {e}")
        await message.answer(
            "❌ Произошла ошибка при активации.\n"
            "Обратитесь в поддержку: @blexler"
        )


# === ОТМЕНА ===

@router.callback_query(F.data == "premium_cancel")
async def premium_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена покупки Premium"""
    await callback.message.edit_text(
        "❌ Покупка отменена.\n\n"
        "Если передумаете - просто нажмите кнопку снова!"
    )
    await state.clear()
    await callback.answer()


logger.info("✅ Premium Purchase handlers зарегистрированы")

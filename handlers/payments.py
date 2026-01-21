from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.types import SuccessfulPayment
from datetime import datetime
import logging

from database import db
from loader import bot
from config import config
from keyboards.builders import build_premium_offer_keyboard, build_discount_offer_keyboard
from keyboards.reply import get_premium_menu

router = Router()
logger = logging.getLogger(__name__)


# === ШАГ 1: ПОКАЗ ПЕРВИЧНОГО ОФФЕРА ===

@router.message(F.text == "🌟 Получить Premium-доступ")
async def show_premium_offer(message: Message):
    """Первичный оффер - полная цена"""
    user_id = message.from_user.id
    
    # Проверяем не Premium ли уже
    is_premium = await db.check_subscription(user_id)
    if is_premium:
        await message.answer(
            "✅ У вас уже активна Premium-подписка!\n"
            "Используйте меню для доступа к функциям."
        )
        return
    
    # Записываем показ оффера в воронку
    await db.track_funnel(user_id, 'offer_shown')
    await db.set_user_field(user_id, 'first_offer_shown_at', datetime.now())
    
    await message.answer(
        "💎 <b>Premium-доступ включает:</b>\n\n"
        "✅ AI-клон аналитика Blexler\n"
        "✅ Эксклюзивные сигналы по фьючерсам\n"
        "✅ Премиум-аналитика и прогнозы\n"
        "✅ Авторские рекомендации\n"
        "✅ Обучающий курс\n\n"
        f"💰 <b>Стоимость:</b> {config.premium_price_full} ⭐️ (на {config.premium_duration_days} дней)",
        parse_mode="HTML",
        reply_markup=build_premium_offer_keyboard(config.premium_price_full)
    )


# === ШАГ 2: ОБРАБОТКА ВОЗРАЖЕНИЯ ПО ЦЕНЕ ===

@router.callback_query(F.data == "price_too_high")
async def handle_price_objection(callback: CallbackQuery):
    """Пользователь говорит что дорого - показываем скидку"""
    user_id = callback.from_user.id
    
    # Записываем возражение в воронку
    await db.track_funnel(user_id, 'price_objection')
    await db.set_user_field(user_id, 'discount_offer_shown_at', datetime.now())
    
    # Показываем скидочный оффер
    discount_percent = round(
        ((config.premium_price_full - config.premium_price_discount) / config.premium_price_full) * 100
    )
    
    await callback.message.edit_text(
        f"💡 <b>Понимаю! У меня есть специальное предложение.</b>\n\n"
        f"Я могу предоставить Premium-доступ за <b>{config.premium_price_discount} ⭐️</b>\n"
        f"(скидка {discount_percent}% только сейчас!)\n\n"
        f"Это разовое предложение — воспользуйтесь им прямо сейчас! 🎁",
        parse_mode="HTML",
        reply_markup=build_discount_offer_keyboard()
    )
    await callback.answer()


# === ШАГ 3: ПОЛНЫЙ ОТКАЗ ===

@router.callback_query(F.data == "reject_premium")
async def handle_full_rejection(callback: CallbackQuery):
    """Пользователь отказывается даже от скидки"""
    user_id = callback.from_user.id
    
    # Записываем полный отказ
    await db.track_funnel(user_id, 'full_rejection')
    
    await callback.message.edit_text(
        "Понимаю 😊\n\n"
        "Вы всегда можете вернуться к покупке Premium через меню.\n\n"
        "А пока — пользуйтесь бесплатными материалами! 🎁"
    )
    await callback.answer()


# === ШАГ 4: ИНИЦИАЦИЯ ПЛАТЕЖА ===

@router.callback_query(F.data.startswith("pay_premium:"))
async def initiate_payment(callback: CallbackQuery):
    """Создание счёта для оплаты через Telegram Stars"""
    user_id = callback.from_user.id
    price = int(callback.data.split(":")[1])  # 500 или 400
    
    discount_used = (price == config.premium_price_discount)
    
    # Создаём запись платежа в БД
    await db.create_payment_record(user_id, price, discount_used)
    await db.track_funnel(user_id, 'payment_initiated', metadata={'price': price})
    
    try:
        # Отправляем Invoice (счёт) пользователю
        await bot.send_invoice(
            chat_id=user_id,
            title="Premium подписка",
            description=f"Premium-доступ на {config.premium_duration_days} дней к эксклюзивным материалам",
            payload=f"premium_{config.premium_duration_days}d_{user_id}_{price}",
            provider_token="",  # Пустая строка для Telegram Stars
            currency="XTR",  # XTR = Telegram Stars
            prices=[LabeledPrice(
                label=f"Premium ({config.premium_duration_days} дней)",
                amount=price
            )]
        )
        
        await callback.answer("💳 Счёт отправлен!", show_alert=True)
        logger.info(f"💰 Invoice отправлен: {user_id} -> {price}⭐️")
        
    except Exception as e:
        logger.error(f"Ошибка отправки invoice: {e}", exc_info=True)
        await callback.answer(
            "⚠️ Ошибка создания счёта. Попробуйте позже или обратитесь в поддержку.",
            show_alert=True
        )


# === ШАГ 5: PRE-CHECKOUT (Валидация перед оплатой) ===

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    """
    Telegram вызывает это перед финальной оплатой.
    Здесь можно добавить дополнительные проверки.
    """
    # Парсим payload
    try:
        parts = pre_checkout.invoice_payload.split("_")
        user_id_from_payload = int(parts[2])
        
        # Проверяем что user_id совпадает
        if user_id_from_payload != pre_checkout.from_user.id:
            await pre_checkout.answer(
                ok=False,
                error_message="Ошибка идентификации пользователя"
            )
            return
        
        # Всё ОК - разрешаем оплату
        await pre_checkout.answer(ok=True)
        logger.info(f"✅ Pre-checkout OK: {user_id_from_payload}")
        
    except Exception as e:
        logger.error(f"Ошибка pre-checkout: {e}")
        await pre_checkout.answer(
            ok=False,
            error_message="Произошла ошибка. Попробуйте позже."
        )


# === ШАГ 6: УСПЕШНАЯ ОПЛАТА ===

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Обработка успешной оплаты"""
    payment_info: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id
    
    # Парсим payload
    payload = payment_info.invoice_payload
    try:
        _, duration_str, user_id_from_payload, price_str = payload.split("_")
        price = int(price_str)
        
        # Дополнительная проверка user_id
        if int(user_id_from_payload) != user_id:
            logger.error(f"⚠️ User ID mismatch: {user_id_from_payload} != {user_id}")
            await message.answer("⚠️ Ошибка обработки платежа. Обратитесь в поддержку.")
            return
        
        # Активируем Premium
        await db.set_subscription(user_id, days=config.premium_duration_days)
        
        # Обновляем запись платежа
        await db.complete_payment(
            user_id=user_id,
            charge_id=payment_info.telegram_payment_charge_id,
            amount=price
        )
        
        # Записываем успешную покупку в воронку
        discount_used = (price == config.premium_price_discount)
        await db.track_funnel(user_id, 'purchase', metadata={
            'price': price,
            'discount_used': discount_used,
            'charge_id': payment_info.telegram_payment_charge_id
        })
        
        # Отправляем поздравление и переключаем на Premium-меню
        await message.answer(
            "🎉 <b>Поздравляю! Premium активирован!</b>\n\n"
            f"Ваша подписка активна на {config.premium_duration_days} дней.\n"
            f"Теперь вам доступны все премиум-функции.\n\n"
            "Используйте меню ниже для навигации. 👇",
            parse_mode="HTML",
            reply_markup=get_premium_menu()
        )
        
        logger.info(
            f"🎉 Premium активирован: {user_id}, "
            f"price={price}⭐️, discount={discount_used}, "
            f"charge_id={payment_info.telegram_payment_charge_id}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки успешного платежа: {e}", exc_info=True)
        await message.answer(
            "⚠️ Платёж получен, но произошла ошибка активации.\n"
            "Обратитесь в поддержку с этим сообщением:\n"
            f"Charge ID: {payment_info.telegram_payment_charge_id}"
        )

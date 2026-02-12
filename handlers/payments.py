from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.types import SuccessfulPayment
from aiogram.fsm.context import FSMContext
from datetime import datetime
import logging

from database import db
from loader import bot
from config import config
from utils.states import SupportState
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
    
    # 🔒 ЗАЩИТА ОТ ДУБЛИРОВАНИЯ: Проверяем нет ли уже pending платежа
    existing_payment = await db.get_pending_payment(user_id)
    if existing_payment:
        await callback.answer(
            "⚠️ У вас уже есть неоплаченный счёт. Завершите его сначала или дождитесь истечения.",
            show_alert=True
        )
        return
    
    discount_used = (price == config.premium_price_discount)
    
    # Создаём запись платежа в БД и получаем UUID
    try:
        payment_uuid = await db.create_payment_record(user_id, price, discount_used)
    except Exception as e:
        logger.error(f"Ошибка создания платежа: {e}")
        await callback.answer(
            "⚠️ Ошибка создания счёта. Попробуйте позже.",
            show_alert=True
        )
        return
    
    await db.track_funnel(user_id, 'payment_initiated', metadata={'price': price, 'uuid': payment_uuid})
    
    try:
        # Отправляем Invoice (счёт) пользователю с UUID в payload
        await bot.send_invoice(
            chat_id=user_id,
            title="Premium подписка",
            description=f"Premium-доступ на {config.premium_duration_days} дней к эксклюзивным материалам",
            payload=f"premium_{config.premium_duration_days}d_{user_id}_{price}_{payment_uuid}",
            provider_token="",  # Пустая строка для Telegram Stars
            currency="XTR",  # XTR = Telegram Stars
            prices=[LabeledPrice(
                label=f"Premium ({config.premium_duration_days} дней)",
                amount=price
            )]
        )
        
        await callback.answer("💳 Счёт отправлен!", show_alert=True)
        logger.info(f"💰 Invoice отправлен: {user_id} -> {price}⭐️ (UUID: {payment_uuid})")
        
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
    # Парсим payload с UUID
    try:
        parts = pre_checkout.invoice_payload.split("_")
        
        # CONSULTATION PAYLOADS: wallet_300, vip_350
        if parts[0] in ['wallet', 'vip']:
            # Payload format: type_price (e.g. wallet_300) - упрощенный для консультаций
            # В данном случае мы не проверяем UUID так строго, так как это stateless
            await pre_checkout.answer(ok=True)
            logger.info(f"✅ Pre-checkout OK (Consultation): {pre_checkout.invoice_payload}")
            return

        if len(parts) < 5:  # Старый формат без UUID
            user_id_from_payload = int(parts[2])
        else:  # Новый формат с UUID
            user_id_from_payload = int(parts[2])
            payment_uuid = parts[4]
        
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
async def process_successful_payment(message: Message, state: FSMContext):
    """Обработка успешной оплаты"""
    payment_info: SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id
    
    # Парсим payload с UUID
    payload = payment_info.invoice_payload
    try:
        parts = payload.split("_")
        
        # === ОБРАБОТКА КОНСУЛЬТАЦИЙ (WALLET / VIP) ===
        if parts[0] in ['wallet', 'vip']:
            consultation_type = parts[0] # wallet or vip
            price = int(parts[1])
            
            # 1. Уведомляем пользователя
            await message.answer(
                "✅ <b>Оплата успешно получена! Спасибо за доверие.</b>\n\n"
                "Я передал информацию BLEXLER. Мы свяжемся с вами в ближайшее время для выбора времени.",
                parse_mode="HTML"
            )
            
            # 2. Отправляем Анкету
            await message.answer(
                "📝 <b>Чтобы встреча прошла максимально эффективно, пожалуйста, ответьте на пару вопросов прямо здесь:</b>\n\n"
                "1. Ваш текущий портфель (скриншот или список монет).\n"
                "2. Ваш опыт в крипте (новичок / любитель / профи).\n"
                "3. Какой у вас депозит (примерно).\n"
                "4. Удобное время для созвона (дни недели и время по МСК).\n"
                "5. Предпочтительный способ связи (Telegram звонок / Zoom / Google Meet).\n\n"
                "<i>Просто напишите ответы сообщением ниже 👇</i>",
                parse_mode="HTML"
            )
            
            # 3. Создаем Relay Session
            from services.relay_manager import relay_manager
            from utils.states import SupportState
            
            # Создаем сессию в БД
            session_id = await relay_manager.create_session(
                user_id=user_id,
                session_type='consultation_planning'
            )
            
            # Включаем для пользователя режим пересылки
            await state.set_state(SupportState.active_session)
            await state.update_data(session_id=session_id)
            
            # Логирование
            logger.info(
                f"💰 CONSULTATION PAID: {user_id} type={consultation_type} price={price} "
                f"charge_id={payment_info.telegram_payment_charge_id} session={session_id}"
            )
            
            # Геймификация
            await db.log_activity(user_id, 'purchase_consultation', metadata={'amount': price, 'type': consultation_type})
            
            return


        # Проверяем формат: premium_custom_userid_amount_uuid_sessionid
        if parts[0] == "premium" and parts[1] == "custom":
            # CUSTOM PRICE PAYMENT
            user_id_from_payload = int(parts[2])
            price = int(parts[3])
            payment_uuid = parts[4]
            session_id = int(parts[5])
            
            # Проверка user_id
            if user_id_from_payload != user_id:
                logger.error(f"⚠️ User ID mismatch: {user_id_from_payload} != {user_id}")
                await message.answer("⚠️ Ошибка обработки платежа. Обратитесь в поддержку.")
                return
            
            # Активируем Premium
            await db.set_subscription(user_id, days=config.premium_duration_days)
            
            # Обновляем запись платежа
            await db.complete_payment(
                payment_uuid=payment_uuid,
                charge_id=payment_info.telegram_payment_charge_id,
                user_id=user_id,
                amount=price
            )
            
            # Закрываем relay session
            from services.relay_manager import relay_manager
            session = await relay_manager.get_session(session_id)
            if session:
                await relay_manager.close_session(session_id, status='completed')
                
                # Уведомляем админа
                admin_id = session.get('current_admin_id')
                if admin_id:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"✅ <b>Клиент оплатил!</b>\n\n"
                            f"User ID: {user_id}\n"
                            f"Сумма: {price}⭐\n"
                            f"Premium активирован на {config.premium_duration_days} дней",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin {admin_id}: {e}")
            
            # Записываем в воронку
            await db.track_funnel(user_id, 'purchase', metadata={
                'price': price,
                'discount_used': True,  # Кастомная цена = скидка
                'charge_id': payment_info.telegram_payment_charge_id,
                'uuid': payment_uuid,
                'session_id': session_id,
                'custom_price': True
            })
            
            # Логирование платежа
            payment_logger = logging.getLogger("payments")
            payment_logger.info(
                f"PAYMENT_SUCCESS | user_id={user_id} | amount={price} | "
                f"charge_id={payment_info.telegram_payment_charge_id} | "
                f"custom_price=True | uuid={payment_uuid} | session={session_id}"
            )
            
            # Геймификация
            xp_result = await db.log_activity(user_id, 'purchase', metadata={
                'amount': price,
                'discount': True,
                'custom_price': True
            })
            
            # Поздравление
            congrats_text = (
                "🎉 <b>Поздравляю! Premium активирован!</b>\n\n"
                f"Ваша подписка активна на {config.premium_duration_days} дней.\n"
                f"Теперь вам доступны все премиум-функции.\n\n"
            )
            
            if xp_result.get('level_up'):
                congrats_text += (
                    f"🎊 <b>Level UP!</b> Вы достигли {xp_result['new_level']} уровня!\n"
                    f"✨ +{xp_result['xp_earned']} XP\n\n"
                )
            else:
                congrats_text += f"✨ +{xp_result.get('xp_earned', 100)} XP\n\n"
            
            congrats_text += "Используйте меню ниже для навигации. 👇"
            
            await message.answer(
                congrats_text,
                parse_mode="HTML",
                reply_markup=get_premium_menu()
            )
            
            logger.info(
                f"🎉 Premium активирован (custom price): {user_id}, "
                f"price={price}⭐, session={session_id}, "
                f"charge_id={payment_info.telegram_payment_charge_id}"
            )
            
            return  # Выходим, обработка завершена
        
        # СТАНДАРТНАЯ ОБРАБОТКА (старый формат)
        # Поддержка старого формата (без UUID) и нового (с UUID)
        if len(parts) < 5:
            # Старый формат: premium_30d_userid_price
            _, duration_str, user_id_from_payload, price_str = parts
            payment_uuid = None
        else:
            # Новый формат: premium_30d_userid_price_uuid
            _, duration_str, user_id_from_payload, price_str, payment_uuid = parts
        
        price = int(price_str)
        
        # Дополнительная проверка user_id
        if int(user_id_from_payload) != user_id:
            logger.error(f"⚠️ User ID mismatch: {user_id_from_payload} != {user_id}")
            await message.answer("⚠️ Ошибка обработки платежа. Обратитесь в поддержку.")
            return
        
        # Активируем Premium
        await db.set_subscription(user_id, days=config.premium_duration_days)
        
        # Обновляем запись платежа (с UUID если есть)
        if payment_uuid:
            await db.complete_payment(
                payment_uuid=payment_uuid,
                charge_id=payment_info.telegram_payment_charge_id,
                user_id=user_id,
                amount=price
            )
        else:
            # Fallback для старых платежей без UUID
            logger.warning(f"⚠️ Payment without UUID for user {user_id}")
        
        # Записываем успешную покупку в воронку
        discount_used = (price == config.premium_price_discount)
        await db.track_funnel(user_id, 'purchase', metadata={
            'price': price,
            'discount_used': discount_used,
            'charge_id': payment_info.telegram_payment_charge_id,
            'uuid': payment_uuid
        })
        
        # 📝 ОТДЕЛЬНОЕ ЛОГИРОВАНИЕ ПЛАТЕЖЕЙ для аудита
        payment_logger = logging.getLogger("payments")
        payment_logger.info(
            f"PAYMENT_SUCCESS | user_id={user_id} | amount={price} | "
            f"charge_id={payment_info.telegram_payment_charge_id} | "
            f"discount={discount_used} | uuid={payment_uuid}"
        )
        
        # 🎮 ГЕЙМИФИКАЦИЯ: начисляем XP за покупку
        xp_result = await db.log_activity(user_id, 'purchase', metadata={
            'amount': price,
            'discount': discount_used
        })
        
        # Отправляем поздравление и переключаем на Premium-меню
        congrats_text = (
            "🎉 <b>Поздравляю! Premium активирован!</b>\n\n"
            f"Ваша подписка активна на {config.premium_duration_days} дней.\n"
            f"Теперь вам доступны все премиум-функции.\n\n"
        )
        
        # Добавляем информацию о level up
        if xp_result.get('level_up'):
            congrats_text += (
                f"🎊 <b>Level UP!</b> Вы достигли {xp_result['new_level']} уровня!\n"
                f"✨ +{xp_result['xp_earned']} XP\n\n"
            )
        else:
            congrats_text += f"✨ +{xp_result.get('xp_earned', 100)} XP\n\n"
        
        congrats_text += "Используйте меню ниже для навигации. 👇"
        
        await message.answer(
            congrats_text,
            parse_mode="HTML",
            reply_markup=get_premium_menu()
        )
        
        logger.info(
            f"🎉 Premium активирован: {user_id}, "
            f"price={price}⭐️, discount={discount_used}, "
            f"charge_id={payment_info.telegram_payment_charge_id}, "
            f"uuid={payment_uuid}"
        )
        
        # 🎁 АВТО-ПРОВЕРКА РЕФЕРАЛЬНОГО БОНУСА
        # Если пользователь был приглашён - проверяем право пригласителя на Premium бонус
        try:
            referrer_info = await db.get_referrer(user_id)
            if referrer_info:
                referrer_id = referrer_info['referrer_id']
                
                # Начисляем XP рефрреру за покупку Premium его рефералом
                await db.log_activity(
                    referrer_id,
                    'referral_purchase',
                    metadata={'referred_user': user_id, 'amount': price}
                )
                
                # Проверяем право на Premium бонус
                eligibility = await db.check_premium_bonus_eligibility(referrer_id)
                
                if eligibility['eligible']:
                    # Выдаём Premium бонус
                    success = await db.grant_referral_premium_bonus(referrer_id, bonus_days=12)
                    
                    if success:
                        # Уведомляем пользователя о бонусе
                        try:
                            await message.bot.send_message(
                                referrer_id,
                                "🎊 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                                "Вы достигли 10 активных рефералов!\n\n"
                                "🎁 <b>Награда:</b> Premium на 12 дней\n"
                                "✨ +500 XP бонус\n\n"
                                "Ваша подписка автоматически активирована!",
                                parse_mode="HTML"
                            )
                            logger.info(f"🎁💎 Premium бонус автоматически выдан: {referrer_id}")
                        except:
                            pass
        except Exception as e:
            logger.error(f"Ошибка проверки реферального бонуса: {e}", exc_info=True)
        
    except Exception as e:
        logger.error(f"Ошибка обработки успешного платежа: {e}", exc_info=True)
        await message.answer(
            "⚠️ Платёж получен, но произошла ошибка активации.\n"
            "Обратитесь в поддержку с этим сообщением:\n"
            f"Charge ID: {payment_info.telegram_payment_charge_id}"
        )


# === TEST TOOLS ===

@router.message(Command("test_pay_consult"))
async def test_successful_payment(message: Message, state: FSMContext):
    """
    Тестовая команда для симуляции оплаты.
    Доступна только разработчику.
    """
    # 1. Защита по ID
    if message.from_user.id != 7453894165:
        return

    # 2. Парсинг аргументов
    args = message.text.split()
    consult_type = args[1] if len(args) > 1 else "wallet"
    
    if consult_type not in ['wallet', 'vip']:
        await message.answer("Usage: /test_pay_consult [wallet|vip]")
        return

    # 3. Подготовка данных
    price = 300 if consult_type == 'wallet' else 350
    stars = 20500 if consult_type == 'wallet' else 24000
    
    payload = f"{consult_type}_{price}"
    
    # 4. Создание Mock-объекта оплаты
    mock_payment = SuccessfulPayment(
        currency="XTR",
        total_amount=stars,
        invoice_payload=payload,
        telegram_payment_charge_id=f"TEST_CHARGE_{datetime.now().timestamp()}",
        provider_payment_charge_id="TEST_PROVIDER"
    )
    
    # 5. Клонирование сообщения с добавлением successful_payment
    # Используем model_copy для создания копии с измененным полем
    try:
        mock_message = message.model_copy(update={'successful_payment': mock_payment})
        
        await message.answer(f"🔄 <b>TEST MODE:</b> Simulating payment for {consult_type}...", parse_mode="HTML")
        
        # 6. Вызов реального обработчика
        await process_successful_payment(mock_message, state)
        
    except Exception as e:
        logger.error(f"Test command failed: {e}", exc_info=True)
        await message.answer(f"❌ Test failed: {e}")



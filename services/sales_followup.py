"""
Сервис автоматического дожима в продажах
Отправляет напоминания пользователям, застрявшим в воронке
"""
import logging
from datetime import datetime, timedelta
from loader import bot
from database import db

logger = logging.getLogger(__name__)


async def check_abandoned_purchases():
    """Проверяет застрявших в воронке пользователей и отправляет напоминания"""
    
    # Импорт клавиатуры для кнопок
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from config import PREMIUM_PRICES
    
    try:
        # Получаем пользователей, застрявших в воронке
        # SQL запрос теперь умный: он возвращает только тех, кому МОЖНО отправить (прошло > 2h или > 24h для повтора)
        abandoned_users = await db.get_abandoned_funnel_users(hours=2)
        
        if not abandoned_users:
            logger.debug("📊 Авто-дожим: нет застрявших пользователей")
            return
        
        logger.info(f"📨 Авто-дожим: найдено {len(abandoned_users)} кандидатов")
        
        for user_data in abandoned_users:
            user_id = user_data['user_id']
            last_step = user_data['last_step']
            
            # Проверка лимита надоедания (не спамить вечно)
            # Считаем сколько раз уже отправляли followup
            followup_count = await db.count_user_activity(user_id, 'followup_sent')
            if followup_count >= 3:
                logger.debug(f"🛑 Дожим пропущен для {user_id}: лимит ({followup_count}/3) исчерпан")
                continue
            
            try:
                # Цена со скидкой для кнопок
                price_discount = PREMIUM_PRICES['with_discount']
                
                # КЛАВИАТУРА С КНОПКАМИ
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=f"💳 Купить Premium ({price_discount['usd']}$)",
                        callback_data=f"pay_premium_discount_{price_discount['stars']}"
                    )],
                    [InlineKeyboardButton(
                        text="🙏 Спасибо, не нужно",
                        callback_data="premium_delete_message"
                    )]
                ])

                message_text = ""
                
                if last_step == 'offer_shown':
                    # Пользователь увидел оффер, но ничего не сделал
                    message_text = (
                        "🤔 <b>Есть вопросы по Premium?</b>\n\n"
                        "Вы смотрели наше Premium-предложение.\n"
                        "Если что-то непонятно - просто напишите!\n\n"
                        "👇 <b>Или оформите со скидкой прямо сейчас:</b>"
                    )
                    
                elif last_step == 'price_objection':
                    # Пользователь возразил о цене
                    message_text = (
                        "💎 <b>Специальное предложение активно!</b>\n\n"
                        "Ваша персональная скидка 100$ всё ещё действует.\n\n"
                        f"<b>{price_discount['usd']}$</b> вместо {PREMIUM_PRICES['base']['usd']}$ - только сегодня!\n\n"
                        "Не упустите возможность 🚀"
                    )
                    
                elif last_step == 'followup_sent':
                    # Повторное напоминание (прошло 24ч)
                    message_text = (
                        "⏰ <b>Последний шанс!</b>\n\n"
                        "Срок действия вашего спецпредложения истекает.\n"
                        "Получите доступ к лучшей аналитике прямо сейчас!\n\n"
                        "👇 <b>Нажмите кнопку ниже:</b>"
                    )

                if message_text:
                    await bot.send_message(
                        user_id,
                        message_text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    
                    # Логируем отправку
                    # Важно: это создаст новую запись в funnel_stats со step='followup_sent'
                    # и временем now(). Следующая выборка увидит это время и отсчитает 24ч.
                    await db.track_funnel_step(user_id, 'followup_sent')
                    logger.info(f"📨 Дожим отправлен: {user_id} (был step: {last_step}, popitka: {followup_count+1})")
                
            except Exception as e:
                logger.error(f"Ошибка отправки дожима {user_id}: {e}")
        
    except Exception as e:
        logger.error(f"Критическая ошибка авто-дожима: {e}", exc_info=True)

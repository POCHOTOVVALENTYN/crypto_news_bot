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
    
    try:
        # Получаем пользователей, застрявших в воронке >2 часов
        abandoned_users = await db.get_abandoned_funnel_users(hours=2)
        
        if not abandoned_users:
            logger.debug("📊 Авто-дожим: нет застрявших пользователей")
            return
        
        logger.info(f"📨 Авто-дожим: найдено {len(abandoned_users)} застрявших")
        
        for user_data in abandoned_users:
            user_id = user_data['user_id']
            last_step = user_data['last_step']
            
            try:
                if last_step == 'offer_shown':
                    # Пользователь увидел оффер, но ничего не сделал
                    await bot.send_message(
                        user_id,
                        "🤔 <b>Есть вопросы по Premium?</b>\n\n"
                        "Вы смотрели наше Premium-предложение.\n"
                        "Если что-то непонятно - просто напишите!\n\n"
                        "Я помогу разобраться с функциями и преимуществами. 💬",
                        parse_mode="HTML"
                    )
                    
                elif last_step == 'price_objection':
                    # Пользователь возразил о цене, но не купил со скидкой
                    await bot.send_message(
                        user_id,
                        "💎 <b>Специальное предложение активно!</b>\n\n"
                        "Ваша персональная скидка 100⭐️ всё ещё действует.\n\n"
                        "400⭐️ вместо 500⭐️ - только сегодня!\n\n"
                        "Не упустите возможность 🚀",
                        parse_mode="HTML"
                    )
                
                # Логируем отправку
                await db.track_funnel_step(user_id, 'followup_sent')
                logger.info(f"📨 Дожим отправлен: {user_id} (step: {last_step})")
                
            except Exception as e:
                logger.error(f"Ошибка отправки дожима {user_id}: {e}")
        
        logger.info(f"✅ Авто-дожим завершён: {len(abandoned_users)} пользователей")
        
    except Exception as e:
        logger.error(f"Критическая ошибка авто-дожима: {e}", exc_info=True)

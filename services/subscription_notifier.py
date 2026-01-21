"""
Сервис уведомлений об истечении подписок
"""
import logging
from datetime import datetime, timedelta
import aiosqlite

from database import db
from loader import bot

logger = logging.getLogger(__name__)


async def check_expiring_subscriptions():
    """
    Проверяет подписки близкие к истечению и отправляет уведомления.
    Запускается по расписанию (1 раз в день).
    """
    now = datetime.now()
    
    # Пороги для уведомлений
    threshold_3d = (now + timedelta(days=3)).isoformat()
    threshold_1d = (now + timedelta(days=1)).isoformat()
    
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            
            # За 3 дня до истечения
            async with conn.execute(
                """SELECT user_id, subscription_end, full_name
                   FROM users 
                   WHERE status='premium' 
                   AND subscription_end <= ?
                   AND subscription_end > ?
                   AND subscription_end > datetime('now')""",
                (threshold_3d, threshold_1d)
            ) as cursor:
                async for row in cursor:
                    user_id = row[0]
                    end_date_str = row[1]
                    full_name = row[2] or "Пользователь"
                    
                    end_date = datetime.fromisoformat(end_date_str)
                    days_left = (end_date - now).days
                    
                    try:
                        await bot.send_message(
                            user_id,
                            f"⚠️ <b>Уважаемый {full_name}!</b>\n\n"
                            f"Ваша Premium-подписка истекает через <b>{days_left} дня</b>!\n\n"
                            f"📅 Дата окончания: {end_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                            f"Продлите сейчас, чтобы не потерять доступ к:\n"
                            f"• 🤖 AI-клону аналитика\n"
                            f"• 🚀 Эксклюзивным сигналам\n"
                            f"• 📊 Премиум-аналитике\n\n"
                            f"Нажмите /start для продления",
                            parse_mode="HTML"
                        )
                        logger.info(f"📧 Уведомление за 3 дня отправлено: {user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления {user_id}: {e}")
            
            # За 1 день до истечения (более срочное)
            async with conn.execute(
                """SELECT user_id, subscription_end, full_name
                   FROM users 
                   WHERE status='premium' 
                   AND subscription_end <= ?
                   AND subscription_end > datetime('now')""",
                (threshold_1d,)
            ) as cursor:
                async for row in cursor:
                    user_id = row[0]
                    end_date_str = row[1]
                    full_name = row[2] or "Пользователь"
                    
                    end_date = datetime.fromisoformat(end_date_str)
                    hours_left = int((end_date - now).total_seconds() / 3600)
                    
                    try:
                        await bot.send_message(
                            user_id,
                            f"🔴 <b>СРОЧНО! {full_name}</b>\n\n"
                            f"Ваша Premium-подписка истекает через <b>{hours_left} часов</b>!\n\n"
                            f"⏰ Продлите СЕЙЧАС, чтобы не потерять доступ:\n"
                            f"/start",
                            parse_mode="HTML"
                        )
                        logger.info(f"📧 Срочное уведомление за 1 день отправлено: {user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка отправки срочного уведомления {user_id}: {e}")
        
        logger.info("✅ Проверка истекающих подписок завершена")
        
    except Exception as e:
        logger.error(f"Ошибка проверки истекающих подписок: {e}", exc_info=True)

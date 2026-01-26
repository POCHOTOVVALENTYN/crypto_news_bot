"""
Дополнительные задачи для Scheduler:
- Эскалация сессий поддержки
- Отправка напоминаний о встречах
"""
import logging
from datetime import datetime, timedelta
from database import db
from services.relay_manager import relay_manager
from loader import bot
from config import CONSULTATION_PRICES
from utils.error_handling import safe_task

logger = logging.getLogger(__name__)


@safe_task("Support Escalation")
async def check_support_escalation():
    """Проверка таймаутов сессий поддержки и эскалация каждые 5 минут"""
    
    try:
        # Получаем все активные сессии старше 15 минут без активности
        timeout_threshold = (datetime.now() - timedelta(minutes=15)).isoformat()
        
        cursor = await db.conn.execute("""
            SELECT id, user_id, current_admin_id, admin_cascade_level, last_activity, type
            FROM support_sessions
            WHERE status = 'active'
            AND datetime(last_activity) < datetime(?)
        """, (timeout_threshold,))
        
        sessions = await cursor.fetchall()
        
        if not sessions:
            return
        
        logger.info(f"⏱️ Найдено {len(sessions)} сессий для эскалации")
        
        for session in sessions:
            session_id, user_id, admin_id, level, last_activity, session_type = session
            
            # Эскалируем сессию
            await relay_manager.escalate_session(session_id)
            
            logger.info(f"⬆️ Эскалирована сессия #{session_id} (user {user_id}, level {level}→{level+1})")
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки эскалации: {e}", exc_info=True)


@safe_task("Meeting Reminders")
async def send_meeting_reminders():
    """Отправка напоминаний о встречах каждые 5 минут"""
    
    try:
        # Получаем все неотправленные напоминания, время которых наступило
        cursor = await db.conn.execute("""
            SELECT r.id, r.consultation_id, r.reminder_type, 
                   c.user_id, c.type, c.scheduled_datetime
            FROM consultation_reminders r
            JOIN consultations c ON r.consultation_id = c.id
            WHERE r.sent = 0
            AND datetime(r.scheduled_time) <= datetime('now')
        """)
        
        reminders = await cursor.fetchall()
        
        if not reminders:
            return
        
        logger.info(f"📨 Найдено {len(reminders)} напоминаний для отправки")
        
        for reminder in reminders:
            reminder_id, consultation_id, reminder_type, user_id, cons_type, meeting_time = reminder
            
            try:
                # Получаем название консультации
                type_name = CONSULTATION_PRICES.get(cons_type, {}).get('name', cons_type)
                
                # Формируем текст в зависимости от типа напоминания
                if reminder_type == '24h_before':
                    user_text = (
                        "⏰ <b>Напоминание о встрече</b>\n\n"
                        f"Через 24 часа у вас встреча:\n"
                        f"📋 {type_name}\n"
                        f"📅 {meeting_time}\n\n"
                        "Не забудьте подготовиться!"
                    )
                    admin_text = (
                        f"⏰ Напоминание: завтра встреча\n\n"
                        f"👤 User ID: {user_id}\n"
                        f"📋 {type_name}\n"
                        f"📅 {meeting_time}"
                    )
                else:  # 1h_before
                    user_text = (
                        "⏰ <b>Встреча через 1 час!</b>\n\n"
                        f"📋 {type_name}\n"
                        f"📅 {meeting_time}\n\n"
                        "Скоро начнём!"
                    )
                    admin_text = (
                        f"⏰ Встреча через 1 час!\n\n"
                        f"👤 User ID: {user_id}\n"
                        f"📋 {type_name}\n"
                        f"📅 {meeting_time}"
                    )
                
                # Отправляем пользователю
                await bot.send_message(user_id, user_text, parse_mode="HTML")
                
                # Уведомляем основателя (он проводит все консультации)
                await bot.send_message(304050247, admin_text)
                
                # Отмечаем как отправленное
                await db.mark_reminder_sent(reminder_id)
                
                logger.info(f"✅ Напоминание отправлено: {reminder_type} для консультации {consultation_id}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка отправки напоминания {reminder_id}: {e}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки напоминаний: {e}", exc_info=True)


def register_additional_jobs(scheduler):
    """
    Регистрация дополнительных задач в scheduler
    
    Args:
        scheduler: APScheduler instance
    """
    # Задача эскалации сессий
    scheduler.add_job(
        check_support_escalation,
        'interval',
        minutes=5,
        id='support_escalation',
        name='Support Escalation Checker'
    )
    logger.info("✅ Scheduler: Support Escalation зарегистрирован (каждые 5 мин)")
    
    # Задача напоминаний о встречах
    scheduler.add_job(
        send_meeting_reminders,
        'interval',
        minutes=5,
        id='meeting_reminders',
        name='Meeting Reminders Sender'
    )
    logger.info("✅ Scheduler: Meeting Reminders зарегистрирован (каждые 5 мин)")

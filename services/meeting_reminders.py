"""
Meeting Reminders - Создание напоминаний о консультациях
"""
import logging
from datetime import datetime, timedelta
from database import db

logger = logging.getLogger(__name__)


async def create_meeting_reminders(consultation_id: int, scheduled_datetime: str):
    """
    Создать напоминания за 24ч и 1ч до встречи
    
    Args:
        consultation_id: ID консультации
        scheduled_datetime: Дата/время встречи в ISO формате
    """
    try:
        meeting_time = datetime.fromisoformat(scheduled_datetime)
        
        # Напоминание за 24 часа
        reminder_24h = meeting_time - timedelta(hours=24)
        
        # Только если встреча >24ч в будущем
        if reminder_24h > datetime.now():
            await db.create_reminder(
                consultation_id=consultation_id,
                reminder_type='24h_before',
                scheduled_time=reminder_24h.isoformat()
            )
            logger.info(f"⏰ Создано напоминание 24ч для консультации {consultation_id}")
        
        # Напоминание за 1 час
        reminder_1h = meeting_time - timedelta(hours=1)
        
        # Только если встреча >1ч в будущем  
        if reminder_1h > datetime.now():
            await db.create_reminder(
                consultation_id=consultation_id,
                reminder_type='1h_before',
                scheduled_time=reminder_1h.isoformat()
            )
            logger.info(f"⏰ Создано напоминание 1ч для консультации {consultation_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка создания напоминаний: {e}", exc_info=True)
        return False

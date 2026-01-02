# utils/error_handling.py
import logging
import traceback
import asyncio
import functools
from aiogram import Bot
from config import TELEGRAM_CHANNEL_ID

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self):
        self.bot = None
        self.admin_id = None

    def init(self, bot: Bot):
        self.bot = bot

    async def notify_admin(self, text: str):
        """Отправляет уведомление об ошибке в лог и (опционально) в Telegram"""
        logger.error(f"ALERT: {text}")
        # Если хотите получать ошибки в личку/канал, раскомментируйте:
        # if self.bot and TELEGRAM_CHANNEL_ID:
        #     try:
        #         await self.bot.send_message(TELEGRAM_CHANNEL_ID, f"🚨 {text}")
        #     except Exception as e:
        #         logger.error(f"Не удалось отправить алерт: {e}")
    
    async def send_alert(self, text: str, level: str = "ERROR"):
        """
        Отправляет алерт админу в Telegram.
        
        Args:
            text: Текст сообщения
            level: Уровень важности (ERROR, CRITICAL, WARNING, INFO)
        """
        # Эмодзи для уровней
        emoji_map = {
            "ERROR": "❌",
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "INFO": "ℹ️"
        }
        emoji = emoji_map.get(level, "📢")
        
        message = f"{emoji} <b>{level}</b>\n\n{text}"
        
        logger.error(f"ALERT [{level}]: {text}")
        
        # Отправляем админу если настроено
        if self.bot and self.admin_id:
            try:
                await self.bot.send_message(
                    self.admin_id,
                    message,
                    parse_mode="HTML"
                )
                logger.info(f"✅ Алерт отправлен админу (ID: {self.admin_id})")
            except Exception as e:
                logger.error(f"❌ Не удалось отправить алерт админу: {e}")

# Глобальный экземпляр
alert_manager = AlertManager()

def critical_error_handler(func):
    """Декоратор для защиты критических функций"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            error_msg = f"CRITICAL ERROR in {func.__name__}: {e}"
            logger.critical(error_msg, exc_info=True)
            await alert_manager.notify_admin(error_msg)
            # Тут можно добавить логику перезапуска или остановки
    return wrapper

def safe_task(task_name=None):
    """
    Декоратор для защиты фоновых задач.
    Ловит исключения, чтобы они не ломали Event Loop.
    
    Использование:
        @safe_task("Task Name")
        async def my_task():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                pass  # Обычная остановка задачи
            except Exception as e:
                task_display = task_name or func.__name__
                logger.error(f"❌ Ошибка в задаче '{task_display}': {e}", exc_info=True)
                if hasattr(alert_manager, 'send_alert'):
                    try:
                        await alert_manager.send_alert(
                            f"Ошибка в задаче '{task_display}': {str(e)[:200]}",
                            level="ERROR"
                        )
                    except Exception as alert_error:
                        logger.error(f"❌ Не удалось отправить алерт: {alert_error}")
                else:
                    await alert_manager.notify_admin(f"Background task '{task_display}' failed: {e}")
        return wrapper
    
    # Если декоратор вызван без скобок (@safe_task), task_name будет функцией
    if callable(task_name):
        # Декоратор использован без аргументов: @safe_task
        func = task_name
        task_name = None
        return decorator(func)
    
    # Декоратор использован с аргументом: @safe_task("Name")
    return decorator
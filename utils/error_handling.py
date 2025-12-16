# utils/error_handling.py
import logging
import traceback
import functools
from typing import Callable, Optional
from aiogram import Bot

logger = logging.getLogger(__name__)


class AlertManager:
    """Менеджер алертов для критических ошибок"""

    def __init__(self, bot: Optional[Bot] = None, admin_id: Optional[int] = None):
        self.bot = bot
        self.admin_id = admin_id
        self.error_count = 0
        self.max_errors_before_alert = 5

    async def send_alert(self, text: str, level: str = "ERROR"):
        """
        Отправляет алерт админу в Telegram

        Args:
            text: Текст сообщения
            level: Уровень важности (ERROR, CRITICAL, WARNING)
        """
        emoji_map = {
            "CRITICAL": "🚨",
            "ERROR": "❌",
            "WARNING": "⚠️",
            "INFO": "ℹ️"
        }

        emoji = emoji_map.get(level, "⚠️")
        message = f"{emoji} <b>{level}</b>\n\n{text}"

        # Логируем всегда
        logger.error(f"ALERT [{level}]: {text}")

        # Отправляем в Telegram если настроено
        if self.bot and self.admin_id:
            try:
                await self.bot.send_message(
                    chat_id=self.admin_id,
                    text=message[:4096],  # Telegram limit
                    parse_mode="HTML"
                )
                logger.info(f"✅ Алерт отправлен админу (ID: {self.admin_id})")
            except Exception as e:
                logger.error(f"❌ Не удалось отправить алерт: {e}")
        else:
            logger.warning("⚠️ AlertManager не настроен (нет ADMIN_ID или Bot)")

    def increment_error_count(self):
        """Увеличивает счетчик ошибок"""
        self.error_count += 1
        if self.error_count >= self.max_errors_before_alert:
            return True
        return False


# Глобальный экземпляр (будет настроен в main.py)
alert_manager = AlertManager()


def safe_task(task_name: str = "Unknown Task"):
    """
    Декоратор для защиты задач планировщика от падения.

    Перехватывает все исключения, логирует с traceback,
    отправляет алерт админу при критических ошибках.

    Usage:
        @safe_task("RSS Parsing")
        async def scheduled_parsing():
            ...
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                logger.debug(f"🔄 Запуск задачи: {task_name}")
                result = await func(*args, **kwargs)
                logger.debug(f"✅ Задача завершена: {task_name}")
                return result

            except Exception as e:
                # Получаем полный traceback
                tb = traceback.format_exc()

                # Логируем с traceback
                logger.error(
                    f"❌ ОШИБКА В ЗАДАЧЕ '{task_name}':\n"
                    f"Исключение: {type(e).__name__}: {e}\n"
                    f"Traceback:\n{tb}"
                )

                # Увеличиваем счетчик ошибок
                if alert_manager.increment_error_count():
                    await alert_manager.send_alert(
                        f"Задача: {task_name}\n"
                        f"Ошибка: {type(e).__name__}: {str(e)[:200]}\n"
                        f"Счетчик ошибок: {alert_manager.error_count}",
                        level="CRITICAL"
                    )
                    # Сбрасываем счетчик после отправки алерта
                    alert_manager.error_count = 0

                # НЕ пробрасываем исключение - задача продолжит работать
                return None

        return wrapper

    return decorator


async def critical_error_handler(error_text: str, exception: Optional[Exception] = None):
    """
    Обработчик критических ошибок (падение БД, сети и т.д.)

    Args:
        error_text: Описание ошибки
        exception: Исключение (если есть)
    """
    full_text = error_text

    if exception:
        tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
        full_text += f"\n\nТип: {type(exception).__name__}\n"
        full_text += f"Сообщение: {exception}\n"
        full_text += f"Traceback:\n{''.join(tb[-5:])}"  # Последние 5 строк

    logger.critical(full_text)
    await alert_manager.send_alert(full_text[:1000], level="CRITICAL")
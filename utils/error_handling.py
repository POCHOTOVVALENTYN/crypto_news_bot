# utils/error_handling.py
import logging
import traceback
from aiogram import Bot
from config import TELEGRAM_CHANNEL_ID

logger = logging.getLogger(__name__)


class ErrorHandler:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def handle_error(self, error: Exception, context: str = "General"):
        """Логирует ошибку и отправляет (если может) алерт админу"""
        error_msg = f"❌ Ошибка в {context}: {type(error).__name__} - {error}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())

        # Пытаемся отправить в админку, но не крашимся, если не вышло
        try:
            # Важно: Не отправляем при сетевых ошибках, чтобы не спамить
            if "ClientConnectorError" in str(error) or "NetworkError" in str(error):
                logger.warning("🔕 Сетевая ошибка - алерт в Telegram пропущен.")
                return

            # Тут лучше слать в ЛС админу, но пока шлем в канал или лог
            # await self.bot.send_message(...)
            pass

        except Exception as send_error:
            logger.error(f"⚠️ Не удалось отправить алерт об ошибке: {send_error}")


# Глобальный обработчик (инициализируется в main)
error_handler = None
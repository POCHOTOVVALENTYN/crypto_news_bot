"""
Middleware для автоматической проверки подписок
"""
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from typing import Callable, Dict, Any, Awaitable
import logging

from database import db

logger = logging.getLogger(__name__)


class SubscriptionCheckMiddleware(BaseMiddleware):
    """
    Автоматически проверяет и обновляет статус подписки
    при каждом взаимодействии пользователя с ботом
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем только для обычных сообщений от пользователей
        if isinstance(event, Message) and event.from_user and not event.from_user.is_bot:
            user_id = event.from_user.id
            
            try:
                # Проверяем подписку (автоматически обновляет статус если истекла)
                await db.check_subscription(user_id)
            except Exception as e:
                logger.error(f"Ошибка проверки подписки в middleware: {e}")
        
        # Продолжаем обработку
        return await handler(event, data)

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, ChatMemberUpdated
import logging

logger = logging.getLogger(__name__)

# ID группы, где бот должен молчать
SILENT_CHATS = [-1002393411639]

class SilentModeMiddleware(BaseMiddleware):
    """
    Middleware для полной блокировки активности бота в указанных чатах.
    Бот будет игнорировать ВСЕ события из этих чатов.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        chat_id = None
        
        # Определяем chat_id из события
        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id if event.message else None
        elif isinstance(event, ChatMemberUpdated):
            chat_id = event.chat.id
            
        # Если чат в списке "тихих" - прерываем обработку
        if chat_id in SILENT_CHATS:
            # Логируем только один раз или на уровне DEBUG, чтобы не спамить
            logger.debug(f"🔇 Silent Mode: пропущено событие из чата {chat_id}")
            return
            
        return await handler(event, data)

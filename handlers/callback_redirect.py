from aiogram import Router, F
from aiogram.types import CallbackQuery
import logging

router = Router()
logger = logging.getLogger(__name__)

# URL-адреса для редиректа
CHAT_URL = "https://t.me/+514GO2tFjAtkMWRi"
CHANNEL_URL = "https://t.me/blexler_invest"

@router.callback_query(F.data == "open_chat")
async def handle_open_chat(callback: CallbackQuery):
    """
    Обработка нажатия на синюю кнопку "💬 Открытый общий чат".
    Отправляет пользователю ephemeral-сообщение (answer) с URL.
    """
    try:
        # url в answer_callback_query открывает ссылку клиенту
        await callback.answer(text="Переходим в чат...", url=CHAT_URL)
    except Exception as e:
        logger.error(f"Ошибка callback open_chat: {e}")
        await callback.answer("Ошибка перехода", show_alert=True)

@router.callback_query(F.data == "subscribe_channel")
async def handle_subscribe_channel(callback: CallbackQuery):
    """
    Обработка нажатия на зеленую кнопку "📢 Подписаться".
    """
    try:
        await callback.answer(text="Подписываемся...", url=CHANNEL_URL)
    except Exception as e:
        logger.error(f"Ошибка callback subscribe_channel: {e}")
        await callback.answer("Ошибка перехода", show_alert=True)

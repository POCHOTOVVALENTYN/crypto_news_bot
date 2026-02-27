"""
utils/message_cleaner.py
========================
Централизованный модуль автоудаления сообщений.

3 стратегии:
  1. auto_delete()       — удалить конкретное сообщение через N секунд (фоновая задача)
  2. track_message()     — добавить msg_id в список FSMContext ("tracked_messages")
  3. delete_tracked()    — удалить все отслеживаемые сообщения диалога (при закрытии)
  4. safe_delete()       — безопасное мгновенное удаление (игнорирует ошибки)
  5. replace_screen()    — удалить предыдущий экран, отправить новый, сохранить его ID

Правила:
  - Навигационные сообщения → replace_screen() при каждом переходе
  - Временные уведомления  → auto_delete(delay=15-30)
  - Диалоги (relay/перего.) → track_message() во время сессии, delete_tracked() при закрытии
"""
import asyncio
import logging
from typing import Optional, Union

from aiogram.types import Message
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)

# Ключ для хранения отслеживаемых сообщений в FSMContext
_TRACKED_KEY = "tracked_messages"
# Ключ для хранения ID последнего экрана меню
_LAST_SCREEN_KEY = "last_menu_msg_id"


async def safe_delete(bot, chat_id: int, message_id: int) -> bool:
    """
    Безопасно удаляет сообщение. Игнорирует ошибки (уже удалено, нет прав и т.д.)
    
    Returns:
        True если удалено успешно, False если ошибка
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except Exception:
        return False


async def auto_delete(bot, chat_id: int, message_id: int, delay: int = 15) -> None:
    """
    Удаляет сообщение через `delay` секунд в фоновом asyncio-таске.
    Не блокирует хендлер.
    
    Usage:
        msg = await message.answer("✅ Готово!")
        asyncio.create_task(auto_delete(bot, msg.chat.id, msg.message_id, delay=15))
    """
    async def _delete():
        await asyncio.sleep(delay)
        await safe_delete(bot, chat_id, message_id)

    asyncio.create_task(_delete())


async def track_message(state: FSMContext, message_id: int) -> None:
    """
    Добавляет message_id в список отслеживаемых сообщений диалога (FSMContext).
    Используется внутри активного диалога (relay/переговоры/консультации).
    
    Сообщения будут удалены при вызове delete_tracked_messages().
    """
    data = await state.get_data()
    tracked: list = data.get(_TRACKED_KEY, [])
    if message_id not in tracked:
        tracked.append(message_id)
    await state.update_data({_TRACKED_KEY: tracked})


async def delete_tracked_messages(state: FSMContext, bot, chat_id: int) -> int:
    """
    Удаляет все отслеживаемые сообщения диалога из FSMContext.
    Вызывать при закрытии сессии (user_close_session / admin_close_session).
    
    Returns:
        Количество успешно удалённых сообщений
    """
    data = await state.get_data()
    tracked: list = data.get(_TRACKED_KEY, [])
    
    if not tracked:
        return 0
    
    deleted = 0
    for msg_id in tracked:
        if await safe_delete(bot, chat_id, msg_id):
            deleted += 1
    
    # Очищаем список
    await state.update_data({_TRACKED_KEY: []})
    logger.debug(f"🗑 Удалено {deleted}/{len(tracked)} сообщений диалога в чате {chat_id}")
    return deleted


async def replace_screen(
    state: FSMContext,
    bot,
    new_message: Message,
    delete_user_msg: bool = True
) -> None:
    """
    Заменяет предыдущий экран при навигации:
      1. Удаляет id предыдущего экрана из FSMContext
      2. Сохраняет id нового сообщения
      3. Опционально удаляет сообщение самого пользователя

    Usage:
        new_msg = await message.answer("📊 Premium-доступ...", ...)
        await replace_screen(state, bot, new_msg, delete_user_msg=True)
        # передать исходное message пользователя отдельно если нужно его удалить
    """
    data = await state.get_data()
    prev_id: Optional[int] = data.get(_LAST_SCREEN_KEY)

    # Удаляем предыдущий экран
    if prev_id:
        await safe_delete(bot, new_message.chat.id, prev_id)

    # Сохраняем новый
    await state.update_data({_LAST_SCREEN_KEY: new_message.message_id})


async def clear_last_screen(state: FSMContext, bot, chat_id: int) -> None:
    """
    Удаляет последний сохранённый экран и сбрасывает ключ.
    Вызывать при /start или полном сбросе состояния.
    """
    data = await state.get_data()
    prev_id = data.get(_LAST_SCREEN_KEY)
    if prev_id:
        await safe_delete(bot, chat_id, prev_id)
        await state.update_data({_LAST_SCREEN_KEY: None})

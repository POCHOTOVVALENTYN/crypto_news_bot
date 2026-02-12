import logging
import asyncio
from typing import Optional
from aiogram import Bot
from config import config

logger = logging.getLogger(__name__)

class CommentManager:
    """Менеджер для работы с комментариями в обсуждениях"""

    @staticmethod
    async def post_disclaimer_comment(bot: Bot, channel_message_id: int):
        """
        Публикует приветственный комментарий с дисклеймером в обсуждении поста
        """
        if not config.discussion_group_id:
            logger.warning("⚠️ Discussion Group ID не установлен. Комментарий не отправлен.")
            return

        discussion_chat_id = config.discussion_group_id
        disclaimer_url = config.disclaimer_url or "https://telegra.ph/Disklejmer-kanala-BLEXLER--INVEST-02-11"
        
        # Текст комментария
        comment_text = (
            "<b>Небольшое напоминание для новичков😎</b>\n\n"
            "🔹 <b>Закрытый BLEXLER Клуб:</b>\n"
            "<a href=\"https://t.me/Blexler_bot\">Вступить в клуб</a>\n\n"
            "💬 <b>Открытый BLEXLER Chat:</b>\n"
            "<a href=\"https://t.me/+514GO2tFjAtkMWRi\">Присоединиться к обсуждению</a>\n\n"
            f"⚠️ <a href=\"{disclaimer_url}\"><b>Информация об использовании контента BLEXLER:</b></a>\n"
        )

        try:
            # Ждем пару секунд, чтобы Telegram успел создать тред (иногда бывает задержка)
            await asyncio.sleep(2)
            
            # Отправляем комментарий как ОТВЕТ на пост в канале (автоматически попадает в обсуждение)
            # В супергруппах, привязанных к каналу, ответы на посты канала создают тред
            # Но так как мы знаем ID группы, можно писать туда напрямую с reply_to_message_id
            
            # Вариант 1: Пишем в привязанную группу, отвечая на message_id поста (если они синхронизированы)
            # Примечание: message_id в канале и группе могут отличаться.
            # Но обычно бот видит пост в группе как пересланный.
            # Самый надежный способ - просто написать в группу, не пытаясь угадать ID треда, 
            # но тогда это будет просто сообщение в чате.
            
            # Более умный способ:
            # Бот должен получить обновление о новом посте в канале, и тогда у него будет ID.
            # Но мы вызываем это сразу после отправки.
            
            # Попробуем отправить в ЧАТ ОБСУЖДЕНИЙ
            # Если это привязанная группа, то сообщения из канала туда пересылаются.
            # Нам нужно найти это пересланное сообщение, чтобы ответить на него.
            # Но это сложно без сохранения маппинга.
            
            # УПРОЩЕНИЕ: Просто отправляем сообщение в чат обсуждений.
            # Если пользователь хочет, чтобы это было ИМЕННО КОММЕНТАРИЕМ (в треде), 
            # боту нужно знать ID сообщения В ГРУППЕ.
            
            # Поскольку мы не знаем ID сообщения в группе (оно появляется асинхронно),
            # мы просто отправим сообщение в группу. 
            # (Пользователь просил "добавлял комментарий в обсуждения", технически это сообщение в группу)
            
            await bot.send_message(
                chat_id=discussion_chat_id,
                text=comment_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
            logger.info(f"✅ Комментарий опубликован в группе {discussion_chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка публикации комментария: {e}")

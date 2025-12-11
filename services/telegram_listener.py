# services/telegram_listener.py
import logging
import asyncio
from telethon import TelegramClient, events
from config import TG_API_ID, TG_API_HASH, SOURCE_CHANNELS
from database import db
from services.ai_summary import NewsAnalyzer

logger = logging.getLogger(__name__)


class TelegramListener:
    def __init__(self):
        # Создаем сессию 'anon_session' (сохранится в папке)
        self.client = TelegramClient('anon_session', TG_API_ID, TG_API_HASH)
        self.ai = NewsAnalyzer()
        self.source_channels = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]

    async def start(self):
        """Запуск прослушки"""
        if not TG_API_ID or not TG_API_HASH:
            logger.warning("⚠️ Не заданы TG_API_ID/HASH. Режим Userbot отключен.")
            return

        logger.info(f"🎧 Запуск Userbot... Слушаем каналы: {self.source_channels}")

        await self.client.start()

        # Регистрируем обработчик новых сообщений
        @self.client.on(events.NewMessage(chats=self.source_channels))
        async def handler(event):
            await self.handle_new_message(event)

        # Клиент будет работать в фоне, не блокируя основной бот
        # Мы не вызываем run_until_disconnected(), так как у нас есть основной цикл в main.py

    async def handle_new_message(self, event):
        """Обработка входящего сообщения"""
        try:
            raw_text = event.message.text
            if not raw_text:
                return

            source_name = event.chat.title if event.chat else "Unknown"
            logger.info(f"⚡️ Поймано сообщение из {source_name}: {raw_text[:30]}...")

            # 1. Проверка на дубликаты (чтобы не обрабатывать одно и то же)
            # Используем ID сообщения как часть уникального URL
            msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"

            if await db.news_exists(msg_unique_id):
                return

            # 2. Фильтрация и перевод через AI
            processed = await self.ai.process_incoming_news(raw_text)

            if processed:
                logger.info(f"✅ AI одобрил: {processed['ru_title']}")

                # 3. Сохраняем в БД (оно попадет в очередь на отправку)
                # Для таких новостей можно ставить image_url=None, они текстовые
                await db.add_news(
                    url=msg_unique_id,
                    title=processed['ru_title'],
                    summary=processed['ru_summary'],
                    source=f"Insider ({source_name})",
                    published_at="Just now",
                    image_url=None
                )
            else:
                logger.info("🗑️ AI отфильтровал новость как мусор")

        except Exception as e:
            logger.error(f"❌ Ошибка в Listener: {e}")


# Глобальный экземпляр
listener = TelegramListener()
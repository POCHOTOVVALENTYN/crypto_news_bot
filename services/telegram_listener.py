# services/telegram_listener.py
import logging
import asyncio
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import User, Channel
from config import TG_API_ID, TG_API_HASH, SOURCE_CHANNELS
from database import db
from services.ai_summary import NewsAnalyzer

logger = logging.getLogger(__name__)


class TelegramListener:
    def __init__(self):
        self.client = None
        self.ai = NewsAnalyzer()
        self.source_channels = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]
        self.is_running = False

    async def start(self):
        """Запуск прослушки (только если есть сессия)"""

        if not TG_API_ID or not TG_API_HASH:
            logger.warning("⚠️ TG_API_ID/HASH не установлены. Userbot выключен.")
            return

        try:
            # 1. Инициализация (Используем стандартные параметры, чтобы не пугать Telegram)
            self.client = TelegramClient(
                'anon_session',
                TG_API_ID,
                TG_API_HASH,
                device_model="Desktop",
                system_version="Windows 10",
                app_version="4.16.30"
            )

            logger.info("🎧 Подключение Userbot...")

            # 2. Просто подключаемся. НЕ вызываем start() с интерактивным вводом.
            await self.client.connect()

            # 3. Проверка: Если не авторизован - выходим, не блокируем бота.
            if not await self.client.is_user_authorized():
                logger.error("🛑 USERBOT НЕ АВТОРИЗОВАН!")
                logger.error("➡️ Остановите бота и запустите 'python auth.py' для входа.")
                # Не прерываем работу основного бота, просто отключаем слушателя
                await self.client.disconnect()
                return

            me = await self.client.get_me()
            logger.info(f"✅ Userbot запущен: {me.first_name} (@{me.username})")

            # 4. Подписка и запуск цикла событий
            accessible_entities = []
            for source_id in self.source_channels:
                try:
                    entity = await self.client.get_entity(source_id)
                    accessible_entities.append(entity)
                    name = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown'))
                    logger.info(f"✅ Слушаю: {name} (@{source_id})")
                except Exception as e:
                    logger.warning(f"⚠️ Канал не найден: @{source_id} ({e})")

            if not accessible_entities:
                logger.warning("⚠️ Нет доступных каналов для прослушки.")

            @self.client.on(events.NewMessage(chats=accessible_entities))
            async def handler(event):
                await self.handle_new_message(event)

            self.is_running = True
            # Клиент работает в фоне

        except Exception as e:
            logger.error(f"❌ Критическая ошибка Userbot: {e}", exc_info=True)

    async def handle_new_message(self, event):
        """Обработка сообщения"""
        try:
            raw_text = event.message.text
            if not raw_text or len(raw_text) < 20: return

            chat = await event.get_chat()
            source_title = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))

            # --- ПРЕ-ФИЛЬТРЫ ---
            STOP_WORDS = ["giveaway", "promo", "discount", "sign up"]
            if any(w in raw_text.lower() for w in STOP_WORDS): return
            # -------------------

            logger.info(f"⚡️ Поймано из {source_title}: {raw_text[:30]}...")

            msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"
            if await db.news_exists(msg_unique_id): return

            # Отправка в ИИ
            processed = await self.ai.process_incoming_news(raw_text)

            if processed:
                title = processed['ru_title']
                if await db.is_duplicate_by_content(title, threshold=85):
                    logger.info(f"♻️ Дубликат пропущен: {title}")
                    return

                logger.info(f"💎 ИНСАЙД: {title}")
                await db.add_news(
                    url=msg_unique_id,
                    title=title,
                    summary=processed['ru_summary'],
                    source=f"⚡ Insider ({source_title})",
                    published_at="Just now",
                    image_url=None,
                    priority=1
                )

        except Exception as e:
            logger.error(f"Ошибка в handle_new_message: {e}")

    async def stop(self):
        if self.client and self.is_running:
            await self.client.disconnect()
            self.is_running = False


listener = TelegramListener()
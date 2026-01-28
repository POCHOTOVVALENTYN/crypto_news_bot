# services/telegram_listener.py
import logging
import asyncio
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel
from config import TG_API_ID, TG_API_HASH, SOURCE_CHANNELS, TG_SESSION_STRING
from database import db
from services.ai_summary import NewsAnalyzer

logger = logging.getLogger(__name__)


class TelegramListener:
    def __init__(self):
        self.client = None
        self.ai = NewsAnalyzer()
        self.source_channels = SOURCE_CHANNELS if isinstance(SOURCE_CHANNELS, list) else []
        self.is_running = False
        # ✅ ИСПРАВЛЕНО: Семафор для ограничения параллельной обработки Userbot новостей (максимум 3 одновременно)
        self.processing_semaphore = asyncio.Semaphore(3)

    async def start(self):
        """Запуск прослушки (только если есть сессия)"""

        if not TG_API_ID or TG_API_ID == 0 or not TG_API_HASH:
            logger.warning("⚠️ TG_API_ID/HASH не установлены. Userbot выключен.")
            return

        if not self.source_channels:
            logger.warning("⚠️ SOURCE_CHANNELS пуст. Userbot выключен.")
            return

        try:
            # 1. Выбор типа сессии: StringSession (приоритет) или файл
            import os
            session_file = 'anon_session.session'
            
            if TG_SESSION_STRING:
                logger.info("✅ Использую StringSession из TG_SESSION_STRING")
                session = StringSession(TG_SESSION_STRING)
            elif os.path.exists(session_file):
                logger.info(f"📁 Использую найденный файл сессии: {session_file}")
                session = 'anon_session'
            else:
                logger.warning("⚠️ Сессия не найдена (нет TG_SESSION_STRING и файла anon_session.session).")
                logger.warning("🛑 Userbot будет ВЫКЛЮЧЕН. Запустите auth.py для авторизации.")
                return

            # 2. Инициализация клиента
            self.client = TelegramClient(
                session,
                TG_API_ID,
                TG_API_HASH
                # Не указываем device_model/system_version/app_version - используем стандартные
            )

            logger.info("🎧 Подключение Userbot...")

            # 3. Подключение (НЕ start() - это блокирует бота!)
            await self.client.connect()

            # 4. Проверка авторизации
            if not await self.client.is_user_authorized():
                logger.error("=" * 60)
                logger.error("🛑 USERBOT НЕ АВТОРИЗОВАН!")
                logger.error("=" * 60)
                logger.error("📋 ИНСТРУКЦИЯ:")
                logger.error("1. Остановите бота (Ctrl+C)")
                logger.error("2. Запустите: python auth.py")
                logger.error("3. Следуйте инструкциям для авторизации")
                logger.error("4. Добавьте TG_SESSION_STRING в .env")
                logger.error("5. Перезапустите бота")
                logger.error("=" * 60)
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
        """
        Обработка сообщения.
        ✅ ИСПРАВЛЕНО: Добавлен семафор для ограничения параллельной обработки.
        """
        # ✅ ИСПРАВЛЕНО: Ограничиваем параллельную обработку через семафор
        async with self.processing_semaphore:
            try:
                raw_text = event.message.text
                if not raw_text or len(raw_text) < 20: 
                    return

                chat = await event.get_chat()
                source_title = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))

                # --- ПРЕ-ФИЛЬТРЫ ---
                STOP_WORDS = ["giveaway", "promo", "discount", "sign up"]
                if any(w in raw_text.lower() for w in STOP_WORDS): 
                    return
                # -------------------

                logger.info(f"⚡️ Поймано из {source_title}: {raw_text[:30]}...")

                msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"
                if await db.news_exists(msg_unique_id): 
                    return

                # ✅ ИСПРАВЛЕНО: Добавлен таймаут для AI анализа (30 секунд)
                try:
                    processed = await asyncio.wait_for(
                        self.ai.analyze_text(raw_text, context="telegram_news"),
                        timeout=30.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"⏱️ AI анализ Userbot новости превысил таймаут (30 секунд), пропускаем")
                    return

                try:
                    importance_str = str(processed.get('importance', '0')).strip()
                    # Если AI вернуло 'High', 'Low' и т.д.
                    if importance_str.lower() == 'high':
                        importance = 9
                    elif importance_str.lower() == 'medium':
                        importance = 5
                    elif importance_str.lower() == 'low':
                        importance = 2
                    else:
                        # Пытаемся преобразовать число, убирая лишние символы
                        importance = int(''.join(filter(str.isdigit, importance_str)) or 0)
                except Exception:
                    importance = 0

                if processed and importance >= 5:
                    title = processed.get('summary', raw_text[:200])
                    if await db.is_duplicate_by_content(title, threshold=85):
                        logger.info(f"♻️ Дубликат пропущен: {title}")
                        return

                    logger.info(f"💎 ИНСАЙД: {title}")
                    await db.add_news(
                        url=msg_unique_id,
                        title=title,
                        summary=processed.get('summary', raw_text[:500]),
                        source=f"⚡ Insider ({source_title})",
                        published_at="Just now",
                        image_url=None,
                        priority=10  # Максимальный приоритет для Insider новостей
                    )

            except Exception as e:
                logger.error(f"Ошибка в handle_new_message: {e}", exc_info=True)

    async def stop(self):
        if self.client and self.is_running:
            await self.client.disconnect()
            self.is_running = False


listener = TelegramListener()
# services/telegram_listener.py
import logging
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError
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
        """Запуск прослушки (требует уже созданный файл сессии)"""

        if not TG_API_ID or not TG_API_HASH:
            logger.warning("⚠️ TG_API_ID/HASH не установлены. Userbot выключен.")
            return

        try:
            # 1. Инициализация клиента
            # ВАЖНО: Убрали system_version, чтобы Telegram не блокировал соединение
            self.client = TelegramClient('anon_session', TG_API_ID, TG_API_HASH)

            logger.info("🎧 Подключение Userbot...")

            # 2. Подключение (БЕЗ start(), используем connect())
            # Мы предполагаем, что auth.py уже создал сессию
            await self.client.connect()

            # 3. Проверка авторизации
            if not await self.client.is_user_authorized():
                logger.error("❌ ОШИБКА АВТОРИЗАЦИИ USERBOT!")
                logger.error("➡️ Запустите сначала 'python auth.py', чтобы войти в аккаунт.")
                return

            me = await self.client.get_me()
            logger.info(f"✅ Userbot активен: @{me.username or me.first_name}")

            # 4. Подписка на каналы
            accessible_entities = []
            for source_id in self.source_channels:
                try:
                    entity = await self.client.get_entity(source_id)
                    accessible_entities.append(entity)
                    name = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown'))
                    logger.info(f"✅ Слушаю источник: {name} (@{source_id})")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось найти канал @{source_id}: {e}")

            if not accessible_entities:
                logger.warning("⚠️ Нет доступных каналов для прослушки.")

            # 5. Обработчик сообщений
            @self.client.on(events.NewMessage(chats=accessible_entities))
            async def handler(event):
                await self.handle_new_message(event)

            self.is_running = True
            logger.info("🟢 Userbot успешно запущен и слушает эфир.")

        except Exception as e:
            logger.error(f"❌ Критическая ошибка запуска Userbot: {e}", exc_info=True)

    async def handle_new_message(self, event):
        """Обработка нового сообщения"""
        try:
            raw_text = event.message.text
            if not raw_text: return

            # Получаем информацию о чате
            chat = await event.get_chat()
            source_title = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))
            username = getattr(chat, 'username', '').lower() if getattr(chat, 'username', None) else ""

            # === ПРЕ-ФИЛЬТРЫ ===

            # Фильтр Whale Alert (мелочь)
            if "whale" in username:
                if "USD" in raw_text and "transferred" in raw_text:
                    # Пропускаем, если нет миллионов/миллиардов
                    if "1,000,000,000" not in raw_text and "500,000,000" not in raw_text and "Minted" not in raw_text:
                        return

                        # Фильтр рекламы
            STOP_WORDS = ["giveaway", "promo", "discount", "sign up", "limited offer"]
            if any(w in raw_text.lower() for w in STOP_WORDS):
                return

            if len(raw_text) < 20: return

            # === КОНЕЦ ФИЛЬТРОВ ===

            logger.info(f"⚡️ Поймано из {source_title}: {raw_text[:40]}...")

            msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"
            if await db.news_exists(msg_unique_id):
                return

            # Отправляем в ИИ
            processed = await self.ai.process_incoming_news(raw_text)

            if processed:
                title = processed['ru_title']

                # Проверка на дубликаты
                if await db.is_duplicate_by_content(title, threshold=85):
                    logger.info(f"♻️ Смысловой дубликат пропущен: {title}")
                    return

                logger.info(f"💎 ИНСАЙД ПРИНЯТ: {title}")

                await db.add_news(
                    url=msg_unique_id,
                    title=title,
                    summary=processed['ru_summary'],
                    source=f"⚡ Insider ({source_title})",
                    published_at="Just now",
                    image_url=None,
                    priority=1  # Высокий приоритет
                )

        except Exception as e:
            logger.error(f"Ошибка в handle_new_message: {e}")

    async def stop(self):
        if self.client and self.is_running:
            await self.client.disconnect()
            self.is_running = False


listener = TelegramListener()
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
        """Запуск прослушки с обработкой ошибок"""

        # Проверка конфигурации
        if not TG_API_ID or TG_API_ID == 0:
            logger.warning("⚠️ TG_API_ID не установлен. Userbot отключен.")
            logger.info("💡 Получите API ID: https://my.telegram.org/apps")
            return

        if not TG_API_HASH:
            logger.warning("⚠️ TG_API_HASH не установлен. Userbot отключен.")
            return

        if not self.source_channels:
            logger.warning("⚠️ SOURCE_CHANNELS пуст. Нечего слушать.")
            return

        try:
            # Создаем клиент
            self.client = TelegramClient(
                'anon_session',
                TG_API_ID,
                TG_API_HASH,
                system_version="4.16.30-vxCUSTOM"
            )

            logger.info(f"🎧 Запуск Userbot...")
            logger.info(f"📡 Источники для прослушки: {self.source_channels}")

            # Подключение
            await self.client.start()

            # Проверка авторизации
            if not await self.client.is_user_authorized():
                logger.error("❌ Userbot не авторизован!")
                return

            me = await self.client.get_me()
            logger.info(f"✅ Userbot: @{me.username or me.first_name}")

            # ✅ УЛУЧШЕННАЯ ПРОВЕРКА ДОСТУПА
            accessible_entities = []

            for source_id in self.source_channels:
                try:
                    entity = await self.client.get_entity(source_id)

                    # Определяем тип entity
                    if isinstance(entity, Channel):
                        name = entity.title
                        entity_type = "Канал"
                    elif isinstance(entity, User):
                        name = entity.first_name or entity.username
                        entity_type = "Пользователь"
                    else:
                        name = str(entity.id)
                        entity_type = "Неизвестно"

                    accessible_entities.append(entity)
                    logger.info(f"✅ {entity_type}: {name} (@{source_id})")

                except ValueError as e:
                    logger.error(f"❌ Неверный username: @{source_id}")
                    logger.info(f"💡 Проверьте username в SOURCE_CHANNELS")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка доступа @{source_id}: {e}")

            if not accessible_entities:
                logger.error("❌ Нет доступных источников!")
                logger.info("💡 Правильные форматы:")
                logger.info("  - Публичный канал: walterbloomberg")
                logger.info("  - Приватный канал: -1001234567890")
                logger.info("  - Пользователь: elonmusk")
                return

            # Регистрируем обработчик
            @self.client.on(events.NewMessage(chats=accessible_entities))
            async def handler(event):
                await self.handle_new_message(event)

            self.is_running = True
            logger.info(f"🟢 Userbot активен. Слушаю {len(accessible_entities)} источников...")

        except SessionPasswordNeededError:
            logger.error("❌ Требуется 2FA пароль!")
        except PhoneNumberInvalidError:
            logger.error("❌ Неверный номер телефона!")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска: {e}", exc_info=True)

    async def handle_new_message(self, event):
        """Обработка входящего сообщения"""
        try:
            raw_text = event.message.text
            if not raw_text: return

            # Определение источника (упрощенно)
            chat_id = event.chat_id
            # Можно получить username, если он доступен
            chat = await event.get_chat()
            username = chat.username.lower() if chat.username else ""

            # === 🛡️ ПРЕ-ФИЛЬТР (Экономим ИИ) ===

            # 1. Фильтр для Whale Alert (Игнорируем мелочь и USDT-USDC свопы)
            if "whale" in username:
                if "USD" in raw_text and "transferred" in raw_text:
                    # Если сумма меньше 50M - игнор (примерная логика, лучше regex)
                    # Простой способ: если нет слова "million" или число маленькое
                    if "50,000,000" not in raw_text and "100,000,000" not in raw_text:
                         # Это грубый пример, лучше настроить точнее
                         return
                if "Minted" in raw_text: # Печать тезера - это важно, оставляем
                    pass
                else:
                    return # Остальное пропускаем

            # 2. Фильтр стоп-слов (Реклама)
            STOP_WORDS = ["giveaway", "promo", "discount", "join vip", "sign up"]
            if any(w in raw_text.lower() for w in STOP_WORDS):
                logger.info(f"🗑️ Сработал стоп-слов фильтр")
                return

            # 3. Фильтр длины (слишком короткие "Hi", "GM")
            if len(raw_text) < 15:
                return

        # === КОНЕЦ ПРЕ-ФИЛЬТРА ===

        source_name = chat.title or "Unknown"
        logger.info(f"⚡️ Поймано из {source_name}: {raw_text[:30]}...")
        try:
            raw_text = event.message.text

            # Базовая фильтрация
            if not raw_text or len(raw_text) < 20:
                return

            # ✅ УЛУЧШЕНО: Получение имени источника
            if hasattr(event.chat, 'title'):
                source_name = event.chat.title
            elif hasattr(event.chat, 'first_name'):
                source_name = event.chat.first_name
            elif hasattr(event.chat, 'username'):
                source_name = f"@{event.chat.username}"
            else:
                source_name = "Unknown"

            logger.info(f"⚡️ Сообщение из {source_name}")

            # Уникальный ID
            msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"

            # Проверка дубликатов
            if await db.news_exists(msg_unique_id):
                return

            # ИИ обработка
            processed = await self.ai.process_incoming_news(raw_text)

            if not processed:
                logger.debug(f"Фильтр: {raw_text[:30]}...")
                return

            title = processed['ru_title']

            # Fuzzy дедупликация
            if await db.is_duplicate_by_content(title, threshold=85):
                logger.info(f"♻️ Дубликат: {title[:40]}...")
                return

            logger.info(f"💎 ИНСАЙД: {title}")

            # Сохранение
            await db.add_news(
                url=msg_unique_id,
                title=title,
                summary=processed['ru_summary'],
                source=f"⚡ Insider ({source_name})",
                published_at="Just now",
                image_url=None,
                priority=1  # МОЛНИЯ
            )

            logger.info("✅ Добавлен в очередь (HIGH PRIORITY)")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки: {e}", exc_info=True)

    async def stop(self):
        """Остановка"""
        if self.client and self.is_running:
            await self.client.disconnect()
            self.is_running = False
            logger.info("🛑 Userbot остановлен")


listener = TelegramListener()
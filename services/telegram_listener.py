# services/telegram_listener.py
import logging
import asyncio
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError
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
            logger.info("💡 Добавьте каналы в .env: SOURCE_CHANNELS=tier10k,walterbloomberg")
            return

        try:
            # Создаем клиент
            self.client = TelegramClient(
                'anon_session',
                TG_API_ID,
                TG_API_HASH,
                system_version="4.16.30-vxCUSTOM"  # Обход некоторых банов
            )

            logger.info(f"🎧 Запуск Userbot...")
            logger.info(f"📡 Слушаем каналы: {self.source_channels}")

            # Подключение
            await self.client.start()

            # Проверка авторизации
            if not await self.client.is_user_authorized():
                logger.error("❌ Userbot не авторизован!")
                logger.info("💡 Запустите скрипт первый раз с phone='+your_phone' для авторизации")
                return

            me = await self.client.get_me()
            logger.info(f"✅ Userbot подключен: @{me.username or me.first_name}")

            # ✅ ПРОВЕРКА ДОСТУПА К КАНАЛАМ
            accessible_channels = []
            for channel_username in self.source_channels:
                try:
                    entity = await self.client.get_entity(channel_username)
                    accessible_channels.append(channel_username)
                    logger.info(f"✅ Доступ к {entity.title}")
                except Exception as e:
                    logger.warning(f"⚠️ Нет доступа к @{channel_username}: {e}")

            if not accessible_channels:
                logger.error("❌ Нет доступных каналов для прослушки!")
                return

            # Регистрируем обработчик
            @self.client.on(events.NewMessage(chats=accessible_channels))
            async def handler(event):
                await self.handle_new_message(event)

            self.is_running = True
            logger.info("🟢 Userbot активен. Ожидаю сообщения...")

            # ✅ НЕ БЛОКИРУЕМ основной цикл
            # Telethon будет работать в фоне через event loop

        except SessionPasswordNeededError:
            logger.error("❌ Требуется 2FA пароль!")
            logger.info("💡 Добавьте password='your_2fa_pass' в client.start()")
        except PhoneNumberInvalidError:
            logger.error("❌ Неверный номер телефона!")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Userbot: {e}", exc_info=True)

    async def handle_new_message(self, event):
        """Обработка входящего сообщения"""
        try:
            raw_text = event.message.text

            # Фильтр по длине
            if not raw_text or len(raw_text) < 20:
                return

            # Игнорируем медиа-только сообщения
            if not raw_text.strip():
                return

            source_name = event.chat.title if hasattr(event.chat, 'title') else "Unknown"
            logger.info(f"⚡️ Новое сообщение из {source_name}")

            # 1. Проверка по URL (строгая дедупликация)
            msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"
            if await db.news_exists(msg_unique_id):
                logger.debug("Уже в БД (по URL)")
                return

            # 2. ИИ Обработка (строгая фильтрация)
            processed = await self.ai.process_incoming_news(raw_text)

            if not processed:
                logger.debug(f"ИИ отфильтровал: {raw_text[:50]}...")
                return

            title = processed['ru_title']

            # 3. Fuzzy дедупликация (защита от похожих новостей)
            if await db.is_duplicate_by_content(title, threshold=85):
                logger.info(f"♻️ Дубликат (fuzzy): {title[:40]}...")
                return

            logger.info(f"💎 ИНСАЙД: {title}")

            # 4. Сохранение с HIGH priority
            await db.add_news(
                url=msg_unique_id,
                title=title,
                summary=processed['ru_summary'],
                source=f"⚡ Insider ({source_name})",
                published_at="Just now",
                image_url=None,  # Картинку подберет formatter
                priority=1  # 🚨 МОЛНИЯ
            )

            logger.info("✅ Инсайд добавлен в очередь с высоким приоритетом")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)

    async def stop(self):
        """Остановка Userbot"""
        if self.client and self.is_running:
            await self.client.disconnect()
            self.is_running = False
            logger.info("🛑 Userbot остановлен")


# Глобальный экземпляр
listener = TelegramListener()
# services/telegram_listener.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)
import logging
from pathlib import Path
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError
from telethon.sessions import StringSession
from config import config
from database import db
from services.ai_summary import NewsAnalyzer

logger = logging.getLogger(__name__)


class TelegramListener:
    def __init__(self):
        self.client = None
        self.ai = NewsAnalyzer()
        self.source_channels = config.get_source_channels_list()
        self.is_running = False
        self.session_string = None

    async def _load_or_migrate_session(self) -> StringSession:
        """
        Загружает StringSession из переменной окружения или мигрирует файл сессии.
        ✅ ИСПРАВЛЕНО: Используем async методы
        """

        # 1. Проверяем переменную окружения
        if config.tg_session_string:
            logger.info("✅ Использую StringSession из TG_SESSION_STRING")
            return StringSession(config.tg_session_string)

        # 2. Проверяем файл сессии (legacy)
        session_file = Path("anon_session.session")
        if session_file.exists():
            logger.warning("⚠️ ОБНАРУЖЕН ФАЙЛ СЕССИИ (небезопасно!)")
            logger.warning("🔄 Мигрирую в StringSession...")

            # ✅ ИСПРАВЛЕНО: Используем async методы
            temp_client = TelegramClient(
                "anon_session",
                config.tg_api_id,
                config.tg_api_hash
            )

            try:
                await temp_client.connect()  # ✅ await добавлен

                if not await temp_client.is_user_authorized():  # ✅ await добавлен
                    logger.error("❌ Сессия не авторизована!")
                    await temp_client.disconnect()
                    return StringSession()

                session_str = temp_client.session.save()
                await temp_client.disconnect()

                # Выводим строку для добавления в .env
                logger.info("=" * 60)
                logger.info("📋 СКОПИРУЙТЕ ЭТУ СТРОКУ В .env:")
                logger.info(f"TG_SESSION_STRING={session_str}")
                logger.info("=" * 60)
                logger.warning(f"⚠️ После добавления в .env удалите файл: rm {session_file}")

                return StringSession(session_str)
            except Exception as e:
                logger.error(f"❌ Ошибка миграции сессии: {e}")
                await temp_client.disconnect()
                return StringSession()

        # 3. Пустая сессия (первый запуск)
        logger.info("🆕 Создаю новую сессию (потребуется авторизация)")
        return StringSession()

    async def start(self):
        """Запуск прослушки с обработкой ошибок"""

        # 1. Проверка конфигурации
        if config.tg_api_id == 0:
            logger.warning("⚠️ TG_API_ID не установлен. Userbot отключен.")
            return

        if not config.tg_api_hash:
            logger.warning("⚠️ TG_API_HASH не установлен. Userbot отключен.")
            return

        if not self.source_channels:
            logger.warning("⚠️ SOURCE_CHANNELS пуст. Нечего слушать.")
            return

        try:
            # 2. Загружаем или мигрируем сессию
            session = await self._load_or_migrate_session()  # ✅ await добавлен

            # 3. Создаем клиент
            self.client = TelegramClient(
                session,
                config.tg_api_id,
                config.tg_api_hash,
                system_version="4.16.30-vxCUSTOM"
            )

            logger.info("🎧 Запуск Userbot...")
            logger.info(f"📡 Источники: {self.source_channels}")

            # 4. Подключение
            await self.client.start()

            # 5. Проверка авторизации
            if not await self.client.is_user_authorized():
                logger.error("❌ Userbot не авторизован!")
                logger.error("💡 Запустите интерактивную авторизацию:")
                logger.error(
                    "💡 python -c 'from services.telegram_listener import setup_userbot; import asyncio; asyncio.run(setup_userbot())'")
                return

            me = await self.client.get_me()
            logger.info(f"✅ Userbot активен: @{me.username or me.first_name}")

            # 6. Сохраняем StringSession для вывода (если новая)
            if not config.tg_session_string:
                self.session_string = self.client.session.save()
                logger.info("=" * 60)
                logger.info("📋 НОВАЯ СЕССИЯ - ДОБАВЬТЕ В .env:")
                logger.info(f"TG_SESSION_STRING={self.session_string}")
                logger.info("=" * 60)

            # 7. Разрешение имен каналов
            accessible_entities = []
            for source_id in self.source_channels:
                try:
                    entity = await self.client.get_entity(source_id)
                    accessible_entities.append(entity)

                    name = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown'))
                    logger.info(f"✅ Подключено: {name} (@{source_id})")

                except Exception as e:
                    logger.warning(f"⚠️ Не удалось подключиться к @{source_id}: {e}")

            if not accessible_entities:
                logger.error("❌ Нет доступных источников для прослушки.")
                return

            # 8. Регистрируем обработчик событий
            @self.client.on(events.NewMessage(chats=accessible_entities))
            async def handler(event):
                await self.handle_new_message(event)

            self.is_running = True
            logger.info(f"🟢 Слушаю {len(accessible_entities)} каналов...")

        except SessionPasswordNeededError:
            logger.error("❌ Требуется 2FA пароль! Установите пароль вручную.")
        except PhoneNumberInvalidError:
            logger.error("❌ Неверный номер телефона или API credentials.")
            logger.error("💡 Формат номера должен быть: +380635609097 (с кодом страны)")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка Userbot: {e}", exc_info=True)

    async def handle_new_message(self, event):
        """Обработка входящего сообщения (Фильтрация -> ИИ -> БД)"""
        try:
            raw_text = event.message.text
            if not raw_text:
                return

            # Получаем информацию об источнике
            chat = await event.get_chat()
            source_title = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))
            username = (getattr(chat, 'username', '') or "").lower()

            # === ПРЕ-ФИЛЬТР ===

            # 1. Whale Alert (крупные транзакции)
            if "whale" in username:
                if "transferred" in raw_text and "USD" in raw_text:
                    if not any(x in raw_text for x in ["1,000,000,000", "500,000,000", "Minted"]):
                        return

            # 2. Стоп-слова
            STOP_WORDS = ["giveaway", "promo", "discount", "join vip", "sign up", "limited offer"]
            if any(w in raw_text.lower() for w in STOP_WORDS):
                return

            # 3. Минимальная длина
            if len(raw_text) < 20:
                return

            logger.info(f"⚡️ Поймано из {source_title}: {raw_text[:40]}...")

            # Проверка дубликатов по ID
            msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"
            if await db.news_exists(msg_unique_id):
                return

            # Обработка через ИИ (с проверкой доступности)
            processed = await self.ai.process_incoming_news(raw_text)

            if processed and isinstance(processed, dict):
                title = processed.get('ru_title')
                summary = processed.get('ru_summary')

                if not title or not summary:
                    logger.warning(f"⚠️ AI вернул неполные данные. Ключи: {list(processed.keys())}")
                    return

                # Fuzzy дедупликация
                if await db.is_duplicate_by_content(title, threshold=85):
                    logger.info(f"♻️ Пропуск дубликата: {title}")
                    return

                logger.info(f"💎 ВАЖНЫЙ ИНСАЙД: {title}")

                # Сохранение с высоким приоритетом
                await db.add_news(
                    url=msg_unique_id,
                    title=title,
                    summary=summary,
                    source=f"⚡ Insider ({source_title})",
                    published_at="Just now",
                    image_url=None,
                    priority=1  # Молния!
                )
            else:
                logger.debug("🗑️ ИИ отфильтровал как неважное или вернул невалидные данные")

        except Exception as e:
            logger.error(f"❌ Ошибка обработчика сообщений: {e}", exc_info=True)

    async def stop(self):
        """Корректная остановка"""
        if self.client and self.is_running:
            await self.client.disconnect()
            self.is_running = False
            logger.info("🛑 Userbot остановлен")


# Глобальный экземпляр
listener = TelegramListener()


# ✅ НОВОЕ: Вспомогательная функция для первичной настройки
async def setup_userbot():
    """
    Интерактивная настройка Userbot (запускается отдельно).

    Usage:
        python -c "from services.telegram_listener import setup_userbot; import asyncio; asyncio.run(setup_userbot())"
    """
    from config import config

    if not config.tg_api_id or not config.tg_api_hash:
        print("❌ TG_API_ID и TG_API_HASH должны быть установлены в .env")
        return

    client = TelegramClient(StringSession(), config.tg_api_id, config.tg_api_hash)

    print("🔐 Запуск интерактивной авторизации...")
    await client.start()

    me = await client.get_me()
    print(f"✅ Авторизован как: @{me.username or me.first_name}")

    session_str = client.session.save()
    print("\n" + "=" * 60)
    print("📋 СКОПИРУЙТЕ ЭТУ СТРОКУ В .env:")
    print(f"TG_SESSION_STRING={session_str}")
    print("=" * 60)

    await client.disconnect()
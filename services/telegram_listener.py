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
        # Очищаем список каналов от пробелов и пустых строк
        self.source_channels = [ch.strip() for ch in SOURCE_CHANNELS if ch.strip()]
        self.is_running = False

    async def start(self):
        """Запуск прослушки с обработкой ошибок"""

        # 1. Проверка конфигурации
        if not TG_API_ID or TG_API_ID == 0:
            logger.warning("⚠️ TG_API_ID не установлен. Userbot отключен.")
            return

        if not TG_API_HASH:
            logger.warning("⚠️ TG_API_HASH не установлен. Userbot отключен.")
            return

        if not self.source_channels:
            logger.warning("⚠️ SOURCE_CHANNELS пуст. Нечего слушать.")
            return

        try:
            # 2. Создаем клиент (Session name: anon_session)
            self.client = TelegramClient(
                'anon_session',
                TG_API_ID,
                TG_API_HASH,
                system_version="4.16.30-vxCUSTOM"
            )

            logger.info(f"🎧 Запуск Userbot...")
            logger.info(f"📡 Источники: {self.source_channels}")

            # 3. Подключение
            await self.client.start()

            # 4. Проверка авторизации
            if not await self.client.is_user_authorized():
                logger.error("❌ Userbot не авторизован! Запустите бота локально и введите код.")
                return

            me = await self.client.get_me()
            logger.info(f"✅ Userbot активен: @{me.username or me.first_name}")

            # 5. Разрешение имен каналов (превращаем username в entity)
            accessible_entities = []
            for source_id in self.source_channels:
                try:
                    # Пытаемся получить объект канала/пользователя
                    entity = await self.client.get_entity(source_id)
                    accessible_entities.append(entity)

                    name = getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown'))
                    logger.info(f"✅ Подключено: {name} (@{source_id})")

                except Exception as e:
                    logger.warning(f"⚠️ Не удалось подключиться к @{source_id}: {e}")

            if not accessible_entities:
                logger.error("❌ Нет доступных источников для прослушки.")
                return

            # 6. Регистрируем обработчик событий (Новые сообщения)
            @self.client.on(events.NewMessage(chats=accessible_entities))
            async def handler(event):
                await self.handle_new_message(event)

            self.is_running = True
            logger.info(f"🟢 Слушаю {len(accessible_entities)} каналов...")

        except SessionPasswordNeededError:
            logger.error("❌ Ошибка входа: Требуется 2FA пароль!")
        except PhoneNumberInvalidError:
            logger.error("❌ Ошибка входа: Неверный номер телефона/хеш!")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка Userbot: {e}", exc_info=True)

    async def handle_new_message(self, event):
        """Обработка входящего сообщения (Фильтрация -> ИИ -> БД)"""
        try:
            raw_text = event.message.text
            if not raw_text:
                return

            # --- СБОР ИНФОРМАЦИИ ОБ ИСТОЧНИКЕ ---
            chat = await event.get_chat()

            # Получаем название для логов
            source_title = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))

            # Получаем username для фильтров (в нижнем регистре)
            username = getattr(chat, 'username', '') or ""
            username = username.lower()

            # === 🛡️ ПРЕ-ФИЛЬТР (Экономим ресурсы ИИ) ===

            # 1. Фильтр для Whale Alert (игнорируем мелкие транзакции)
            if "whale" in username:
                # Если в тексте нет миллионов (крупных сумм) и это не 'Minted' (печать)
                # Логика: если это обычный перевод (transferred) и сумма маленькая
                if "transferred" in raw_text and "USD" in raw_text:
                    # Простой эвристический фильтр: ищем большие числа или слова markers
                    if "1,000,000,000" not in raw_text and "500,000,000" not in raw_text and "Minted" not in raw_text:
                        # Если это не миллиардный перевод и не минтинг - пропускаем
                        # (Можно настроить точнее под ваши нужды)
                        return

                        # 2. Фильтр стоп-слов (Реклама, спам)
            STOP_WORDS = ["giveaway", "promo", "discount", "join vip", "sign up", "limited offer"]
            if any(w in raw_text.lower() for w in STOP_WORDS):
                return

            # 3. Фильтр длины (слишком короткие сообщения неинформативны)
            if len(raw_text) < 20:
                return

            # === КОНЕЦ ПРЕ-ФИЛЬТРА ===

            logger.info(f"⚡️ Поймано из {source_title}: {raw_text[:40]}...")

            # --- ПРОВЕРКА НА ДУБЛИКАТЫ (По ID сообщения) ---
            # Формируем уникальный ID: tg_IDКанала_IDСообщения
            msg_unique_id = f"tg_{event.chat_id}_{event.message.id}"

            if await db.news_exists(msg_unique_id):
                return

            # --- ОБРАБОТКА ЧЕРЕЗ ИИ (Gemini) ---
            # Отправляем текст в Gemini, чтобы он решил: "High Importance" или нет
            processed = await self.ai.process_incoming_news(raw_text)

            if processed:
                title = processed['ru_title']

                # --- УМНАЯ ДЕДУПЛИКАЦИЯ (Fuzzy Matching) ---
                # Если такая же новость уже была (даже с другим ID), пропускаем
                if await db.is_duplicate_by_content(title, threshold=85):
                    logger.info(f"♻️ Пропуск смыслового дубликата: {title}")
                    return

                logger.info(f"💎 ВАЖНЫЙ ИНСАЙД: {title}")

                # --- СОХРАНЕНИЕ В БД (С ВЫСОКИМ ПРИОРИТЕТОМ) ---
                await db.add_news(
                    url=msg_unique_id,
                    title=title,
                    summary=processed['ru_summary'],
                    source=f"⚡ Insider ({source_title})",
                    published_at="Just now",
                    image_url=None,  # У текстовых молний обычно нет картинки
                    priority=1  # 🚨 ВАЖНО: Приоритет 1 заставит main.py отправить это МГНОВЕННО
                )
            else:
                # Если ИИ вернул None (решил, что новость Low importance)
                logger.debug("🗑️ ИИ отфильтровал новость как неважную")

        except Exception as e:
            logger.error(f"❌ Ошибка в обработчике сообщений: {e}")

    async def stop(self):
        """Корректная остановка"""
        if self.client and self.is_running:
            await self.client.disconnect()
            self.is_running = False
            logger.info("🛑 Userbot остановлен")


# Создаем глобальный экземпляр класса
listener = TelegramListener()
# database.py
import aiosqlite
import logging
from typing import Optional, Dict, List
from thefuzz import fuzz

DB_PATH = "crypto_news.db"
logger = logging.getLogger(__name__)


class NewsDatabase:
    def __init__(self):
        self.db_path = DB_PATH
        self.conn = None  # Постоянное соединение для relay_manager


    async def init(self):
        # Создаём постоянное соединение
        self.conn = await aiosqlite.connect(self.db_path)
        
        async with aiosqlite.connect(self.db_path) as db:
            # Добавили колонку priority (0-10 - расширенная система приоритетов)
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS news
                             (
                                 id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                                 url                TEXT UNIQUE NOT NULL,
                                 title              TEXT        NOT NULL,
                                 summary            TEXT,
                                 full_content       TEXT,
                                 image_url          TEXT,
                                 source             TEXT        NOT NULL,
                                 published_at       TEXT        NOT NULL,
                                 added_at           TEXT    DEFAULT CURRENT_TIMESTAMP,
                                 posted_to_telegram BOOLEAN DEFAULT 0,
                                 priority           INTEGER DEFAULT 0,
                                 priority           INTEGER DEFAULT 0,
                                 telegram_message_id INTEGER DEFAULT NULL,
                                 category           TEXT,
                                 sentiment_score    INTEGER,
                                 why_it_matters     TEXT
                             )
                             """)
            
            # ✅ МИГРАЦИЯ: Добавляем колонку full_content если её нет
            try:
                # Проверяем существование колонок
                async with db.execute("PRAGMA table_info(news)") as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]
                    
                    if 'full_content' not in columns:
                        await db.execute("ALTER TABLE news ADD COLUMN full_content TEXT")
                        await db.commit()
                        logger.info("✅ Добавлена колонка full_content в таблицу news")
                        
                    if 'telegram_message_id' not in columns:
                        await db.execute("ALTER TABLE news ADD COLUMN telegram_message_id INTEGER")
                        await db.commit()
                        logger.info("✅ Добавлена колонка telegram_message_id в таблицу news")
                    
                    # ✅ НОВОЕ: Добавляем metadata для Telegram источников
                    if 'metadata' not in columns:
                        await db.execute("ALTER TABLE news ADD COLUMN metadata TEXT")
                        await db.commit()
                        logger.info("✅ Добавлена колонка metadata в таблицу news")
                    
                    # ✅ НОВОЕ: Добавляем digest_batch_id для группировки в дайджестах
                    if 'digest_batch_id' not in columns:
                        await db.execute("ALTER TABLE news ADD COLUMN digest_batch_id INTEGER")
                        await db.commit()
                        logger.info("✅ Добавлена колонка digest_batch_id в таблицу news")

                    # ✅ НОВОЕ: Digest 2.0 fields
                    if 'category' not in columns:
                        await db.execute("ALTER TABLE news ADD COLUMN category TEXT")
                        await db.execute("ALTER TABLE news ADD COLUMN sentiment_score INTEGER")
                        await db.execute("ALTER TABLE news ADD COLUMN why_it_matters TEXT")
                        await db.commit()
                        logger.info("✅ Добавлены колонки Digest 2.0 (category, sentiment, why_it_matters) в таблицу news")
                        
            except Exception as e:
                # Игнорируем ошибки миграции
                logger.debug(f"⚠️ Миграция: {e}")
            
            # ✅ МИГРАЦИЯ: Добавляем колонки для модерации Stories
            try:
                async with db.execute("PRAGMA table_info(user_activities)") as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]
                    
                    if 'verification_status' not in columns:
                        await db.execute("ALTER TABLE user_activities ADD COLUMN verification_status TEXT")
                        await db.execute("ALTER TABLE user_activities ADD COLUMN ai_confidence REAL")
                        await db.execute("ALTER TABLE user_activities ADD COLUMN reviewed_by INTEGER")
                        await db.execute("ALTER TABLE user_activities ADD COLUMN reviewed_at DATETIME")
                        await db.execute("ALTER TABLE user_activities ADD COLUMN local_file_path TEXT")
                        await db.execute("ALTER TABLE user_activities ADD COLUMN image_hash TEXT")
                        await db.commit()
                        logger.info("✅ Добавлены колонки для модерации Stories")
            except Exception as e:
                logger.debug(f"⚠️ Миграция модерации: {e}")
            
            # Добавляем индекс для быстрого поиска по приоритету
            await db.execute("""
                             CREATE INDEX IF NOT EXISTS idx_priority_posted 
                             ON news(priority DESC, posted_to_telegram, id ASC)
                             """)
            
            # Индекс для быстрого поиска проверок на модерации
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_stories 
                ON user_activities(verification_status, created_at DESC)
            """)
            
            # Таблица настроек (key-value store)
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS settings
                             (
                                 key   TEXT PRIMARY KEY,
                                 value TEXT
                             )
                             """)
            
            # === НОВЫЕ ТАБЛИЦЫ ДЛЯ ПОЛЬЗОВАТЕЛЬСКОЙ СИСТЕМЫ ===
            
            # Таблица пользователей
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS users
                             (
                                 user_id INTEGER PRIMARY KEY,
                                 username TEXT,
                                 full_name TEXT,
                                 status TEXT DEFAULT 'free',  -- 'free' / 'premium'
                                 subscription_end DATETIME,
                                 joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 
                                 -- Поля для аналитики воронки продаж
                                 first_offer_shown_at DATETIME,
                                 discount_offer_shown_at DATETIME,
                                 total_purchases INTEGER DEFAULT 0,
                                 lifetime_spent INTEGER DEFAULT 0
                             )
                             """)
            
            # Таблица платежей
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS payments
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 user_id INTEGER NOT NULL,
                                 
                                 -- Детали платежа
                                 amount_stars INTEGER NOT NULL,
                                 discount_used BOOLEAN DEFAULT 0,
                                 telegram_payment_charge_id TEXT,
                                 payment_uuid TEXT UNIQUE,  -- Уникальный UUID для отслеживания
                                 
                                 -- Метрики
                                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 status TEXT DEFAULT 'pending',  -- 'pending' / 'completed' / 'failed'
                                 
                                 -- Связь с воронкой
                                 funnel_step TEXT,  -- 'full_price' / 'discount_price'
                                 
                                 FOREIGN KEY (user_id) REFERENCES users(user_id)
                             )
                             """)
            
            # Миграция: добавляем payment_uuid если его нет
            try:
                async with db.execute("PRAGMA table_info(payments)") as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]
                    
                    if 'payment_uuid' not in columns:
                        await db.execute("ALTER TABLE payments ADD COLUMN payment_uuid TEXT")
                        await db.commit()
                        logger.info("✅ Добавлена колонка payment_uuid в таблицу payments")
            except Exception as e:
                logger.debug(f"⚠️ Миграция payments: {e}")
            
            # Таблица статистики воронки продаж
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS funnel_stats
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 user_id INTEGER NOT NULL,
                                 
                                 -- Шаги воронки
                                 step TEXT NOT NULL,  -- 'offer_shown' / 'price_objection' / 'purchase' / etc
                                 
                                 -- Метаданные
                                 happened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 metadata TEXT,  -- JSON с дополнительными данными
                                 
                                 FOREIGN KEY (user_id) REFERENCES users(user_id)
                             )
                             """)
            
            # Таблица рефералов
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS referrals
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 referrer_id INTEGER NOT NULL,
                                 referred_id INTEGER NOT NULL,
                                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 reward_given BOOLEAN DEFAULT 0,
                                 referral_depth INTEGER DEFAULT 1,
                                 
                                 FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                                 FOREIGN KEY (referred_id) REFERENCES users(user_id),
                                 UNIQUE(referrer_id, referred_id)
                             )
                             """)
            
            # Таблица активности пользователей (для бейджей и геймификации)
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS user_activities
                             (
                                 id            INTEGER PRIMARY KEY AUTOINCREMENT,
                                 user_id       INTEGER NOT NULL,
                                 activity_type TEXT    NOT NULL,
                                 xp_earned     INTEGER DEFAULT 0,
                                 created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 metadata      TEXT,
                                 FOREIGN KEY (user_id) REFERENCES users (user_id)
                             )
                             """)
            
            # === ТАБЛИЦЫ ДЛЯ RELAY MODE (ПОДДЕРЖКА И КОНСУЛЬТАЦИИ) ===
            
            # Таблица сессий поддержки
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS support_sessions
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 user_id INTEGER NOT NULL,
                                 type TEXT NOT NULL,
                                 current_admin_id INTEGER,
                                 admin_cascade_level INTEGER DEFAULT 1,
                                 status TEXT DEFAULT 'active',
                                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 resolved_at DATETIME,
                                 escalation_attempts INTEGER DEFAULT 0,
                                 related_consultation_id INTEGER,
                                 FOREIGN KEY (user_id) REFERENCES users(user_id)
                             )
                             """)
            
            # Таблица сообщений поддержки
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS support_messages
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 session_id INTEGER NOT NULL,
                                 from_user_id INTEGER NOT NULL,
                                 to_user_id INTEGER NOT NULL,
                                 message_text TEXT,
                                 message_type TEXT DEFAULT 'text',
                                 telegram_message_id INTEGER,
                                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 FOREIGN KEY (session_id) REFERENCES support_sessions(id)
                             )
                             """)
            
            # Таблица консультаций
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS consultations
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 user_id INTEGER NOT NULL,
                                 type TEXT NOT NULL,
                                 amount_paid INTEGER NOT NULL,
                                 amount_usd INTEGER NOT NULL,
                                 status TEXT DEFAULT 'paid',
                                 scheduled_datetime DATETIME,
                                 payment_id INTEGER,
                                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 completed_at DATETIME,
                                 notes TEXT,
                                 FOREIGN KEY (user_id) REFERENCES users(user_id),
                                 FOREIGN KEY (payment_id) REFERENCES payments(id)
                             )
                             """)
            
            # ✅ НОВОЕ: Таблица дайджестов новостей
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS news_digests
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 type TEXT NOT NULL,
                                 published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 telegram_message_id INTEGER,
                                 news_count INTEGER DEFAULT 0
                             )
                             """)
            
            # ✅ НОВОЕ: Таблица модерации breaking news
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS pending_breaking_news
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 news_url TEXT NOT NULL,
                                 detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 admin_approved_by INTEGER DEFAULT NULL,
                                 admin_decision TEXT DEFAULT 'pending',
                                 published_at DATETIME DEFAULT NULL,
                                 auto_published BOOLEAN DEFAULT 0,
                                 FOREIGN KEY (news_url) REFERENCES news(url)
                             )
                             """)
            
            # Таблица напоминаний о консультациях
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS consultation_reminders
                             (
                                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                                 consultation_id INTEGER NOT NULL,
                                 reminder_type TEXT NOT NULL,
                                 sent BOOLEAN DEFAULT 0,
                                 scheduled_time DATETIME NOT NULL,
                                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                 FOREIGN KEY (consultation_id) REFERENCES consultations(id)
                             )
                             """)
            
            # Миграции для геймификации
            try:
                async with db.execute("PRAGMA table_info(users)") as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]
                    
                    if 'xp' not in columns:
                        await db.execute("ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0")
                        logger.info("✅ Добавлена колонка xp в таблицу users")
                    
                    if 'level' not in columns:
                        await db.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
                        logger.info("✅ Добавлена колонка level в таблицу users")
                    
                    if 'last_activity' not in columns:
                        await db.execute("ALTER TABLE users ADD COLUMN last_activity DATETIME")
                        logger.info("✅ Добавлена колонка last_activity в таблицу users")
                    
                    await db.commit()
            except Exception as e:
                logger.debug(f"⚠️ Миграция геймификации: {e}")
            
            await db.commit()

    async def close(self):
        """Закрывает соединение с БД (для совместимости, так как используем контекстные менеджеры)"""
        pass

    async def execute(self, query: str, args=()):
        """Выполняет SQL запрос и возвращает результат (для статистики)"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, args) as cursor:
                # Если это SELECT count(*), возвращаем число
                if "SELECT COUNT" in query.upper():
                    row = await cursor.fetchone()
                    return row[0] if row else 0
                # Иначе возвращаем все строки
                return await cursor.fetchall()

    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Получает значение настройки по ключу"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        """Сохраняет значение настройки"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
                (key, value, value)
            )
            await db.commit()

    async def get_statistics(self) -> Dict:
        """Получает статистику по базе данных"""
        stats = {}
        async with aiosqlite.connect(self.db_path) as db:
            # Всего новостей
            async with db.execute("SELECT COUNT(*) FROM news") as cursor:
                stats['total_news'] = (await cursor.fetchone())[0]
            
            # Опубликовано в Telegram
            async with db.execute("SELECT COUNT(*) FROM news WHERE posted_to_telegram = 1") as cursor:
                stats['posted_count'] = (await cursor.fetchone())[0]
                
            # В очереди (не опубликовано)
            async with db.execute("SELECT COUNT(*) FROM news WHERE posted_to_telegram = 0") as cursor:
                stats['queue_count'] = (await cursor.fetchone())[0]
                
            # Сегодняшние новости
            async with db.execute("SELECT COUNT(*) FROM news WHERE date(added_at) = date('now')") as cursor:
                stats['today_count'] = (await cursor.fetchone())[0]
                
        return stats


    async def news_exists(self, url: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM news WHERE url = ?", (url,)) as cursor:
                return await cursor.fetchone() is not None

    async def is_duplicate_by_content(self, title: str, threshold: int = 85) -> bool:
        """Проверяет, нет ли похожей новости в последних 50 записях"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Берем последние 50 новостей
                async with db.execute("SELECT title FROM news ORDER BY id DESC LIMIT 50") as cursor:
                    rows = await cursor.fetchall()

                for row in rows:
                    existing_title = row[0]
                    # Сравниваем похожесть строк (0-100)
                    ratio = fuzz.token_sort_ratio(title.lower(), existing_title.lower())
                    if ratio >= threshold:
                        logger.info(f"♻️ Найден дубликат (сходство {ratio}%): '{title}' == '{existing_title}'")
                        return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при fuzzy matching: {e}")
            return False

    async def save_custom_price(self, session_id: int, user_id: int, amount: int):
        """Сохранить кастомную цену для сессии переговоров"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """UPDATE support_sessions 
                       SET custom_price = ? 
                       WHERE id = ? AND user_id = ?""",
                    (amount, session_id, user_id)
                )
                await db.commit()
            logger.info(f"💰 Custom price {amount}⭐ saved for session {session_id}")
        except Exception as e:
            logger.error(f"Error saving custom price: {e}")
            raise

    async def add_news(self, url: str, title: str, summary: str, source: str,
                       published_at: str, image_url: str = None, priority: int = 0,
                       full_content: str = None, metadata: str = None,
                       category: str = None, sentiment_score: int = None, why_it_matters: str = None) -> bool:
        """
        Добавляет новость в БД
        
        Args:
            url: URL новости
            title: Заголовок
            summary: Краткое описание (для обратной совместимости)
            source: Источник
            published_at: Дата публикации
            image_url: URL изображения
            priority: Приоритет (0-10)
            full_content: Полный текст статьи (новое поле)
            metadata: JSON с дополнительной информацией (Telegram каналы и т.д.)
            category: Категория новости (Digest 2.0)
            sentiment_score: Оценка настроения (-10..10)
            why_it_matters: Объяснение важности
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """INSERT INTO news
                           (url, title, summary, full_content, source, published_at, image_url, priority, metadata, 
                            category, sentiment_score, why_it_matters)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (url, title, summary, full_content, source, published_at, image_url, priority, metadata,
                     category, sentiment_score, why_it_matters)
                )
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            # Дубликат - это нормально
            return False
        except Exception as e:
            # Другие ошибки БД (подключение, блокировка и т.д.)
            logger.error(f"❌ Ошибка добавления новости в БД: {e}", exc_info=True)
            return False

    async def get_hot_news(self, min_priority: int = 6) -> Optional[Dict]:
        """
        Ищет самую старую НЕОПУБЛИКОВАННУЮ новость с высоким приоритетом
        
        Args:
            min_priority: Минимальный приоритет для "горячей" новости (по умолчанию 6)
        
        Returns:
            Словарь с новостью или None
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM news WHERE posted_to_telegram = 0 AND priority >= ? ORDER BY priority DESC, id ASC LIMIT 1",
                    (min_priority,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_oldest_unposted_news(self):
        """Обычная очередь (низкий приоритет)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM news WHERE posted_to_telegram = 0 ORDER BY priority DESC, id ASC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def mark_as_posted(self, url: str, message_id: int = None):
        async with aiosqlite.connect(self.db_path) as db:
            if message_id:
                await db.execute("UPDATE news SET posted_to_telegram = 1, telegram_message_id = ? WHERE url = ?", (message_id, url))
            else:
                await db.execute("UPDATE news SET posted_to_telegram = 1 WHERE url = ?", (url,))
            await db.commit()

    async def get_news_for_period(self, hours: int = 24, min_priority: int = 4) -> List[Dict]:
        """
        Получает новости за указанный период (в часах) с фильтром по приоритету.
        Используется для генерации дайджестов.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Вычисляем время отсечки (UTC, так как в БД время обычно в UTC или локальном, надеемся на CURRENT_TIMESTAMP)
            # SQLite modifier: '-24 hours'
            time_modifier = f'-{hours} hours'
            
            async with db.execute(
                f"""
                SELECT title, summary, full_content, source, url, telegram_message_id
                FROM news 
                WHERE added_at >= datetime('now', ?) 
                AND priority >= ?
                ORDER BY priority DESC, id ASC
                """,
                (time_modifier, min_priority)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # === МЕТОДЫ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ===
    
    async def add_user(self, user_id: int, username: str = None, full_name: str = None) -> bool:
        """Регистрирует нового пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
                    (user_id, username, full_name)
                )
                await db.commit()
            logger.info(f"✅ Зарегистрирован новый пользователь: {user_id} (@{username})")
            return True
        except aiosqlite.IntegrityError:
            # Пользователь уже существует
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка добавления пользователя: {e}", exc_info=True)
            return False
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Получает данные пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def set_subscription(self, user_id: int, days: int = 30):
        """Устанавливает Premium подписку на указанное количество дней"""
        from datetime import datetime, timedelta
        
        async with aiosqlite.connect(self.db_path) as db:
            subscription_end = datetime.now() + timedelta(days=days)
            await db.execute(
                """UPDATE users 
                   SET status = 'premium', subscription_end = ?
                   WHERE user_id = ?""",
                (subscription_end.isoformat(), user_id)
            )
            await db.commit()
        logger.info(f"✅ Premium активирован для {user_id} до {subscription_end}")
    
    async def check_subscription(self, user_id: int) -> bool:
        """Проверяет активна ли Premium подписка"""
        from datetime import datetime
        
        user = await self.get_user(user_id)
        if not user:
            return False
        
        if user['status'] != 'premium':
            return False
        
        if not user['subscription_end']:
            return False
        
        # Проверяем не истекла ли подписка
        subscription_end = datetime.fromisoformat(user['subscription_end'])
        if datetime.now() > subscription_end:
            # Подписка истекла - обновляем статус
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET status = 'free' WHERE user_id = ?",
                    (user_id,)
                )
                await db.commit()
            return False
        
        return True
    
    async def set_user_field(self, user_id: int, field: str, value):
        """Обновляет конкретное поле пользователя (БЕЗОПАСНО)"""
        # 🔒 WHITELIST разрешённых полей для защиты от SQL Injection
        ALLOWED_FIELDS = {
            'username', 'full_name', 'status', 'subscription_end',
            'first_offer_shown_at', 'discount_offer_shown_at',
            'total_purchases', 'lifetime_spent'
        }
        
        if field not in ALLOWED_FIELDS:
            logger.error(f"❌ Попытка обновить недопустимое поле: {field}")
            raise ValueError(f"Field '{field}' is not allowed for modification")
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Для datetime конвертируем в ISO формат
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                
                # Безопасно формируем запрос (field проверен через whitelist)
                query = f"UPDATE users SET {field} = ? WHERE user_id = ?"
                await db.execute(query, (value, user_id))
                await db.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления поля {field} для {user_id}: {e}", exc_info=True)
            raise
    
    async def get_user_statistics(self) -> Dict:
        """Возвращает статистику пользователей"""
        stats = {}
        async with aiosqlite.connect(self.db_path) as db:
            # Всего пользователей
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                stats['total_users'] = (await cursor.fetchone())[0]
            
            # Бесплатных
            async with db.execute("SELECT COUNT(*) FROM users WHERE status='free'") as cursor:
                stats['free_users'] = (await cursor.fetchone())[0]
            
            # Premium
            async with db.execute("SELECT COUNT(*) FROM users WHERE status='premium'") as cursor:
                stats['premium_users'] = (await cursor.fetchone())[0]
        
        return stats
    
    # === МЕТОДЫ УПРАВЛЕНИЯ ПЛАТЕЖАМИ И ВОРОНКОЙ ===
    
    async def track_funnel(self, user_id: int, step: str, metadata: dict = None):
        """Отслеживает шаги воронки продаж"""
        import json
        metadata_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO funnel_stats (user_id, step, metadata) VALUES (?, ?, ?)",
                    (user_id, step, metadata_str)
                )
                await db.commit()
            logger.debug(f"📊 Funnel: {user_id} -> {step}")
        except Exception as e:
            logger.error(f"❌ Ошибка отслеживания воронки: {e}", exc_info=True)
    
    async def get_pending_payment(self, user_id: int) -> Optional[Dict]:
        """Проверяет есть ли pending платёж (защита от дублирования)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM payments WHERE user_id=? AND status='pending' LIMIT 1",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки pending платежа: {e}", exc_info=True)
            return None
    
    async def create_payment_record(self, user_id: int, amount: int, discount_used: bool) -> str:
        """Создаёт запись платежа и возвращает UUID (защита от Race Condition)"""
        import uuid
        payment_uuid = str(uuid.uuid4())
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                funnel_step = 'discount_price' if discount_used else 'full_price'
                await db.execute(
                    """INSERT INTO payments 
                       (user_id, amount_stars, discount_used, funnel_step, status, payment_uuid)
                       VALUES (?, ?, ?, ?, 'pending', ?)""",
                    (user_id, amount, discount_used, funnel_step, payment_uuid)
                )
                await db.commit()
            logger.info(f"💳 Payment record created: {payment_uuid} for user {user_id}")
            return payment_uuid
        except Exception as e:
            logger.error(f"❌ Ошибка создания записи платежа: {e}", exc_info=True)
            raise
    
    async def complete_payment(self, payment_uuid: str, charge_id: str, user_id: int, amount: int):
        """Подтверждает успешный платёж по UUID (безопасно от Race Condition)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Обновляем статус платежа по UUID
                await db.execute(
                    """UPDATE payments 
                       SET status='completed', telegram_payment_charge_id=?
                       WHERE payment_uuid=? AND status='pending'""",
                    (charge_id, payment_uuid)
                )
                
                # Обновляем lifetime_spent и total_purchases пользователя
                await db.execute(
                    """UPDATE users 
                       SET total_purchases = total_purchases + 1,
                           lifetime_spent = lifetime_spent + ?
                       WHERE user_id = ?""",
                    (amount, user_id)
                )
                await db.commit()
            logger.info(f"💰 Платёж завершён: UUID={payment_uuid}, {user_id} -> {amount}⭐️")
        except Exception as e:
            logger.error(f"❌ Ошибка завершения платежа {payment_uuid}: {e}", exc_info=True)
            raise
    
    async def get_sales_analytics(self) -> Dict:
        """Возвращает подробную аналитику продаж"""
        async with aiosqlite.connect(self.db_path) as db:
            stats = {}
            
            # Всего показов первичного оффера
            async with db.execute(
                "SELECT COUNT(*) FROM funnel_stats WHERE step='offer_shown'"
            ) as cursor:
                stats['total_offers_shown'] = (await cursor.fetchone())[0]
            
            # Возражений по цене
            async with db.execute(
                "SELECT COUNT(*) FROM funnel_stats WHERE step='price_objection'"
            ) as cursor:
                stats['price_objections'] = (await cursor.fetchone())[0]
            
            # Покупок по полной цене (500⭐️)
            async with db.execute(
                "SELECT COUNT(*) FROM payments WHERE discount_used=0 AND status='completed'"
            ) as cursor:
                stats['full_price_sales'] = (await cursor.fetchone())[0]
            
            # Покупок со скидкой (400⭐️)
            async with db.execute(
                "SELECT COUNT(*) FROM payments WHERE discount_used=1 AND status='completed'"
            ) as cursor:
                stats['discount_sales'] = (await cursor.fetchone())[0]
            
            # Общий доход в звёздах
            async with db.execute(
                "SELECT SUM(amount_stars) FROM payments WHERE status='completed'"
            ) as cursor:
                stats['total_revenue'] = (await cursor.fetchone())[0] or 0
            
            # Средний чек
            total_sales = stats['full_price_sales'] + stats['discount_sales']
            if total_sales > 0:
                stats['average_check'] = round(stats['total_revenue'] / total_sales, 2)
            else:
                stats['average_check'] = 0
            
            # Конверсия воронки
            if stats['total_offers_shown'] > 0:
                stats['conversion_rate'] = round(
                    (total_sales / stats['total_offers_shown']) * 100, 2
                )
            else:
                stats['conversion_rate'] = 0
            
            # Процент использования скидки
            if total_sales > 0:
                stats['discount_usage_rate'] = round(
                    (stats['discount_sales'] / total_sales) * 100, 2
                )
            else:
                stats['discount_usage_rate'] = 0
            
            return stats
    
    async def get_abandoned_funnel_users(self, hours: int = 2) -> List[Dict]:
        """
        Получить пользователей, застрявших в воронке.
        Выбирает только АКТУАЛЬНЫЙ (последний) статус пользователя.
        """
        from datetime import datetime, timedelta
        
        # Время отсечки для первичного напоминания (2 часа назад)
        cutoff_time_first = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        # Время отсечки для ПОВТОРНОГО напоминания (24 часа назад)
        cutoff_time_repeat = (datetime.now() - timedelta(hours=24)).isoformat()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Сложный запрос: берем только ПОСЛЕДНЕЕ событие для каждого юзера
                query = """
                WITH LastUserSteps AS (
                    SELECT 
                        user_id, 
                        step, 
                        happened_at,
                        ROW_NUMBER() OVER(PARTITION BY user_id ORDER BY happened_at DESC) as rn
                    FROM funnel_stats
                )
                SELECT user_id, step as last_step, happened_at
                FROM LastUserSteps
                WHERE rn = 1 
                AND (
                    -- Случай 1: Пользователь увидел оффер > 2 часов назад и молчит
                    (step IN ('offer_shown', 'price_objection') AND happened_at < ?)
                    OR
                    -- Случай 2: Мы уже напоминали, но прошло > 24 часов (можно напомнить еще раз)
                    (step = 'followup_sent' AND happened_at < ?)
                )
                LIMIT 50
                """
                
                async with db.execute(query, (cutoff_time_first, cutoff_time_repeat)) as cursor:
                    results = await cursor.fetchall()
                    return [dict(row) for row in results]
                    
        except Exception as e:
            logger.error(f"Ошибка get_abandoned_funnel_users: {e}")
            return []


    # === МЕТОДЫ РЕФЕРАЛЬНОЙ СИСТЕМЫ ===
    
    async def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        """Добавляет реферальную связь"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                    (referrer_id, referred_id)
                )
                await db.commit()
            logger.info(f"📎 Реферал создан: {referrer_id} -> {referred_id}")
            return True
        except aiosqlite.IntegrityError:
            logger.debug(f"Реферал уже существует: {referrer_id} -> {referred_id}")
            return False
        except Exception as e:
            logger.error(f"Ошибка создания реферала: {e}", exc_info=True)
            return False
    
    async def get_referral_count(self, referrer_id: int) -> int:
        """Возвращает количество рефералов пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM referrals WHERE referrer_id=?",
                    (referrer_id,)
                ) as cursor:
                    return (await cursor.fetchone())[0]
        except Exception as e:
            logger.error(f"Ошибка получения количества рефералов: {e}")
            return 0
    
    async def get_top_referrers(self, limit: int = 10) -> List[Dict]:
        """Получить топ рефереров для админ dashboard"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """SELECT r.referrer_id, u.username, u.full_name, COUNT(*) as referral_count
                       FROM referrals r
                       JOIN users u ON r.referrer_id = u.user_id
                       GROUP BY r.referrer_id
                       ORDER BY referral_count DESC
                       LIMIT ?""",
                    (limit,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения топ рефереров: {e}")
            return []
    
    async def give_referral_bonus(self, referrer_id: int, referred_id: int, bonus_days: int = 12):
        """Даёт бонус реферреру когда реферал покупает Premium (10-15 дней)"""
        from datetime import datetime, timedelta
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Проверяем не был ли уже выдан бонус
                async with db.execute(
                    "SELECT reward_given FROM referrals WHERE referrer_id=? AND referred_id=?",
                    (referrer_id, referred_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row or row[0]:
                        return False  # Бонус уже выдан
                
                # Продлеваем подписку реферреру
                user = await self.get_user(referrer_id)
                if user and user['status'] == 'premium':
                    current_end = datetime.fromisoformat(user['subscription_end'])
                    new_end = current_end + timedelta(days=bonus_days)
                else:
                    # Если не премиум - даём новую подписку
                    new_end = datetime.now() + timedelta(days=bonus_days)
                
                await db.execute(
                    """UPDATE users 
                       SET subscription_end = ?, status = 'premium'
                       WHERE user_id = ?""",
                    (new_end.isoformat(), referrer_id)
                )
                
                # Отмечаем что бонус выдан
                await db.execute(
                    "UPDATE referrals SET reward_given=1 WHERE referrer_id=? AND referred_id=?",
                    (referrer_id, referred_id)
                )
                
                await db.commit()
            
            logger.info(f"🎁 Реферальный бонус выдан: {referrer_id} (+{bonus_days} дней)")
            return True
        except Exception as e:
            logger.error(f"Ошибка выдачи реферального бонуса: {e}", exc_info=True)
            return False
    
    async def get_referral_tree(self, user_id: int, max_depth: int = 3) -> List[Dict]:
        """Построить дерево рефералов с глубиной"""
        referrals = []
        
        async def fetch_level(parent_id: int, depth: int):
            if depth > max_depth:
                return
            
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        """SELECT r.referred_id, u.username, u.full_name, u.status, r.created_at
                           FROM referrals r
                           JOIN users u ON r.referred_id = u.user_id
                           WHERE r.referrer_id = ?""",
                        (parent_id,)
                    ) as cursor:
                        for row in await cursor.fetchall():
                            ref = dict(row)
                            ref['depth'] = depth
                            referrals.append(ref)
                            
                            # Рекурсивно получаем рефералов следующего уровня
                            await fetch_level(ref['referred_id'], depth + 1)
            except Exception as e:
                logger.error(f"Ошибка получения дерева рефералов: {e}")
        
        await fetch_level(user_id, 1)
        return referrals
    
    async def calculate_referral_rewards(self, new_user_id: int):
        """Начислить XP всем в цепочке вверх при регистрации реферала"""
        try:
            # Получаем того, кто пригласил
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT referrer_id FROM referrals WHERE referred_id = ?",
                    (new_user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return
                    
                    referrer_id = row[0]
            
            # Level 1: прямой реферал → +50 XP
            await self.log_activity(
                referrer_id,
                'referral',
                xp_amount=50,
                metadata={'referred_user': new_user_id, 'depth': 1}
            )
            
            # Ищем цепочку выше (Level 2 и 3)
            current_id = referrer_id
            for depth in [2, 3]:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute(
                        "SELECT referrer_id FROM referrals WHERE referred_id = ?",
                        (current_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if not row:
                            break
                        
                        parent_id = row[0]
                
                # Level 2 → +25 XP, Level 3 → +10 XP
                xp_amounts = {2: 25, 3: 10}
                await self.log_activity(
                    parent_id,
                    'referral',
                    xp_amount=xp_amounts[depth],
                    metadata={'referred_user': new_user_id, 'depth': depth}
                )
                
                current_id = parent_id
            
            logger.info(f"🌳 MLM rewards calculated for referral chain of user {new_user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка расчёта MLM наград: {e}", exc_info=True)
    
    async def check_premium_bonus_eligibility(self, user_id: int) -> Dict:
        """Проверяет право на Premium бонус за 10 активных рефералов"""
        try:
            # Получаем всех Level 1 рефералов
            tree = await self.get_referral_tree(user_id, max_depth=1)
            level1_refs = [r for r in tree if r['depth'] == 1]
            
            # Считаем активных (купили Premium)
            active_count = sum(1 for r in level1_refs if r['status'] == 'premium')
            
            # Проверяем не был ли уже выдан бонус
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM user_activities WHERE user_id=? AND activity_type='referral_bonus_premium'",
                    (user_id,)
                ) as cursor:
                    bonus_given = (await cursor.fetchone())[0] > 0
            
            eligible = active_count >= 10 and not bonus_given
            
            return {
                'eligible': eligible,
                'total_referrals': len(level1_refs),
                'active_referrals': active_count,
                'bonus_given': bonus_given,
                'needed': max(0, 10 - active_count)
            }
        except Exception as e:
            logger.error(f"Ошибка проверки права на Premium бонус: {e}", exc_info=True)
            return {'eligible': False}
    
    async def grant_referral_premium_bonus(self, user_id: int, bonus_days: int = 12):
        """Выдать Premium на 10-15 дней за 10 активных рефералов"""
        from datetime import datetime, timedelta
        
        try:
            # Проверяем право
            eligibility = await self.check_premium_bonus_eligibility(user_id)
            if not eligibility['eligible']:
                return False
            
            # Выдаём Premium
            user = await self.get_user(user_id)
            if user and user['status'] == 'premium' and user['subscription_end']:
                current_end = datetime.fromisoformat(user['subscription_end'])
                new_end = current_end + timedelta(days=bonus_days)
            else:
                new_end = datetime.now() + timedelta(days=bonus_days)
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET subscription_end=?, status='premium' WHERE user_id=?",
                    (new_end.isoformat(), user_id)
                )
                await db.commit()
            
            # Логируем бонус
            await self.log_activity(
                user_id,
                'referral_bonus_premium',
                xp_amount=500,  # Большой бонус за достижение
                metadata={'bonus_days': bonus_days}
            )
            
            logger.info(f"🎁💎 Premium бонус за рефералов выдан: {user_id} (+{bonus_days} дней)")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка выдачи Premium бонуса: {e}", exc_info=True)
            return False
    
    async def get_referrer(self, user_id: int) -> Optional[Dict]:
        """Получить того, кто пригласил пользователя (Level 1)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT referrer_id FROM referrals WHERE referred_id = ?",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return {'referrer_id': row[0]} if row else None
        except Exception as e:
            logger.error(f"Ошибка получения реферрера: {e}", exc_info=True)
            return None
    
    async def count_user_story_checks(self, user_id: int, date: str = None) -> int:
        """Подсчитать количество проверок Stories за день"""
        from datetime import datetime
        
        if not date:
            date = datetime.now().date().isoformat()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """SELECT COUNT(*) FROM user_activities 
                       WHERE user_id = ? 
                       AND activity_type = 'story_check'
                       AND DATE(created_at) = ?""",
                    (user_id, date)
                ) as cursor:
                    return (await cursor.fetchone())[0]
        except Exception as e:
            logger.error(f"Ошибка подсчёта Stories проверок: {e}", exc_info=True)
            return 0
    
    async def get_user_story_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить историю проверок Stories пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """SELECT created_at, xp_earned, metadata, 
                              verification_status, ai_confidence
                       FROM user_activities
                       WHERE user_id = ? AND activity_type = 'story_check'
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (user_id, limit)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения истории Stories: {e}")
            return []
    
    async def get_pending_story_reviews(self, limit: int = 20) -> List[Dict]:
        """Получить список Stories на модерации"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT ua.id, ua.user_id, ua.created_at, ua.ai_confidence,
                           ua.local_file_path, ua.metadata,
                           u.username, u.full_name
                    FROM user_activities ua
                    LEFT JOIN users u ON ua.user_id = u.user_id
                    WHERE ua.activity_type = 'story_check' 
                    AND ua.verification_status = 'pending_review'
                    ORDER BY ua.created_at ASC
                    LIMIT ?
                """, (limit,)) as cursor:
                    return [dict(row) for row in await cursor.fetchall()]
        except Exception as e:
            logger.error(f"Ошибка получения очереди модерации: {e}")
            return []
    
    async def approve_story_check(self, activity_id: int, admin_id: int) -> bool:
        """Одобрить проверку Stories"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем user_id для начисления XP
                async with db.execute(
                    "SELECT user_id FROM user_activities WHERE id = ?", 
                    (activity_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return False
                    user_id = row[0]
                
                # Обновляем статус
                await db.execute("""
                    UPDATE user_activities 
                    SET verification_status = 'manual_approved',
                        xp_earned = 100,
                        reviewed_by = ?,
                        reviewed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (admin_id, activity_id))
                await db.commit()
                
                # Начисляем XP
                await self.add_xp(user_id, 100, 'story_manual_approval')
                return True
        except Exception as e:
            logger.error(f"Ошибка одобрения Stories: {e}")
            return False
    
    async def reject_story_check(self, activity_id: int, admin_id: int, reason: str = None) -> bool:
        """Отклонить проверку Stories"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                import json
                metadata_update = json.dumps({"rejection_reason": reason}) if reason else '{}'
                await db.execute("""
                    UPDATE user_activities 
                    SET verification_status = 'manual_rejected',
                        reviewed_by = ?,
                        reviewed_at = CURRENT_TIMESTAMP,
                        metadata = ?
                    WHERE id = ?
                """, (admin_id, metadata_update, activity_id))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка отклонения Stories: {e}")
            return False
    
    async def check_story_ban(self, user_id: int) -> bool:
        """Проверить, забанен ли пользователь для Stories"""
        try:
            from datetime import datetime
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT story_ban_until FROM users WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row or not row[0]:
                        return False
                    
                    ban_until = datetime.fromisoformat(row[0])
                    return datetime.now() < ban_until
        except Exception as e:
            logger.error(f"Ошибка проверки бана: {e}")
            return False
    
    async def set_story_ban(self, user_id: int, hours: int = 24) -> bool:
        """Установить временный бан для Stories"""
        try:
            from datetime import datetime, timedelta
            ban_until = datetime.now() + timedelta(hours=hours)
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET story_ban_until = ? WHERE user_id = ?",
                    (ban_until.isoformat(), user_id)
                )
                await db.commit()
                logger.info(f"⚠️ Пользователь {user_id} забанен до {ban_until}")
                return True
        except Exception as e:
            logger.error(f"Ошибка установки бана: {e}")
            return False
    
    async def check_abuse_pattern(self, user_id: int) -> bool:
        """Проверить паттерн злоупотреблений (3+ отклонения подряд)"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT verification_status
                    FROM user_activities
                    WHERE user_id = ? AND activity_type = 'story_check'
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (user_id,)) as cursor:
                    rows = await cursor.fetchall()
                    
                    if len(rows) < 3:
                        return False
                    
                    # Проверяем последние 3 проверки
                    recent_statuses = [row['verification_status'] for row in rows[:3]]
                    rejected_count = sum(
                        1 for status in recent_statuses 
                        if status in ['auto_rejected', 'manual_rejected']
                    )
                    
                    return rejected_count >= 3
        except Exception as e:
            logger.error(f"Ошибка проверки абьюза: {e}")
            return False
    
    async def get_story_statistics(self) -> Dict:
        """Получить статистику по Stories для админов"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Общая статистика
                async with db.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN verification_status = 'auto_approved' THEN 1 ELSE 0 END) as auto_approved,
                        SUM(CASE WHEN verification_status = 'auto_rejected' THEN 1 ELSE 0 END) as auto_rejected,
                        SUM(CASE WHEN verification_status = 'pending_review' THEN 1 ELSE 0 END) as pending,
                        SUM(CASE WHEN verification_status = 'manual_approved' THEN 1 ELSE 0 END) as manual_approved,
                        SUM(CASE WHEN verification_status = 'manual_rejected' THEN 1 ELSE 0 END) as manual_rejected,
                        AVG(ai_confidence) as avg_confidence
                    FROM user_activities
                    WHERE activity_type = 'story_check'
                """) as cursor:
                    row = await cursor.fetchone()
                    stats = dict(row) if row else {}
                
                # Статистика по AI провайдерам
                async with db.execute("""
                    SELECT metadata
                    FROM user_activities
                    WHERE activity_type = 'story_check' AND metadata IS NOT NULL
                """) as cursor:
                    rows = await cursor.fetchall()
                    
                    import json
                    provider_counts = {}
                    for row in rows:
                        try:
                            metadata = json.loads(row['metadata'])
                            provider = metadata.get('ai_provider', 'unknown')
                            provider_counts[provider] = provider_counts.get(provider, 0) + 1
                        except:
                            pass
                    
                    stats['provider_counts'] = provider_counts
                
                return stats
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}
    
    async def create_badges_table(self):
        """Создать таблицу бейджей достижений"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS user_badges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        badge_type TEXT NOT NULL,
                        earned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        UNIQUE(user_id, badge_type)
                    )
                """)
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка создания таблицы бейджей: {e}")
    
    async def award_badge(self, user_id: int, badge_type: str) -> bool:
        """Выдать бейдж пользователю"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO user_badges (user_id, badge_type) VALUES (?, ?)",
                    (user_id, badge_type)
                )
                await db.commit()
                logger.info(f"🏅 Бейдж выдан: {user_id} - {badge_type}")
                return True
        except Exception as e:
            logger.error(f"Ошибка выдачи бейджа: {e}")
            return False
    
    async def get_user_badges(self, user_id: int) -> List[str]:
        """Получить список бейджей пользователя"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT badge_type FROM user_badges WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения бейджей: {e}")
            return []
    
    async def check_and_award_badges(self, user_id: int):
        """Проверить условия и выдать бейджи автоматически"""
        user = await self.get_user(user_id)
        if not user:
            return
        
        # Level badges
        level = user.get('level', 1)
        if level >= 5:
            await self.award_badge(user_id, 'level_5')
        if level >= 10:
            await self.award_badge(user_id, 'level_10_champion')
        
        # Referral badges
        ref_count = await self.get_referral_count(user_id)
        if ref_count >= 10:
            await self.award_badge(user_id, 'referrer_10')
        if ref_count >= 50:
            await self.award_badge(user_id, 'referrer_50')
        
        # Premium badge
        if user.get('status') == 'premium':
            await self.award_badge(user_id, 'premium_member')
        
        # Story checker badge
        # Use the existing method instead of raw db.execute
        total_story_count = 0
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM user_activities WHERE user_id=? AND activity_type='story_check'",
                    (user_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    total_story_count = result[0] if result else 0
        except Exception as e:
            logger.error(f"Error counting stories for badges: {e}")
        
        if total_story_count >= 10:
            await self.award_badge(user_id, 'story_hunter')



    # === МЕТОДЫ ГЕЙМИФИКАЦИИ ===
    
    # Константы уровней
    LEVEL_THRESHOLDS = {
        1: 0,
        2: 100,
        3: 300,
        4: 600,
        5: 1000,
        6: 1500,
        7: 2200,
        8: 3000,
        9: 4000,
        10: 5000
    }
    
    # XP за активности
    XP_REWARDS = {
        'read_post': 5,
        'referral': 50,
        'referral_purchase': 200,
        'story_check': 100,
        'share_20': 150,
        'purchase': 100
    }
    
    async def add_xp(self, user_id: int, amount: int, activity: str, metadata: dict = None) -> Dict:
        """Добавляет XP пользователю и проверяет повышение уровня"""
        import json
        from datetime import datetime
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем текущий XP и уровень
                async with db.execute(
                    "SELECT xp, level FROM users WHERE user_id = ?",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        logger.warning(f"User {user_id} not found for XP")
                        return {'level_up': False}
                    
                    current_xp, current_level = row
                    new_xp = current_xp + amount
                
                # Проверяем повышение уровня
                new_level = current_level
                for level, threshold in sorted(self.LEVEL_THRESHOLDS.items()):
                    if new_xp >= threshold:
                        new_level = level
                
                level_up = new_level > current_level
                
                # Обновляем XP и уровень
                await db.execute(
                    """UPDATE users 
                       SET xp = ?, level = ?, last_activity = ?
                       WHERE user_id = ?""",
                    (new_xp, new_level, datetime.now().isoformat(), user_id)
                )
                
                # Логируем активность
                metadata_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
                await db.execute(
                    """INSERT INTO user_activities 
                       (user_id, activity_type, xp_earned, metadata)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, activity, amount, metadata_str)
                )
                
                await db.commit()
            
            result = {
                'xp_earned': amount,
                'new_xp': new_xp,
                'new_level': new_level,
                'level_up': level_up
            }
            
            if level_up:
                logger.info(f"🎉 Level UP! User {user_id}: {current_level} → {new_level}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка добавления XP: {e}", exc_info=True)
            return {'level_up': False}
    
    async def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Возвращает топ пользователей по XP"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """SELECT user_id, username, full_name, xp, level
                       FROM users
                       WHERE xp > 0
                       ORDER BY xp DESC
                       LIMIT ?""",
                    (limit,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения лидерборда: {e}", exc_info=True)
            return []
    
    async def get_user_rank(self, user_id: int) -> Optional[int]:
        """Возвращает позицию пользователя в рейтинге"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    """SELECT COUNT(*) + 1 as rank
                       FROM users
                       WHERE xp > (SELECT xp FROM users WHERE user_id = ?)""",
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error(f"Ошибка получения ранга: {e}", exc_info=True)
            return None
    
    async def log_activity(self, user_id: int, activity_type: str, xp_amount: int = None, metadata: dict = None):
        """Логирует активность и автоматически начисляет XP"""
        if xp_amount is None:
            xp_amount = self.XP_REWARDS.get(activity_type, 0)
        
        if xp_amount > 0:
            return await self.add_xp(user_id, xp_amount, activity_type, metadata)
        
        return {'level_up': False}

    async def save_payment(self, user_id: int, amount_stars: int, amount_usd: int,
                          payment_type: str, telegram_payment_id: str, status: str = 'completed'):
        """Сохранить платёж в БД"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO payments 
                (user_id, amount, amount_usd, payment_type, telegram_payment_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount_stars, amount_usd, payment_type, telegram_payment_id, status, 
                 datetime.now().isoformat())
            )
            payment_id = cursor.lastrowid
            await conn.commit()
            return payment_id
    
    async def create_consultation(self, user_id: int, consultation_type: str,
                                  amount_paid: int, amount_usd: int, payment_id: int = None):
        """Создать консультацию после оплаты"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO consultations
                (user_id, type, amount_paid, amount_usd, payment_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'paid', ?)
                """,
                (user_id, consultation_type, amount_paid, amount_usd, payment_id,
                 datetime.now().isoformat())
            )
            consultation_id = cursor.lastrowid
            await conn.commit()
            return consultation_id
    
    async def update_consultation_datetime(self, consultation_id: int, scheduled_datetime: str):
        """Обновить дату/время консультации"""
        async with self.get_connection() as conn:
            await conn.execute(
                """
                UPDATE consultations
                SET scheduled_datetime = ?, status = 'scheduled'
                WHERE id = ?
                """,
                (scheduled_datetime, consultation_id)
            )
            await conn.commit()
    
    async def get_consultation(self, consultation_id: int):
        """Получить консультацию по ID"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM consultations WHERE id = ?",
                (consultation_id,)
            )
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
        return None
    
    async def create_reminder(self, consultation_id: int, reminder_type: str, scheduled_time: str):
        """Создать напоминание о консультации"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO consultation_reminders
                (consultation_id, reminder_type, scheduled_time, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (consultation_id, reminder_type, scheduled_time, datetime.now().isoformat())
            )
            await conn.commit()
            return cursor.lastrowid
    
    async def mark_reminder_sent(self, reminder_id: int):
        """Отметить напоминание как отправленное"""
        async with self.get_connection() as conn:
            await conn.execute(
                "UPDATE consultation_reminders SET sent = 1 WHERE id = ?",
                (reminder_id,)
            )
            await conn.commit()

# Экспортируем экземпляр
db = NewsDatabase()

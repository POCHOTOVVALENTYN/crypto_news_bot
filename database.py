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


    async def init(self):
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
                                 telegram_message_id INTEGER DEFAULT NULL
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
                        
            except Exception as e:
                # Игнорируем ошибки миграции
                logger.debug(f"⚠️ Миграция: {e}")
            
            # Добавляем индекс для быстрого поиска по приоритету
            await db.execute("""
                             CREATE INDEX IF NOT EXISTS idx_priority_posted 
                             ON news(priority DESC, posted_to_telegram, id ASC)
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
                                 
                                 FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                                 FOREIGN KEY (referred_id) REFERENCES users(user_id),
                                 UNIQUE(referrer_id, referred_id)
                             )
                             """)
            
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

    async def add_news(self, url: str, title: str, summary: str, source: str,
                       published_at: str, image_url: str = None, priority: int = 0,
                       full_content: str = None) -> bool:
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
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """INSERT INTO news
                           (url, title, summary, full_content, source, published_at, image_url, priority)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (url, title, summary, full_content, source, published_at, image_url, priority)
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
    
    async def give_referral_bonus(self, referrer_id: int, referred_id: int, bonus_days: int = 7):
        """Даёт бонус реферреру когда реферал покупает Premium"""
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



db = NewsDatabase()
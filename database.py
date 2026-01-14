# database.py
import aiosqlite
import logging
from typing import Optional, Dict
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
                                 priority           INTEGER DEFAULT 0
                             )
                             """)
            
            # ✅ МИГРАЦИЯ: Добавляем колонку full_content если её нет
            try:
                # Проверяем существование колонки
                async with db.execute("PRAGMA table_info(news)") as cursor:
                    columns = [row[1] for row in await cursor.fetchall()]
                    if 'full_content' not in columns:
                        await db.execute("ALTER TABLE news ADD COLUMN full_content TEXT")
                        await db.commit()
                        logger.info("✅ Добавлена колонка full_content в таблицу news")
            except Exception as e:
                # Игнорируем ошибки миграции
                logger.debug(f"⚠️ Миграция full_content: {e}")
            
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

    async def mark_as_posted(self, url: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE news SET posted_to_telegram = 1 WHERE url = ?", (url,))
            await db.commit()


db = NewsDatabase()
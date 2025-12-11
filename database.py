# database.py
import aiosqlite
import logging
from thefuzz import fuzz

DB_PATH = "crypto_news.db"
logger = logging.getLogger(__name__)


class NewsDatabase:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Добавили колонку priority (0 - обычно, 1 - молния)
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS news
                             (
                                 id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                                 url                TEXT UNIQUE NOT NULL,
                                 title              TEXT        NOT NULL,
                                 summary            TEXT,
                                 image_url          TEXT,
                                 source             TEXT        NOT NULL,
                                 published_at       TEXT        NOT NULL,
                                 added_at           TEXT    DEFAULT CURRENT_TIMESTAMP,
                                 posted_to_telegram BOOLEAN DEFAULT 0,
                                 priority           INTEGER DEFAULT 0
                             )
                             """)
            await db.commit()

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
                       published_at: str, image_url: str = None, priority: int = 0) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """INSERT INTO news
                           (url, title, summary, source, published_at, image_url, priority)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (url, title, summary, source, published_at, image_url, priority)
                )
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def get_hot_news(self):
        """Ищет самую старую НЕОПУБЛИКОВАННУЮ новость с ВЫСОКИМ приоритетом"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                    "SELECT * FROM news WHERE posted_to_telegram = 0 AND priority = 1 ORDER BY id ASC LIMIT 1"
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
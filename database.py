# database.py
import aiosqlite
import logging

DB_PATH = "crypto_news.db"

class NewsDatabase:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS news
                             (
                                 id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                                 url                TEXT UNIQUE NOT NULL,
                                 title              TEXT        NOT NULL,
                                 summary            TEXT, -- Добавили
                                 image_url          TEXT, -- Добавили
                                 source             TEXT        NOT NULL,
                                 published_at       TEXT        NOT NULL,
                                 added_at           TEXT    DEFAULT CURRENT_TIMESTAMP,
                                 posted_to_telegram BOOLEAN DEFAULT 0
                             )
                             """)
            await db.commit()

    async def news_exists(self, url: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM news WHERE url = ?", (url,)) as cursor:
                result = await cursor.fetchone()
                return result is not None

    async def add_news(self, url: str, title: str, source: str, published_at: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO news (url, title, source, published_at) VALUES (?, ?, ?, ?)",
                    (url, title, source, published_at)
                )
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def get_oldest_unposted_news(self):
        """Получает одну самую старую неотправленную новость"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row  # Чтобы обращаться по именам полей
            async with db.execute(
                "SELECT * FROM news WHERE posted_to_telegram = 0 ORDER BY id ASC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row) # Конвертируем в словарь
                return None

    async def mark_as_posted(self, url: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE news SET posted_to_telegram = 1 WHERE url = ?", (url,))
            await db.commit()

db = NewsDatabase()
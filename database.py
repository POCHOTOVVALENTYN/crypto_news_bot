# database.py
import aiosqlite
import os
from datetime import datetime
from typing import Optional

DB_PATH = "crypto_news.db"


class NewsDatabase:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        """Инициализируйте БД и создайте таблицы"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                             CREATE TABLE IF NOT EXISTS news
                             (
                                 id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                                 url                TEXT UNIQUE NOT NULL,
                                 title              TEXT        NOT NULL,
                                 source             TEXT        NOT NULL,
                                 published_at       TEXT        NOT NULL,
                                 added_at           TEXT    DEFAULT CURRENT_TIMESTAMP,
                                 posted_to_telegram BOOLEAN DEFAULT 0
                             )
                             """)
            await db.commit()

    async def news_exists(self, url: str) -> bool:
        """Проверьте, существует ли новость в БД"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM news WHERE url = ?",
                (url,)
            )
            result = await cursor.fetchone()
            return result is not None

    async def add_news(self, url: str, title: str, source: str,
                       published_at: str) -> bool:
        """Добавьте новость в БД"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO news (url, title, source, published_at) VALUES (?, ?, ?, ?)",
                    (url, title, source, published_at)
                )
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            # URL уже существует
            return False

    async def mark_as_posted(self, url: str):
        """Отметьте новость как отправленную в Telegram"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE news SET posted_to_telegram = 1 WHERE url = ?",
                (url,)
            )
            await db.commit()

    async def get_unposted_count(self) -> int:
        """Получите количество неотправленных новостей"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM news WHERE posted_to_telegram = 0"
            )
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def is_posted(self, url: str) -> bool:
        """Проверьте, была ли новость уже отправлена в Telegram"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT posted_to_telegram FROM news WHERE url = ?",
                (url,)
            )
            result = await cursor.fetchone()
            # Если новости нет или флаг 0 -> False. Если флаг 1 -> True
            return result is not None and result[0] == 1


# Создайте глобальный экземпляр
db = NewsDatabase()
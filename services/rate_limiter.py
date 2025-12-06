# services/rate_limiter.py
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Система для ограничения частоты публикаций (анти-спам)

    Правило: максимум 1 публикация в течение X секунд
    """

    def __init__(self, min_interval_seconds: int = 300):
        """
        min_interval_seconds: минимальный интервал между постами (по умолчанию 5 минут)
        """
        self.min_interval = timedelta(seconds=min_interval_seconds)
        self.last_post_time: Optional[datetime] = None
        self.posts_queue = []

    def can_post(self) -> bool:
        """Проверьте, можно ли публиковать сейчас"""
        if self.last_post_time is None:
            return True

        time_since_last = datetime.now() - self.last_post_time

        if time_since_last >= self.min_interval:
            return True

        return False

    def get_wait_time(self) -> int:
        """Получите время ожидания до следующей публикации (в секундах)"""
        if self.can_post():
            return 0

        time_since_last = datetime.now() - self.last_post_time
        wait_seconds = (self.min_interval - time_since_last).total_seconds()

        return max(0, int(wait_seconds))

    def mark_posted(self):
        """Отметьте что пост был опубликован"""
        self.last_post_time = datetime.now()
        logger.info(f"⏱️ Следующий пост возможен через {self.min_interval.total_seconds():.0f}с")

    async def wait_if_needed(self):
        """Подождите если нужно перед публикацией"""
        wait_time = self.get_wait_time()

        if wait_time > 0:
            logger.info(f"⏳ Ожидание {wait_time}с перед следующим постом...")
            await asyncio.sleep(wait_time)


class MessageFormatter:
    """Форматирование сообщений для профессионального вида"""

    @staticmethod
    def format_crypto_news(
            title: str,
            summary: str,
            source: str,
            btc_price_str: str = "",
            gif_url: str = "",
            language: str = "en"
    ) -> str:
        """
        Форматируйте новость с профессиональным стилем

        Структура:
        🔔 [GIF если есть]
        **ЗАГОЛОВОК**

        Описание...

        💰 BTC цена
        📰 Источник
        """

        # Определите эмодзи по языку
        if language == "ru":
            news_emoji = "📰"
            source_label = "Источник"
        else:
            news_emoji = "📰"
            source_label = "Source"

        # Укоротите заголовок если нужно
        title_display = title[:80] if len(title) > 80 else title

        # Создайте сообщение БЕЗ ссылки (как вы просили)
        message = f"""🔔 *{title_display}*

{summary}
"""

        # Добавьте GIF если есть
        if gif_url:
            message += f"\n[GIF вставляется отдельно через API]\n"

        # Добавьте цену BTC
        if btc_price_str:
            message += f"{btc_price_str}\n"

        # Добавьте источник
        message += f"\n{news_emoji} *{source_label}:* {source}"

        return message

    @staticmethod
    def get_thematic_gif(keywords: str) -> str:
        """
        Получите URL GIF на основе ключевых слов

        Используется Giphy API (бесплатный)
        https://giphy.com/docs/api
        """
        gifs = {
            "pump": "https://media.giphy.com/media/l0HlDy9x8FZo0XO1i/giphy.gif",  # Бычий рынок
            "dump": "https://media.giphy.com/media/xTiTnIilwuFFFpf2Cc/giphy.gif",  # Медвежий рынок
            "crash": "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",  # Падение
            "moon": "https://media.giphy.com/media/l0HlQaQ6gWfllcjDo/giphy.gif",  # Луна (рост)
            "default": "https://media.giphy.com/media/l0IypeKl9NJhMDatlV/giphy.gif",  # Крипто монета
        }

        keywords_lower = keywords.lower()

        for key, gif_url in gifs.items():
            if key in keywords_lower:
                return gif_url

        return gifs["default"]
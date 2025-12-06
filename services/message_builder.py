"""
Продвинутый форматировщик сообщений для Telegram с поддержкой:
- Встроенных GIF через inline keyboard
- Стилизованных ссылок в тексте
- Большого количества эмодзи
- Изображений из новостей
"""

import logging
from typing import Optional, Dict, List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from html import escape

logger = logging.getLogger(__name__)


class TelegramGIFLibrary:
    """
    Библиотека встроенных GIF от Telegram
    Используется через inline keyboard с callback данными

    Технически это работает через:
    1. Inline кнопку с наименованием GIF
    2. Или отправку через @gif bot ID
    3. Или через стикеры
    """

    # Встроенные GIF ID из Telegram GIF library
    GIFS = {
        # Бычий рынок / Позитив
        "bullish": {
            "query": "bull market",  # Поисковый запрос в Telegram GIF
            "emoji": "📈",
            "keywords": ["pump", "rally", "surge", "spike", "прорыв", "рост", "взлет"]
        },

        # Медвежий рынок / Негатив
        "bearish": {
            "query": "bear market",
            "emoji": "📉",
            "keywords": ["dump", "crash", "fall", "decline", "падение", "крах", "обвал"]
        },

        # Нейтральный / Стабильно
        "neutral": {
            "query": "bitcoin",
            "emoji": "⚪",
            "keywords": ["stable", "consolidation", "sideways", "консолидация"]
        },

        # Луна / Экспоненциальный рост
        "moon": {
            "query": "moon rocket",
            "emoji": "🚀",
            "keywords": ["moon", "moon", "to the moon", "луна", "взлет"]
        },

        # Крах
        "crash": {
            "query": "crash burn",
            "emoji": "🔥",
            "keywords": ["crash", "liquidation", "rekt", "крах", "ликвидация"]
        },

        # Аналитика / Исследование
        "analysis": {
            "query": "data analysis charts",
            "emoji": "📊",
            "keywords": ["analysis", "report", "data", "analytics", "анализ"]
        },

        # Волатильность / Паника
        "panic": {
            "query": "panic sell",
            "emoji": "😱",
            "keywords": ["panic", "volatility", "crazy", "паника", "волатил"]
        },
    }

    @staticmethod
    def get_gif_query(keywords: str) -> str:
        """
        Получите GIF запрос на основе ключевых слов

        Для использования:
        await bot.send_animation(
            chat_id=CHANNEL_ID,
            animation=f"https://media.tenor.com/search/{gif_query}/",
            caption="💡"
        )
        """
        keywords_lower = keywords.lower()

        for gif_type, gif_data in TelegramGIFLibrary.GIFS.items():
            for keyword in gif_data["keywords"]:
                if keyword in keywords_lower:
                    return gif_data["query"]

        return TelegramGIFLibrary.GIFS["neutral"]["query"]

    @staticmethod
    def create_gif_keyboard() -> Optional[InlineKeyboardMarkup]:
        """
        Создайте inline keyboard с кнопками GIF

        ВАЖНО: Это теоретическое решение. В реальности Telegram не поддерживает
        встроенные GIF через callback. Вместо этого используйте:
        1. send_animation() - отправить GIF отдельным сообщением
        2. @gif bot - встроенный бот для поиска GIF
        3. URL на Giphy или Tenor
        """
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📈 Бычий",
                        callback_data="gif_bullish"
                    ),
                    InlineKeyboardButton(
                        text="📉 Медвежий",
                        callback_data="gif_bearish"
                    ),
                ]
            ]
        )
        return keyboard


class ImageExtractor:
    """Извлечение изображений из RSS новостей"""

    @staticmethod
    def extract_image_from_entry(entry: Dict) -> Optional[str]:
        """
        Извлеките URL изображения из RSS entry

        Проверяет следующие источники:
        1. entry.media_content
        2. entry.links (image)
        3. og:image meta tag
        4. entry.summary (img src)
        """

        # 1. Проверьте media_content (стандартный RSS)
        if hasattr(entry, 'media_content') and entry.media_content:
            try:
                return entry.media_content[0].get('url')
            except:
                pass

        # 2. Проверьте links
        if hasattr(entry, 'links') and entry.links:
            for link in entry.links:
                if link.get('type', '').startswith('image'):
                    return link.get('href')

        # 3. Извлеките из summary HTML (регулярное выражение)
        if hasattr(entry, 'summary') and entry.summary:
            import re
            img_urls = re.findall(
                r'<img[^>]+src=["\']([^"\']+)["\']',
                entry.summary
            )
            if img_urls:
                return img_urls[0]

        # 4. Проверьте image поле
        if hasattr(entry, 'image') and entry.image:
            return entry.image.get('href') or entry.image.get('url')

        return None

    @staticmethod
    def is_valid_image_url(url: Optional[str]) -> bool:
        """Проверьте валидность URL изображения"""
        if not url:
            return False

        # Проверьте расширение файла
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        url_lower = url.lower()

        # Базовая проверка
        if any(ext in url_lower for ext in valid_extensions):
            return True

        # Проверьте наличие размеров (признак валидного изображения)
        if 'image' in url_lower or 'img' in url_lower:
            return True

        return False


class AdvancedMessageFormatter:
    """
    Продвинутое форматирование сообщений для Telegram

    Особенности:
    - Стилизованные ссылки прямо в тексте
    - Большое количество эмодзи для выразительности
    - Встроенные GIF
    - Изображения из новостей
    - Markdown форматирование (bold, italic, code, links)
    """

    # Расширенная эмодзи палитра
    EMOJIS = {
        # Статус
        "status_bullish": "📈🔥",
        "status_bearish": "📉❄️",
        "status_neutral": "⚪",
        "status_moon": "🚀🌙",

        # Действия
        "action_buy": "🛒💰",
        "action_sell": "📤🚫",
        "action_hold": "🙌",
        "action_alert": "🚨⚠️",

        # Рынок
        "market_up": "⬆️💹",
        "market_down": "⬇️💔",
        "market_high": "🏔️",
        "market_low": "🐁",

        # Крипто
        "btc": "₿",
        "eth": "Ξ",
        "volume": "📊💧",
        "price": "💵💰",

        # События
        "event_regulation": "⚖️📋",
        "event_hack": "🔓💣",
        "event_fork": "🍴⛓️",
        "event_listing": "📢🎉",

        # Разное
        "source": "📰🔗",
        "time": "⏰🕐",
        "analysis": "🔬📊",
        "community": "👥💬",
    }

    @staticmethod
    def create_markdown_link(text: str, url: str) -> str:
        """
        Создайте Markdown ссылку для Telegram

        Формат: [читай здесь](https://example.com)
        """
        return f"[{escape(text)}]({escape(url)})"

    @staticmethod
    def format_professional_news(
            title: str,
            summary: str,
            source: str,
            source_url: str,
            btc_price: Optional[str] = None,
            sentiment: str = "neutral",
            image_url: Optional[str] = None,
            language: str = "en"
    ) -> Dict:
        """
        Форматируйте новость профессионально с максимумом деталей

        Возвращает словарь:
        {
            "text": основной текст сообщения,
            "image_url": URL изображения если есть,
            "gif_query": поисковый запрос для GIF,
            "keyboard": inline keyboard (если нужна)
        }
        """

        # Определите эмодзи по настроению
        sentiment_emoji_map = {
            "bullish": "📈🟢",
            "bearish": "📉🔴",
            "neutral": "⚪",
            "moon": "🚀🌙",
        }
        sentiment_emoji = sentiment_emoji_map.get(sentiment, "⚪")

        # Определите стартовый эмодзи
        start_emoji = "🔔📰" if language == "ru" else "📰🔔"

        # Укоротите заголовок если нужно
        title_display = title[:100] if len(title) > 100 else title

        # Создайте основной текст с ссылкой в тексте
        message = f"""{start_emoji} *{title_display}*

{summary}

{sentiment_emoji} *Настроение:* {sentiment.capitalize()}

"""

        # Добавьте BTC цену если есть
        if btc_price:
            message += f"{btc_price}\n\n"

        # Добавьте источник со ССЫЛКОЙ в текст (как вы просили)
        source_link = AdvancedMessageFormatter.create_markdown_link(
            f"📰 читай здесь",
            source_url
        )
        message += f"*Источник:* {source} • {source_link}\n"

        # Добавьте дополнительные элементы
        message += f"👥 *Криптосообщество* 💬"

        # Получите GIF запрос
        gif_query = TelegramGIFLibrary.get_gif_query(title + " " + summary)

        return {
            "text": message,
            "image_url": image_url if ImageExtractor.is_valid_image_url(image_url) else None,
            "gif_query": gif_query,
            "keyboard": None,  # Пока не используется
        }

    @staticmethod
    def create_detailed_message(
            title: str,
            summary: str,
            source: str,
            source_url: str,
            image_url: Optional[str] = None,
            btc_price: Optional[str] = None
    ) -> str:
        """
        Создайте детальное сообщение с максимумом эмодзи и информации

        Включает:
        - Заголовок с эмодзи
        - Описание с форматированием
        - Изображение (если есть)
        - BTC цена
        - Ссылка на источник прямо в тексте
        - Множество эмодзи для выразительности
        """

        message = f"""
🔴 🟠 🟡 🟢 🔵 🟣
━━━━━━━━━━━━━━━━━━
📰 *{title[:80]}*
━━━━━━━━━━━━━━━━━━

{summary}

"""

        # Добавьте цену BTC
        if btc_price:
            message += f"{btc_price}\n"

        # Добавьте источник со ССЫЛКОЙ
        source_link = AdvancedMessageFormatter.create_markdown_link(
            "📖 читай полную новость здесь",
            source_url
        )
        message += f"""
━━━━━━━━━━━━━━━━━━
📍 *Источник:* {source}
{source_link}

👤 Поделись с друзьями: 👥
💬 Обсуди в комментариях: 💭
━━━━━━━━━━━━━━━━━━
⏰ Свежая новость прямо сейчас ⚡
"""

        return message


class RichMediaMessage:
    """
    Полное сообщение с медиа:
    - Текст
    - Изображение (если есть в новости)
    - GIF (встроенный через поиск)
    - Ссылка
    """

    def __init__(
            self,
            text: str,
            image_url: Optional[str] = None,
            gif_query: Optional[str] = None,
    ):
        self.text = text
        self.image_url = image_url
        self.gif_query = gif_query

    async def send(self, bot, chat_id: int):
        """
        Отправьте полное сообщение в Telegram

        Порядок отправки:
        1. Основной текст с ссылкой
        2. Изображение (если есть)
        3. GIF (если есть)
        """
        try:
            # Отправьте основное текстовое сообщение
            await bot.send_message(
                chat_id=chat_id,
                text=self.text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            logger.info("✅ Текстовое сообщение отправлено")

            # Отправьте изображение если есть
            if self.image_url and ImageExtractor.is_valid_image_url(self.image_url):
                try:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=self.image_url,
                        caption="📸 Иллюстрация к новости",
                    )
                    logger.info("✅ Изображение отправлено")
                except Exception as e:
                    logger.warning(f"⚠️ Не смог отправить изображение: {e}")

            # Отправьте GIF если есть
            if self.gif_query:
                try:
                    # Используйте встроенного Telegram бота @gif
                    # Альтернативно отправьте через URL или file_id
                    await bot.send_animation(
                        chat_id=chat_id,
                        animation=self.gif_query,  # Это может быть file_id или URL
                        caption="🎬 Визуализация",
                    )
                    logger.info("✅ GIF отправлено")
                except Exception as e:
                    logger.warning(f"⚠️ Не смог отправить GIF: {e}")

            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")
            return False
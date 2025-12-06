# services/message_builder.py
"""
Оптимизированный форматировщик сообщений для Telegram:
- Полный текст новости (без обрезания)
- Фото вместе с текстом (единое сообщение)
- Ссылка источника встроена в слово
- Несколько цен: BTC, ETH, SOL
- "Настроение рынка" вместо просто "Настроение"
"""

import logging
from typing import Optional, Dict
from html import escape

logger = logging.getLogger(__name__)


class CryptoMultiPriceTracker:
    """Получение цен нескольких криптоактивов"""
    
    CRYPTO_IDS = {
        "bitcoin": "₿",
        "ethereum": "Ξ",
        "solana": "◎",
    }
    
    @staticmethod
    def format_multi_prices(prices: Dict[str, float]) -> str:
        """
        Форматируйте цены нескольких крипто
        
        prices = {
            "bitcoin": {"price": 50000, "change": 2.5},
            "ethereum": {"price": 3000, "change": -1.2},
            "solana": {"price": 150, "change": 5.8},
        }
        """
        if not prices:
            return ""
        
        lines = []
        
        # Bitcoin
        if "bitcoin" in prices:
            btc = prices["bitcoin"]
            emoji = "📈" if btc["change"] >= 0 else "📉"
            change_str = f"{btc['change']:+.2f}%"
            lines.append(f"₿ BTC: ${btc['price']:,} {emoji} {change_str}")
        
        # Ethereum
        if "ethereum" in prices:
            eth = prices["ethereum"]
            emoji = "📈" if eth["change"] >= 0 else "📉"
            change_str = f"{eth['change']:+.2f}%"
            lines.append(f"Ξ ETH: ${eth['price']:,.0f} {emoji} {change_str}")
        
        # Solana
        if "solana" in prices:
            sol = prices["solana"]
            emoji = "📈" if sol["change"] >= 0 else "📉"
            change_str = f"{sol['change']:+.2f}%"
            lines.append(f"◎ SOL: ${sol['price']:,.2f} {emoji} {change_str}")
        
        if lines:
            return "💰 *Цены криптовалют (24h):*\n" + "\n".join(lines)
        
        return ""


class TelegramGIFLibrary:
    """Библиотека GIF для визуализации настроения новости"""
    
    GIFS = {
        "bullish": {
            "query": "bull market",
            "keywords": ["pump", "rally", "surge", "spike", "прорыв", "рост", "взлет"]
        },
        "bearish": {
            "query": "bear market",
            "keywords": ["dump", "crash", "fall", "decline", "падение", "крах", "обвал"]
        },
        "neutral": {
            "query": "bitcoin",
            "keywords": ["stable", "consolidation", "sideways", "консолидация"]
        },
        "moon": {
            "query": "moon rocket",
            "keywords": ["moon", "луна"]
        },
        "crash": {
            "query": "crash burn",
            "keywords": ["crash", "liquidation", "rekt", "ликвидация"]
        },
    }
    
    @staticmethod
    def get_gif_query(keywords: str) -> str:
        """Получите тип GIF на основе ключевых слов"""
        keywords_lower = keywords.lower()
        
        for gif_type, gif_data in TelegramGIFLibrary.GIFS.items():
            for keyword in gif_data["keywords"]:
                if keyword in keywords_lower:
                    return gif_data["query"]
        
        return TelegramGIFLibrary.GIFS["neutral"]["query"]
    
    @staticmethod
    def get_sentiment_emoji(sentiment: str) -> str:
        """Получите эмодзи по настроению"""
        sentiments = {
            "bullish": "📈🟢",
            "bearish": "📉🔴",
            "neutral": "⚪",
            "moon": "🚀🌙",
            "crash": "💥🔥",
        }
        return sentiments.get(sentiment, "⚪")


class ImageExtractor:
    """Извлечение изображений из RSS новостей"""
    
    @staticmethod
    def extract_image_from_entry(entry: Dict) -> Optional[str]:
        """Извлеките URL изображения из RSS entry"""
        
        try:
            import re
            
            # 1. media_content
            if hasattr(entry, 'media_content') and entry.media_content:
                for media in entry.media_content:
                    if 'url' in media:
                        return media['url']
            
            # 2. enclosures
            if hasattr(entry, 'enclosures') and entry.enclosures:
                for enc in entry.enclosures:
                    if enc.get('type', '').startswith('image'):
                        return enc.get('href')
            
            # 3. links
            if hasattr(entry, 'links') and entry.links:
                for link in entry.links:
                    link_type = link.get('type', '')
                    if 'image' in link_type or link.get('rel') == 'image':
                        return link.get('href')
            
            # 4. summary (HTML img tag)
            if hasattr(entry, 'summary') and entry.summary:
                img_urls = re.findall(
                    r'<img[^>]+src=["\']([^"\']+)["\']',
                    entry.summary
                )
                if img_urls:
                    return img_urls[0]
            
            # 5. image поле
            if hasattr(entry, 'image'):
                if isinstance(entry.image, dict):
                    return entry.image.get('href') or entry.image.get('url')
                elif isinstance(entry.image, str):
                    return entry.image
            
            # 6. description для img
            if hasattr(entry, 'description') and entry.description:
                img_urls = re.findall(
                    r'<img[^>]+src=["\']([^"\']+)["\']',
                    entry.description
                )
                if img_urls:
                    return img_urls[0]
        
        except Exception as e:
            logger.debug(f"⚠️ Ошибка извлечения изображения: {e}")
        
        return None
    
    @staticmethod
    def is_valid_image_url(url: Optional[str]) -> bool:
        """Проверьте валидность URL изображения"""
        if not url:
            return False
        
        valid_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        url_lower = url.lower()
        
        if any(ext in url_lower for ext in valid_extensions):
            return True
        
        if 'image' in url_lower or 'img' in url_lower:
            return True
        
        return False


class AdvancedMessageFormatter:
    """
    Продвинутое форматирование сообщений для Telegram
    
    ✅ Полный текст новости
    ✅ Ссылка встроена в слово [читай источник](url)
    ✅ Фото вместе с текстом
    ✅ Цены BTC, ETH, SOL
    ✅ "Настроение рынка"
    """
    
    @staticmethod
    def create_markdown_link(text: str, url: str) -> str:
        """Создайте Markdown ссылку"""
        return f"[{escape(text)}]({escape(url)})"
    
    @staticmethod
    def format_professional_news(
        title: str,
        summary: str,
        source: str,
        source_url: str,
        prices: Optional[Dict] = None,
        sentiment: str = "neutral",
        image_url: Optional[str] = None,
        language: str = "en"
    ) -> Dict:
        """
        Форматируйте новость профессионально
        
        Возвращает:
        {
            "text": основной текст (с полным summary),
            "image_url": URL изображения,
            "gif_query": тип GIF,
        }
        """
        
        # Определите эмодзи по настроению
        sentiment_emoji = TelegramGIFLibrary.get_sentiment_emoji(sentiment)
        
        # Стартовый эмодзи
        start_emoji = "🔔📰"
        
        # ✅ ИЗМЕНЕНИЕ 1: Укоротите заголовок до 80 символов, но оставьте полный summary
        title_display = title[:80] if len(title) > 80 else title
        
        # Создайте основной текст
        message = f"""{start_emoji} *{title_display}*

{summary}

{sentiment_emoji} *Настроение рынка:* {sentiment.capitalize()}
"""
        
        # ✅ ИЗМЕНЕНИЕ 2: Добавьте цены нескольких крипто
        if prices:
            prices_str = CryptoMultiPriceTracker.format_multi_prices(prices)
            if prices_str:
                message += f"\n{prices_str}\n"
        
        # ✅ ИЗМЕНЕНИЕ 3: Ссылка встроена в слово источника
        source_link_text = "источник" if language == "ru" else "source"
        source_link = AdvancedMessageFormatter.create_markdown_link(
            source_link_text,
            source_url
        )
        message += f"\n📰 *{source}*: [{source_link_text}]({source_url})\n"
        
        # Добавьте CTA
        if language == "ru":
            message += "\n👥 Обсуди в комментариях 💬"
        else:
            message += "\n👥 Discuss in comments 💬"
        
        # Получите тип GIF
        gif_query = TelegramGIFLibrary.get_gif_query(title + " " + summary)
        
        return {
            "text": message,
            "image_url": image_url if ImageExtractor.is_valid_image_url(image_url) else None,
            "gif_query": gif_query,
        }


class RichMediaMessage:
    """
    ✅ ИЗМЕНЕНИЕ 4: Фото отправляется ВМЕСТЕ с текстом, а не отдельно
    
    Использует send_photo с caption вместо двух отдельных сообщений
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
        Отправьте сообщение с медиа
        
        Порядок:
        1. Основной текст с фото (если есть)
        2. GIF отдельно (если есть)
        """
        try:
            # ✅ ОСНОВНОЙ СПОСОБ: Отправьте фото с текстом вместе
            if self.image_url and ImageExtractor.is_valid_image_url(self.image_url):
                try:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=self.image_url,
                        caption=self.text,
                        parse_mode="Markdown",
                    )
                    logger.info("✅ Фото + текст отправлены вместе")
                except Exception as e:
                    logger.warning(f"⚠️ Не смог отправить фото: {e}")
                    # Fallback: отправьте только текст
                    await bot.send_message(
                        chat_id=chat_id,
                        text=self.text,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
                    logger.info("✅ Только текст отправлен (фото не смог)")
            else:
                # Если нет фото - отправьте только текст
                await bot.send_message(
                    chat_id=chat_id,
                    text=self.text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                logger.info("✅ Текст отправлен (нет фото)")
            
            # ✅ GIF отправляется отдельным сообщением (визуализация)
            if self.gif_query:
                try:
                    await asyncio.sleep(0.5)  # Небольшая задержка
                    await bot.send_animation(
                        chat_id=chat_id,
                        animation=self.gif_query,
                        caption="🎬",
                    )
                    logger.info("✅ GIF отправлено")
                except Exception as e:
                    logger.debug(f"⚠️ Не смог отправить GIF: {e}")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")
            return False


# Вспомогательная функция для получения цен нескольких крипто
async def get_multiple_crypto_prices() -> Optional[Dict]:
    """
    Получите цены BTC, ETH, SOL через CoinGecko API
    
    Возвращает:
    {
        "bitcoin": {"price": 50000, "change": 2.5},
        "ethereum": {"price": 3000, "change": -1.2},
        "solana": {"price": 150, "change": 5.8},
    }
    """
    try:
        import aiohttp
        import asyncio
        
        async with aiohttp.ClientSession() as session:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                "ids": "bitcoin,ethereum,solana",
                "vs_currencies": "usd",
                "include_24hr_change": "true"
            }
            
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    prices = {}
                    
                    if "bitcoin" in data:
                        btc = data["bitcoin"]
                        prices["bitcoin"] = {
                            "price": int(btc.get("usd", 0)),
                            "change": round(btc.get("usd_24h_change", 0), 2)
                        }
                    
                    if "ethereum" in data:
                        eth = data["ethereum"]
                        prices["ethereum"] = {
                            "price": eth.get("usd", 0),
                            "change": round(eth.get("usd_24h_change", 0), 2)
                        }
                    
                    if "solana" in data:
                        sol = data["solana"]
                        prices["solana"] = {
                            "price": sol.get("usd", 0),
                            "change": round(sol.get("usd_24h_change", 0), 2)
                        }
                    
                    return prices if prices else None
    
    except Exception as e:
        logger.error(f"❌ Ошибка получения цен: {e}")
    
    return None


import asyncio
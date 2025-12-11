# services/message_builder.py
"""
Финальная версия форматирования сообщений для Telegram:
✅ Индекс страха вместо настроения рынка
✅ Убраны эмодзи возле цен (заменены на обычные)
✅ Убраны GIF
✅ Ссылка встроена в слово источника
✅ BLEXLER ЧАТ со ссылкой
"""

import logging
import time
import re
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class CryptoMultiPriceTracker:
    """Получение цен нескольких криптоактивов с кэшированием"""

    _cache = None
    _cache_timestamp = 0
    CACHE_TTL = 300  # 5 минут

    @staticmethod
    def format_multi_prices(prices: Dict[str, Dict]) -> str:
        """
        ✅ ИСПРАВЛЕНО: Убраны эмодзи возле цен

        Формат:
        💰 Цены криптовалют (24h):
        🪙 BTC: $91,365 (+2.17%)
        🔷 ETH: $3,136 (+3.52%)
        🟣 SOL: $135.87 (+2.90%)
        """
        if not prices:
            return ""

        lines = []

        # Bitcoin
        if "bitcoin" in prices:
            btc = prices["bitcoin"]
            change_str = f"({btc['change']:+.2f}%)"
            lines.append(f"🪙 BTC: ${btc['price']:,} {change_str}")

        # Ethereum
        if "ethereum" in prices:
            eth = prices["ethereum"]
            change_str = f"({eth['change']:+.2f}%)"
            lines.append(f"🔷 ETH: ${eth['price']:,} {change_str}")

        # Solana
        if "solana" in prices:
            sol = prices["solana"]
            change_str = f"({sol['change']:+.2f}%)"
            lines.append(f"🟣 SOL: ${sol['price']:,.2f} {change_str}")

        if lines:
            return "💰 <b>Цены криптовалют (24h):</b>\n" + "\n".join(lines)

        return ""


class FearGreedIndexTracker:
    """
    ✅ НОВОЕ: Получение индекса страха и жадности

    Источник: Alternative.me Fear & Greed Index API
    """

    _cache = None
    _cache_timestamp = 0
    CACHE_TTL = 3600  # 1 час

    @staticmethod
    def get_fear_greed_emoji(value: int) -> str:
        """Получите эмодзи по значению индекса"""
        if value >= 75:
            return "🤑"  # Extreme Greed
        elif value >= 55:
            return "😊"  # Greed
        elif value >= 45:
            return "😐"  # Neutral
        elif value >= 25:
            return "😰"  # Fear
        else:
            return "😱"  # Extreme Fear

    @staticmethod
    def get_fear_greed_label(value: int, language: str = "ru") -> str:
        """Получите текстовую метку"""
        if language == "ru":
            if value >= 75:
                return "Экстремальная жадность"
            elif value >= 55:
                return "Жадность"
            elif value >= 45:
                return "Нейтрально"
            elif value >= 25:
                return "Страх"
            else:
                return "Экстремальный страх"
        else:
            if value >= 75:
                return "Extreme Greed"
            elif value >= 55:
                return "Greed"
            elif value >= 45:
                return "Neutral"
            elif value >= 25:
                return "Fear"
            else:
                return "Extreme Fear"

    @staticmethod
    async def get_fear_greed_index() -> Optional[Dict]:
        """
        Получите индекс страха и жадности

        Возвращает:
        {
            "value": 42,
            "label": "Fear",
            "emoji": "😰"
        }
        """
        # Проверьте кэш
        current_time = time.time()
        if (FearGreedIndexTracker._cache and
                current_time - FearGreedIndexTracker._cache_timestamp < FearGreedIndexTracker.CACHE_TTL):
            return FearGreedIndexTracker._cache

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                url = "https://api.alternative.me/fng/"

                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        if data and "data" in data and len(data["data"]) > 0:
                            fng_data = data["data"][0]
                            value = int(fng_data.get("value", 50))

                            result = {
                                "value": value,
                                "label": FearGreedIndexTracker.get_fear_greed_label(value, "ru"),
                                "emoji": FearGreedIndexTracker.get_fear_greed_emoji(value)
                            }

                            # Обновите кэш
                            FearGreedIndexTracker._cache = result
                            FearGreedIndexTracker._cache_timestamp = current_time

                            logger.info(f"😱 Индекс страха: {value}/100 ({result['label']})")

                            return result

        except Exception as e:
            logger.error(f"❌ Ошибка получения индекса страха: {e}")

            # Вернуть кэшированные данные если есть
            if FearGreedIndexTracker._cache:
                logger.warning("⚠️ Используем устаревший кэш индекса страха")
                return FearGreedIndexTracker._cache

        return None


class ImageExtractor:
    """Извлечение изображений из RSS новостей"""

    @staticmethod
    def extract_image_from_entry(entry: Dict) -> Optional[str]:
        """Извлеките URL изображения из RSS entry"""

        try:
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

            # 6. description
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
    # Карта картинок для монет (можно расширить)
    COIN_IMAGES = {
        "BTC": "https://s3.coinmarketcap.com/static-gravity/image/5cc0b99a8095453bb209c2963feb7e82.png",
        "ETH": "https://s3.coinmarketcap.com/static-gravity/image/28c114dc354e4444983637402dc4db42.png",
        "SOL": "https://s3.coinmarketcap.com/static-gravity/image/358e2d45387c47d792b0024ba1622325.png",
        "DOGE": "https://s3.coinmarketcap.com/static-gravity/image/b61920b727404223b207a9e223c70420.png",
        "General": "https://images.unsplash.com/photo-1621761191319-c6fb62004040?auto=format&fit=crop&w=1000&q=80"
        # Абстрактная крипта
    }

    @staticmethod
    def get_coin_image(coin_ticker: str) -> str:
        """Возвращает картинку для монеты или дефолтную"""
        return AdvancedMessageFormatter.COIN_IMAGES.get(coin_ticker, AdvancedMessageFormatter.COIN_IMAGES["General"])

    # ... (clean_text и smart_truncate оставляем как были) ...
    @staticmethod
    def clean_text(text: str) -> str:
        # Убираем HTML теги
        text = re.sub(r'<[^>]+>', '', text)
        # Убираем длинные технические строки (коды, ошибки)
        text = re.sub(r'[A-Za-z0-9+/=]{20,}', '', text)
        # Убираем лишние символы Markdown
        text = text.replace('*', '').replace('_', '').replace('`', '')
        # Убираем ссылки в тексте (обычно они мусорные)
        text = re.sub(r'http\S+', '', text)
        # Убираем множественные пробелы и переносы
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()

    @staticmethod
    def smart_truncate(text: str, length: int = 950) -> str:
        if len(text) <= length: return text
        cut_text = text[:length]
        last_end = max(cut_text.rfind('.'), cut_text.rfind('!'), cut_text.rfind('?'))
        if last_end > length // 2: return cut_text[:last_end + 1]
        return cut_text + "..."

        # services/message_builder.py

    @staticmethod
    def format_professional_news(
            title: str,
            summary: str,
            source: str,
            source_url: str,
            prices: Optional[Dict] = None,
            fear_greed: Optional[Dict] = None,
            image_url: Optional[str] = None,
            ai_data: Optional[Dict] = None
    ) -> Dict:

        # 1. Готовим "обвес" (цены, ссылки, футер)
        footer = ""

        # Инфо-блок
        if ai_data and ai_data.get("sentiment"):
            footer += f"\n📊 <b>Настроение:</b> {ai_data['sentiment']}"

        if fear_greed:
            footer += f"\n😱 <b>Индекс страха:</b> {fear_greed['value']}/100\n"

        if prices:
            prices_str = CryptoMultiPriceTracker.format_multi_prices(prices)
            if prices_str:
                footer += f"\n{prices_str}\n"

        footer += f"\n📰 Источник: <a href='{source_url}'>{source}</a>"
        footer += f"\n💬 <a href='https://t.me/+hwsBvRtEj2w3NTli'>BLEXLER ЧАТ</a>"

        # 2. Обработка Заголовка
        sentiment_emoji = "🔔"
        coin_tag = ""

        if ai_data:
            sentiment = ai_data.get("sentiment", "Neutral")
            coin = ai_data.get("coin", "")

            if "Bullish" in sentiment:
                sentiment_emoji = "🟢"
            elif "Bearish" in sentiment:
                sentiment_emoji = "🔴"

            if coin and coin != "Market":
                coin_tag = f"#{coin}"
                if not image_url:
                    image_url = AdvancedMessageFormatter.get_coin_image(coin)

        if not image_url:
            image_url = AdvancedMessageFormatter.COIN_IMAGES["General"]

        title_display = title[:100]  # Ограничим заголовок 100 символами

        # Заголовок сообщения
        header = f"{sentiment_emoji} <b>{title_display}</b> {coin_tag}\n\n"

        # 3. МАТЕМАТИКА ЛИМИТОВ (Самое важное!)
        # Лимит Telegram Caption = 1024 символа.
        # Вычисляем: 1024 - длина_заголовка - длина_футера - 50 (запас)
        used_length = len(header) + len(footer)
        available_length = 1024 - used_length - 50

        # Если места мало (меньше 200), ставим минимум 200, но тогда придется резать футер (редкий кейс)
        if available_length < 200:
            available_length = 200

            # 4. Чистка и обрезка Summary под точный размер
        summary = AdvancedMessageFormatter.clean_text(summary)
        summary_display = AdvancedMessageFormatter.smart_truncate(summary, length=available_length)

        # 5. Финальная сборка
        message = f"{header}{summary_display}\n{footer}"

        return {
            "text": message,
            "image_url": image_url,
        }


class RichMediaMessage:
    """
    Упрощённая отправка сообщений
    ✅ Убраны GIF
    ✅ Только фото + текст
    """

    def __init__(
            self,
            text: str,
            image_url: Optional[str] = None,
    ):
        self.text = text
        self.image_url = image_url

    async def send(self, bot, chat_id: int):
        """Отправьте сообщение с медиа"""
        try:
            import asyncio

            # Отправьте фото с текстом вместе
            if self.image_url and ImageExtractor.is_valid_image_url(self.image_url):
                try:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=self.image_url,
                        caption=self.text,
                        parse_mode="HTML",
                    )
                    logger.info("✅ Фото + текст отправлены")
                except Exception as e:
                    logger.warning(f"⚠️ Не смог отправить фото: {e}")
                    # Fallback: только текст
                    await bot.send_message(
                        chat_id=chat_id,
                        text=self.text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    logger.info("✅ Только текст отправлен")
            else:
                # Если нет фото - только текст
                await bot.send_message(
                    chat_id=chat_id,
                    text=self.text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
                logger.info("✅ Текст отправлен (нет фото)")

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}", exc_info=True)
            return False


# ✅ ИСПРАВЛЕНО: Кэширование цен
async def get_multiple_crypto_prices() -> Optional[Dict]:
    """
    Получите цены BTC, ETH, SOL с кэшированием

    Возвращает:
    {
        "bitcoin": {"price": 91365, "change": 2.17},
        "ethereum": {"price": 3136, "change": 3.52},
        "solana": {"price": 135.87, "change": 2.90},
    }
    """
    # Проверьте кэш
    current_time = time.time()
    if (CryptoMultiPriceTracker._cache and
            current_time - CryptoMultiPriceTracker._cache_timestamp < CryptoMultiPriceTracker.CACHE_TTL):
        logger.debug("💾 Используем кэшированные цены")
        return CryptoMultiPriceTracker._cache

    try:
        import aiohttp

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
                            "price": int(eth.get("usd", 0)),
                            "change": round(eth.get("usd_24h_change", 0), 2)
                        }

                    if "solana" in data:
                        sol = data["solana"]
                        prices["solana"] = {
                            "price": round(sol.get("usd", 0), 2),
                            "change": round(sol.get("usd_24h_change", 0), 2)
                        }

                    # Обновите кэш
                    if prices:
                        CryptoMultiPriceTracker._cache = prices
                        CryptoMultiPriceTracker._cache_timestamp = current_time
                        logger.info("💰 Цены обновлены и закэшированы")

                    return prices if prices else None

    except Exception as e:
        logger.error(f"❌ Ошибка получения цен: {e}")

        # Вернуть кэшированные данные если есть
        if CryptoMultiPriceTracker._cache:
            logger.warning("⚠️ Используем устаревший кэш цен")
            return CryptoMultiPriceTracker._cache

    return None
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
    """
    Финальное форматирование сообщений для Telegram
    """

    @staticmethod
    def clean_text(text: str) -> str:
        # 1. Удаляем длинные английские технические строки
        text = re.sub(r'[A-Za-z\s,\.]{50,}', '', text)
        # 2. Удаляем лишние звездочки
        text = text.replace('*', '')
        # 3. Чистим HTML
        text = re.sub(r'<[^>]+>', '', text)
        # 4. Удаляем множественные пробелы
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def smart_truncate(text: str, length: int = 950) -> str:
        """Обрезает текст умно: ищет конец предложения"""
        if len(text) <= length:
            return text

        # Берем кусок с запасом
        cut_text = text[:length]

        # Список знаков препинания, на которых можно закончить
        endings = ['. ', '! ', '? ', '\n']

        last_end = -1
        for char in endings:
            pos = cut_text.rfind(char)
            if pos > last_end:
                last_end = pos

        # Если нашли конец предложения во второй половине текста
        if last_end > length // 2:
            return cut_text[:last_end + 1]  # +1 чтобы захватить точку

        # Если предложений нет, режем по пробелу
        last_space = cut_text.rfind(' ')
        if last_space > length // 2:
            return cut_text[:last_space] + "..."

        return cut_text + "..."

    @staticmethod
    def format_professional_news(
            title: str,
            summary: str,
            source: str,
            source_url: str,
            prices: Optional[Dict] = None,
            fear_greed: Optional[Dict] = None,
            image_url: Optional[str] = None,
            language: str = "ru"
    ) -> Dict:
        # Укоротите заголовок
        title_display = title[:150]  # Увеличили лимит заголовка

        # 1. Сначала чистим
        summary = AdvancedMessageFormatter.clean_text(summary)

        # 2. Потом применяем "Умную обрезку" до 800 символов
        # (Лимит Telegram Caption = 1024, оставляем 200 под цены и ссылки)
        summary_display = AdvancedMessageFormatter.smart_truncate(summary, length=950)

        # Экранируем HTML
        from html import escape
        title_safe = escape(title_display)
        summary_safe = escape(summary_display)

        message = f"🔔 <b>{title_safe}</b>\n\n{summary_safe}\n"

        if fear_greed:
            message += f"\n{fear_greed['emoji']} Индекс страха: {fear_greed['value']}/100\n"

        if prices:
            prices_str = CryptoMultiPriceTracker.format_multi_prices(prices)
            if prices_str:
                message += f"\n{prices_str}\n"

        message += f"\n📰 Источник: <a href='{source_url}'>{source}</a>\n"
        message += f"\n💬 <a href='https://t.me/+hwsBvRtEj2w3NTli'>BLEXLER ЧАТ</a>"

        return {
            "text": message,
            "image_url": image_url if ImageExtractor.is_valid_image_url(image_url) else None,
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
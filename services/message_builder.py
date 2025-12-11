# services/message_builder.py
import logging
import re
import time
import aiohttp
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


# --- 1. ТРЕКЕР ЦЕН (Восстановлен) ---
async def get_multiple_crypto_prices() -> Optional[Dict]:
    """Получает цены BTC, ETH, SOL с кэшированием"""
    # Простая реализация кэша через замыкание или глобальные переменные модуля
    if hasattr(get_multiple_crypto_prices, "cache"):
        cache_data, cache_time = get_multiple_crypto_prices.cache
        if time.time() - cache_time < 300:  # 5 минут кэш
            return cache_data

    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum,solana",
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    prices = {}
                    for coin in ["bitcoin", "ethereum", "solana"]:
                        if coin in data:
                            prices[coin] = {
                                "price": data[coin]["usd"],
                                "change": data[coin]["usd_24h_change"]
                            }

                    # Сохраняем в кэш
                    get_multiple_crypto_prices.cache = (prices, time.time())
                    return prices
    except Exception as e:
        logger.error(f"Ошибка получения цен: {e}")
    return None


class CryptoMultiPriceTracker:
    @staticmethod
    def format_multi_prices(prices: Dict[str, Dict]) -> str:
        if not prices: return ""
        lines = []
        if "bitcoin" in prices:
            lines.append(f"🪙 BTC: ${prices['bitcoin']['price']:,} ({prices['bitcoin']['change']:+.2f}%)")
        if "ethereum" in prices:
            lines.append(f"🔷 ETH: ${prices['ethereum']['price']:,} ({prices['ethereum']['change']:+.2f}%)")
        if "solana" in prices:
            lines.append(f"🟣 SOL: ${prices['solana']['price']:.2f} ({prices['solana']['change']:+.2f}%)")

        return "💰 <b>Цены (24h):</b>\n" + "\n".join(lines)


# --- 2. ИНДЕКС СТРАХА (Восстановлен) ---
class FearGreedIndexTracker:
    _cache = None
    _cache_timestamp = 0

    @staticmethod
    async def get_fear_greed_index() -> Optional[Dict]:
        """Получает индекс страха с кэшированием"""
        if FearGreedIndexTracker._cache and time.time() - FearGreedIndexTracker._cache_timestamp < 3600:
            return FearGreedIndexTracker._cache

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.alternative.me/fng/", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            item = data["data"][0]
                            result = {
                                "value": int(item["value"]),
                                "label": item["value_classification"]
                            }
                            # Перевод лейбла
                            translations = {
                                "Extreme Fear": "Экстремальный страх",
                                "Fear": "Страх",
                                "Neutral": "Нейтрально",
                                "Greed": "Жадность",
                                "Extreme Greed": "Экстремальная жадность"
                            }
                            result["label"] = translations.get(result["label"], result["label"])

                            FearGreedIndexTracker._cache = result
                            FearGreedIndexTracker._cache_timestamp = time.time()
                            return result
        except Exception as e:
            logger.error(f"Ошибка индекса страха: {e}")
        return None


# --- 3. РАБОТА С КАРТИНКАМИ (Восстановлено) ---
class ImageExtractor:
    @staticmethod
    def extract_image_from_entry(entry: Dict) -> Optional[str]:
        """Пытается найти картинку в RSS entry"""
        try:
            if 'media_content' in entry:
                return entry.media_content[0]['url']
            if 'links' in entry:
                for link in entry.links:
                    if 'image' in link.type:
                        return link.href
            # Поиск в description через regex
            if 'summary' in entry:
                match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    @staticmethod
    def is_valid_image_url(url: Optional[str]) -> bool:
        if not url: return False
        return url.lower().startswith('http') and not url.endswith('.svg')


# --- 4. ФОРМАТИРОВАНИЕ (Ваш улучшенный код) ---
class AdvancedMessageFormatter:
    COIN_IMAGES = {
        "BTC": "https://s3.coinmarketcap.com/static-gravity/image/5cc0b99a8095453bb209c2963feb7e82.png",
        "ETH": "https://s3.coinmarketcap.com/static-gravity/image/28c114dc354e4444983637402dc4db42.png",
        "SOL": "https://s3.coinmarketcap.com/static-gravity/image/358e2d45387c47d792b0024ba1622325.png",
        "General": "https://images.unsplash.com/photo-1621761191319-c6fb62004040?auto=format&fit=crop&w=1000&q=80"
    }

    @staticmethod
    def get_coin_image(coin: str) -> str:
        return AdvancedMessageFormatter.COIN_IMAGES.get(coin, AdvancedMessageFormatter.COIN_IMAGES["General"])

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text)  # Убираем теги
        text = text.replace('[…]', '').replace('...', '')
        text = re.sub(r'Читать далее.*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def smart_truncate(text: str, length: int = 900) -> str:
        if len(text) <= length: return text
        cut = text[:length]
        last_dot = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
        if last_dot > length // 2:
            return cut[:last_dot + 1]
        return cut + "..."

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

        # Заголовок
        sentiment_emoji = "🔔"
        coin_tag = ""

        if ai_data:
            sent = ai_data.get("sentiment", "Neutral")
            if "Bullish" in sent:
                sentiment_emoji = "🟢"
            elif "Bearish" in sent:
                sentiment_emoji = "🔴"

            coin = ai_data.get("coin", "Market")
            if coin and coin != "Market":
                coin_tag = f"#{coin}"
                if not image_url: image_url = AdvancedMessageFormatter.get_coin_image(coin)

        if not image_url: image_url = AdvancedMessageFormatter.COIN_IMAGES["General"]

        header = f"{sentiment_emoji} <b>{title[:100]}</b> {coin_tag}\n\n"

        # Футер
        footer = ""
        if ai_data and ai_data.get("sentiment"):
            footer += f"\n📊 Настроение: {ai_data['sentiment']}"
        if fear_greed:
            footer += f"\n😱 Индекс страха: {fear_greed['value']}/100"
        if prices:
            price_str = CryptoMultiPriceTracker.format_multi_prices(prices)
            if price_str: footer += f"\n\n{price_str}"

        footer += f"\n\n📰 <a href='{source_url}'>{source}</a>"
        footer += f"\n👥 <a href='https://t.me/+hwsBvRtEj2w3NTli'>ОБЩИЙ ЧАТ BLEXLER</a>"

        # Расчет длины текста
        available_len = 1024 - len(header) - len(footer) - 50
        if available_len < 100: available_len = 100

        summary = AdvancedMessageFormatter.clean_text(summary)
        summary_display = AdvancedMessageFormatter.smart_truncate(summary, length=available_len)

        return {
            "text": f"{header}{summary_display}{footer}",
            "image_url": image_url
        }


class RichMediaMessage:
    def __init__(self, text: str, image_url: Optional[str] = None):
        self.text = text
        self.image_url = image_url

    async def send(self, bot, chat_id: int):
        try:
            if self.image_url and ImageExtractor.is_valid_image_url(self.image_url):
                try:
                    await bot.send_photo(chat_id=chat_id, photo=self.image_url, caption=self.text, parse_mode="HTML")
                    logger.info("✅ Фото + текст отправлены")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка фото: {e}. Шлю текст.")
                    await bot.send_message(chat_id=chat_id, text=self.text, parse_mode="HTML",
                                           disable_web_page_preview=True)
            else:
                await bot.send_message(chat_id=chat_id, text=self.text, parse_mode="HTML",
                                       disable_web_page_preview=True)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
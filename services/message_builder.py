# services/message_builder.py
import logging
import re
import aiohttp
import random
from typing import Optional, Dict, List
from functools import lru_cache
import asyncio

logger = logging.getLogger(__name__)


# === ASYNC LRU CACHE (Простая реализация) ===
def async_lru_cache(maxsize=128, ttl=300):
    """Декоратор для кэширования асинхронных функций с TTL."""

    def decorator(func):
        cache = {}
        cache_times = {}
        _lock = None  # Ленивая инициализация

        def get_lock():
            nonlocal _lock
            if _lock is None:
                _lock = asyncio.Lock()
            return _lock

        async def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            lock = get_lock()  # Получаем lock при первом вызове

            async with lock:
                # Проверяем наличие и актуальность
                if key in cache:
                    age = asyncio.get_event_loop().time() - cache_times[key]
                    if age < ttl:
                        logger.debug(f"✅ Cache HIT: {func.__name__}")
                        return cache[key]
                    else:
                        del cache[key]
                        del cache_times[key]

            # Выполняем функцию
            logger.debug(f"❌ Cache MISS: {func.__name__}")
            result = await func(*args, **kwargs)

            lock = get_lock()
            async with lock:
                cache[key] = result
                cache_times[key] = asyncio.get_event_loop().time()

                # Ограничиваем размер кэша
                if len(cache) > maxsize:
                    oldest_key = min(cache_times, key=cache_times.get)
                    del cache[oldest_key]
                    del cache_times[oldest_key]

            return result

        wrapper.cache_clear = lambda: cache.clear() or cache_times.clear()
        return wrapper

    return decorator


# === ТРЕКЕР ЦЕН (С КЭШИРОВАНИЕМ) ===
@async_lru_cache(maxsize=1, ttl=300)  # 5 минут кэш, 1 запись
async def get_multiple_crypto_prices() -> Optional[Dict]:
    """Получает цены BTC, ETH, SOL с автоматическим кэшированием"""
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
                                "change": data[coin].get("usd_24h_change", 0)
                            }

                    return prices

    except Exception as e:
        logger.error(f"Ошибка получения цен: {e}")

    return None


class CryptoMultiPriceTracker:
    @staticmethod
    def format_multi_prices(prices: Dict[str, Dict]) -> str:
        if not prices:
            return ""

        lines = []
        if "bitcoin" in prices:
            lines.append(
                f"🪙 BTC: ${prices['bitcoin']['price']:,} "
                f"({prices['bitcoin']['change']:+.2f}%)"
            )
        if "ethereum" in prices:
            lines.append(
                f"🔷 ETH: ${prices['ethereum']['price']:,} "
                f"({prices['ethereum']['change']:+.2f}%)"
            )
        if "solana" in prices:
            lines.append(
                f"🟣 SOL: ${prices['solana']['price']:.2f} "
                f"({prices['solana']['change']:+.2f}%)"
            )

        return "💰 <b>Цены (24h):</b>\n" + "\n".join(lines)


# === ИНДЕКС СТРАХА (С КЭШИРОВАНИЕМ) ===
class FearGreedIndexTracker:
    @staticmethod
    @async_lru_cache(maxsize=1, ttl=3600)  # 1 час кэш
    async def get_fear_greed_index() -> Optional[Dict]:
        """Получает индекс страха с автоматическим кэшированием"""
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

                            # Перевод
                            translations = {
                                "Extreme Fear": "Экстремальный страх",
                                "Fear": "Страх",
                                "Neutral": "Нейтрально",
                                "Greed": "Жадность",
                                "Extreme Greed": "Экстремальная жадность"
                            }
                            result["label"] = translations.get(result["label"], result["label"])

                            return result

        except Exception as e:
            logger.error(f"Ошибка индекса страха: {e}")

        return None


# === РАБОТА С КАРТИНКАМИ ===
class ImageExtractor:
    @staticmethod
    def extract_image_from_entry(entry: Dict) -> Optional[str]:
        """Извлекает URL изображения из RSS entry"""
        try:
            if 'media_content' in entry:
                return entry.media_content[0]['url']

            if 'links' in entry:
                for link in entry.links:
                    if 'image' in link.type:
                        return link.href

            if 'summary' in entry:
                match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
                if match:
                    return match.group(1)

        except Exception:
            pass

        return None

    @staticmethod
    def is_valid_image_url(url: Optional[str]) -> bool:
        if not url:
            return False
        return url.lower().startswith('http') and not url.endswith('.svg')


# === ФОРМАТИРОВАНИЕ ===
class AdvancedMessageFormatter:
    COIN_IMAGES = {
        "BTC": "https://s3.coinmarketcap.com/static-gravity/image/5cc0b99a8095453bb209c2963feb7e82.png",
        "ETH": "https://s3.coinmarketcap.com/static-gravity/image/28c114dc354e4444983637402dc4db42.png",
        "SOL": "https://s3.coinmarketcap.com/static-gravity/image/358e2d45387c47d792b0024ba1622325.png",
        "General": "https://images.unsplash.com/photo-1621761191319-c6fb62004040?auto=format&fit=crop&w=1000&q=80"
    }

    @staticmethod
    def get_coin_image(coin: str) -> str:
        return AdvancedMessageFormatter.COIN_IMAGES.get(
            coin,
            AdvancedMessageFormatter.COIN_IMAGES["General"]
        )

    @staticmethod
    def clean_text(text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('[…]', '').replace('...', '')
        text = re.sub(r'Читать далее.*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    @staticmethod
    def translate_sentiment(sentiment: str) -> str:
        """Переводит sentiment на русский язык"""
        translations = {
            "Extreme Bullish": "Экстремально бычий",
            "Bullish": "Бычий",
            "Neutral": "Нейтральный",
            "Bearish": "Медвежий",
            "Extreme Bearish": "Экстремально медвежий"
        }
        return translations.get(sentiment, sentiment)
    
    @staticmethod
    def insert_random_link(text: str, url: str) -> str:
        """Рандомно вставляет ссылку в одно из слов текста"""
        # Разбиваем текст на слова (сохраняем HTML теги)
        # Находим все слова (не HTML теги)
        words = re.findall(r'\b\w+\b', text)
        if not words:
            return text
        
        # Выбираем случайное слово
        random_word = random.choice(words)
        
        # Ищем слово в тексте (учитывая, что оно может быть частью HTML тега)
        # Заменяем только первое вхождение слова (не в HTML теге)
        pattern = r'\b' + re.escape(random_word) + r'\b'
        
        # Проверяем, не находится ли слово внутри HTML тега
        def replace_func(match):
            start = match.start()
            # Проверяем, что мы не внутри HTML тега
            text_before = text[:start]
            # Подсчитываем открытые и закрытые теги до этой позиции
            open_tags = text_before.count('<')
            close_tags = text_before.count('>')
            # Если количество открытых тегов больше закрытых, мы внутри тега
            if open_tags > close_tags:
                return match.group(0)  # Не заменяем
            # Заменяем на ссылку
            return f'<a href="{url}">{match.group(0)}</a>'
        
        result = re.sub(pattern, replace_func, text, count=1)
        return result

    @staticmethod
    def smart_truncate(text: str, length: int = 900) -> str:
        """Обрезает текст по словам (не режет слова посередине)"""
        if len(text) <= length:
            return text

        cut = text[:length]
        # Сначала ищем точку, восклицательный или вопросительный знак
        last_dot = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))

        if last_dot > length // 2:
            return cut[:last_dot + 1]

        # Если знаков препинания нет, обрезаем по последнему пробелу
        last_space = cut.rfind(' ')
        if last_space > length * 0.7:  # Если пробел не слишком близко к началу
            return cut[:last_space] + "..."
        
        # Если пробел слишком близко к началу, обрезаем с "..."
        return cut + "..."
    
    @staticmethod
    def smart_truncate_words(text: str, max_chars: int) -> str:
        """Обрезает текст по словам (не режет слова посередине)"""
        if len(text) <= max_chars:
            return text
        
        cut = text[:max_chars]
        last_space = cut.rfind(' ')
        
        if last_space > max_chars * 0.7:  # Если пробел не слишком близко к началу
            return cut[:last_space] + "..."
        
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
            ai_data: Optional[Dict] = None,
            technical_analysis: Optional[Dict] = None,
            key_points: Optional[List[str]] = None,
            full_content: Optional[str] = None
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
                if not image_url:
                    image_url = AdvancedMessageFormatter.get_coin_image(coin)

        if not image_url:
            image_url = AdvancedMessageFormatter.COIN_IMAGES["General"]

        # ✅ ИСПРАВЛЕНО: Увеличиваем лимит заголовка (или убираем обрезку для более полного отображения)
        # Убираем обрезку заголовка для более полного отображения
        title_display = title  # Не обрезаем заголовок
        
        # ✅ НОВОЕ: Рандомно вставляем ссылку в заголовок
        title_with_link = AdvancedMessageFormatter.insert_random_link(title_display, source_url)
        header = f"{sentiment_emoji} <b>{title_with_link}</b> {coin_tag}\n\n"

        # ✅ НОВОЕ: Контент с ключевыми моментами (bullet points)
        content_section = ""
        
        if key_points and len(key_points) > 0:
            # Используем ключевые моменты для bullet points
            content_section = "📝 <b>Ключевые моменты:</b>\n"
            for point in key_points[:3]:  # Максимум 3 пункта
                # ✅ ИСПРАВЛЕНО: Убираем обрезку ключевых моментов для более полного отображения
                point_clean = AdvancedMessageFormatter.clean_text(point)
                point_display = point_clean  # Не обрезаем ключевые моменты
                # ✅ ИСПРАВЛЕНО: Убрали ссылку из ключевых моментов (оставляем только в заголовке)
                
                content_section += f"• {point_display}\n"
            content_section += "\n"
        elif full_content:
            # Если нет key_points, используем выжимку из full_content
            from services.content_summarizer import ContentSummarizer
            try:
                summary_text = ContentSummarizer.create_extractive_summary(full_content, sentences_count=3)
                if summary_text:
                    content_section = AdvancedMessageFormatter.clean_text(summary_text)
                    content_section = AdvancedMessageFormatter.smart_truncate(content_section, length=400)
                    content_section += "\n\n"
            except Exception:
                # Fallback на summary
                pass
        
        # Если content_section пустой, используем summary
        if not content_section:
            summary_clean = AdvancedMessageFormatter.clean_text(summary)
            content_section = AdvancedMessageFormatter.smart_truncate(summary_clean, length=400)
            content_section += "\n\n"

        # Футер
        footer = ""
        
        # ✅ ИСПРАВЛЕНО: Настроение (sentiment) на русском
        # Проверяем наличие ai_data и sentiment более тщательно
        if ai_data:
            sentiment = ai_data.get("sentiment")
            if sentiment:  # Проверяем, что sentiment не пустой
                sentiment_ru = AdvancedMessageFormatter.translate_sentiment(sentiment)
                footer += f"📊 <b>Настроение:</b> {sentiment_ru}\n"
        
        # Индекс страха
        if fear_greed:
            footer += f"😱 <b>Индекс страха:</b> {fear_greed['value']}/100\n"
        
        # ✅ ИСПРАВЛЕНО: Убрали разделитель после индекса страха
        
        # ✅ ИСПРАВЛЕНО: Цены (каждая монета с новой строки + изменение за 24ч)
        if prices:
            if "bitcoin" in prices:
                change_24h = prices['bitcoin'].get('change', 0)
                change_emoji = "📈" if change_24h >= 0 else "📉"
                footer += f"{change_emoji} BTC: ${prices['bitcoin']['price']:,.0f} ({change_24h:+.2f}%)\n"
            if "ethereum" in prices:
                change_24h = prices['ethereum'].get('change', 0)
                change_emoji = "📈" if change_24h >= 0 else "📉"
                footer += f"{change_emoji} ETH: ${prices['ethereum']['price']:,.0f} ({change_24h:+.2f}%)\n"
            if "solana" in prices:
                change_24h = prices['solana'].get('change', 0)
                change_emoji = "📈" if change_24h >= 0 else "📉"
                footer += f"{change_emoji} SOL: ${prices['solana']['price']:.2f} ({change_24h:+.2f}%)\n"

        # Сборка сообщения
        text = f"{header}{content_section}{footer}"
        
        # Проверка длины (Telegram limit: 1024 символа)
        if len(text) > 1024:
            # Укорачиваем контент
            max_content_len = 1024 - len(header) - len(footer) - 50
            if max_content_len > 100:
                if key_points:
                    # Укорачиваем ключевые моменты
                    content_section = "📝 <b>Ключевые моменты:</b>\n"
                    for point in key_points[:2]:  # Оставляем только 2 пункта
                        point_clean = AdvancedMessageFormatter.clean_text(point)
                        point_display = point_clean[:max_content_len // 2] + "..."
                        content_section += f"• {point_display}\n"
                    content_section += "\n"
                else:
                    content_section = AdvancedMessageFormatter.smart_truncate(
                        content_section, length=max_content_len
                    ) + "\n\n"
                text = f"{header}{content_section}{footer}"

        return {
            "text": text,
            "image_url": image_url
        }


class RichMediaMessage:
    def __init__(self, text: str, image_url: Optional[str] = None, reply_markup=None):
        self.text = text
        self.image_url = image_url
        self.reply_markup = reply_markup

    async def send(self, bot, chat_id: int):
        try:
            if self.image_url and ImageExtractor.is_valid_image_url(self.image_url):
                try:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=self.image_url,
                        caption=self.text,
                        parse_mode="HTML",
                        reply_markup=self.reply_markup
                    )
                    logger.info("✅ Фото + текст отправлены")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка фото: {e}. Отправляю текст.")
                    await bot.send_message(
                        chat_id=chat_id,
                        text=self.text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=self.reply_markup
                    )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=self.text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=self.reply_markup
                )
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
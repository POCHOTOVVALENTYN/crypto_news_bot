# parser/rss_parser.py
import feedparser
import aiohttp
import asyncio
import re
from typing import List, Dict
from html import unescape

# ✅ ИСПРАВЛЕНО: Только рабочие источники
RSS_FEEDS = {
    "Forklog": "https://forklog.com/feed/",
    "Bits.media": "https://bits.media/feed/",
}

# Английские источники (fallback)
ENGLISH_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/feed",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
}

WHITELIST_KEYWORDS = [
    "bitcoin", "ethereum", "btc", "eth", "crypto", "blockchain",
    "sec", "regulation", "trading", "market", "price", "exchange",
    "ripple", "xrp", "solana", "cardano", "polygon", "bnb", "usdt",
    "крипто", "биткойн", "эфириум", "блокчейн", "торговля",
    "рынок", "цена", "обмен", "регуляция", "майнинг",
]

BLACKLIST_KEYWORDS = [
    "nft collection", "airdrop", "presale", "promo", "giveaway",
    "casino", "gambling", "lottery", "scam",
    "гивэвей", "казино", "лотерея", "пампинг", "схема",
]

# ✅ НОВОЕ: Слова для удаления из описания
REMOVE_KEYWORDS = [
    "источник:", "джерело:", "source:", "via:", "read more:",
    "подробнее:", "читать далее:", "читать полностью:",
    "cryptoquant", "glassnode", "coindesk", "cointelegraph",
    "forklog", "bits.media", "cryptonuz", "miningcrypto",
]


def clean_html(text: str) -> str:
    """Удалите HTML теги и расшифруйте HTML сущности"""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def remove_source_mentions(text: str) -> str:
    """
    ✅ НОВОЕ: Удалите упоминания источников из текста

    Примеры:
    - "Источник: CryptoQuant" → ""
    - "Source: Bloomberg" → ""
    - "via CoinDesk" → ""
    """
    text_lower = text.lower()

    # Найдите позицию первого упоминания источника
    min_position = len(text)

    for keyword in REMOVE_KEYWORDS:
        pos = text_lower.find(keyword.lower())
        if pos != -1 and pos < min_position:
            min_position = pos

    # Обрежьте текст до первого упоминания источника
    if min_position < len(text):
        text = text[:min_position].strip()

    # Удалите финальные точки/запятые если остались
    text = text.rstrip('.,;: ')

    return text


class RSSParser:
    def __init__(self, use_russian: bool = True):
        self.feeds = RSS_FEEDS if use_russian else ENGLISH_FEEDS
        self.use_russian = use_russian

    @staticmethod
    def _is_relevant(title: str, description: str = "") -> bool:
        """Проверьте релевантность новости"""
        text = (title + " " + description).lower()

        # Сначала blacklist
        for keyword in BLACKLIST_KEYWORDS:
            if keyword in text:
                return False

        # Затем whitelist
        for keyword in WHITELIST_KEYWORDS:
            if keyword in text:
                return True

        return False

    @staticmethod
    def _detect_language(text: str) -> str:
        """Определите язык текста"""
        if re.search(r'[а-яА-ЯёЁ]', text):
            return "ru"
        return "en"

    @staticmethod
    def _extract_image_from_entry(entry: dict) -> str:
        """Извлеките изображение из entry"""
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
            print(f"⚠️ Ошибка извлечения изображения: {e}")

        return None

    async def fetch_feed(self, feed_url: str) -> List[dict]:
        """Парсьте RSS ленту с улучшенной обработкой ошибок"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        feed_url,
                        timeout=aiohttp.ClientTimeout(total=20)  # ✅ Увеличен до 20 секунд
                ) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        feed = feedparser.parse(content)
                        return feed.entries[:20]
                    else:
                        print(f"⚠️ HTTP {resp.status}: {feed_url}")
        except asyncio.TimeoutError:
            print(f"⏱️ Timeout (20s): {feed_url}")
        except aiohttp.ClientConnectorError as e:
            print(f"🔌 Connection error: {feed_url}")
        except Exception as e:
            print(f"❌ Unexpected error: {feed_url}: {e}")

        return []

    async def get_all_news(self) -> List[Dict]:
        """Получите новости из всех источников"""
        all_news = []

        for source_name, feed_url in self.feeds.items():
            print(f"🔄 Fetching: {source_name}...")
            entries = await self.fetch_feed(feed_url)

            if not entries:
                print(f"⚠️ No entries from {source_name}")
                continue

            print(f"✅ Found {len(entries)} entries from {source_name}")

            for entry in entries:
                title = entry.get("title", "No title")
                link = entry.get("link", "")
                published = entry.get("published", "")
                summary = entry.get("summary", "")

                # Очистите HTML
                summary = clean_html(summary)

                # ✅ НОВОЕ: Удалите упоминания источников
                summary = remove_source_mentions(summary)

                # Проверка релевантности
                if not self._is_relevant(title, summary):
                    continue

                # Определите язык
                lang = self._detect_language(title + " " + summary)

                # Извлеките изображение
                image_url = self._extract_image_from_entry(entry)

                # ✅ ИСПРАВЛЕНО: Полный summary без обрезания
                all_news.append({
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "published": published,
                    "summary": summary,  # Полный текст
                    "language": lang,
                    "image_url": image_url,
                    "raw_entry": entry,
                })

        return all_news
# parser/rss_parser.py
import feedparser
import aiohttp
import asyncio
import re
from typing import List, Dict
from html import unescape

# Русскоязычные источники с ХОРОШЕЙ поддержкой изображений
RSS_FEEDS = {
    "Forklog": "https://forklog.com/feed/",
    "CryptoNuz": "https://cryptonuz.ru/feed/",
    "Bits.media": "https://bits.media/feed/",
    "Miningcrypto": "https://miningcrypto.ru/feed/",
}

# Английские источники (fallback)
ENGLISH_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/feed",
    "Cointelegraph": "https://cointelegraph.com/feed",
    "Decrypt": "https://decrypt.co/feed",
}

WHITELIST_KEYWORDS = [
    "bitcoin", "ethereum", "btc", "eth", "crypto", "blockchain",
    "sec", "regulation", "trading", "market", "price", "exchange",
    "ripple", "xrp", "solana", "cardano", "polygon",
    "крипто", "биткойн", "эфириум", "блокчейн", "торговля",
    "рынок", "цена", "обмен", "регуляция",
]

BLACKLIST_KEYWORDS = [
    "nft collection", "airdrop", "presale", "promo", "giveaway",
    "casino", "gambling", "lottery",
    "гивэвей", "казино", "лотерея", "пампинг", "схема",
]


def clean_html(text: str) -> str:
    """Удалите HTML теги и расшифруйте HTML сущности"""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class RSSParser:
    def __init__(self, use_russian: bool = True):
        self.feeds = RSS_FEEDS if use_russian else ENGLISH_FEEDS
        self.use_russian = use_russian

    @staticmethod
    def _is_relevant(title: str, description: str = "") -> bool:
        """Проверьте релевантность новости"""
        text = (title + " " + description).lower()

        for keyword in BLACKLIST_KEYWORDS:
            if keyword in text:
                return False

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
        """
        Попытайтесь извлечь изображение из entry

        Проверяет:
        1. media_content
        2. enclosures
        3. links с type=image
        4. img src в summary
        5. image поле
        """

        try:
            # 1. Проверьте media_content (Podcast/Media RSS)
            if hasattr(entry, 'media_content') and entry.media_content:
                for media in entry.media_content:
                    if 'url' in media:
                        return media['url']

            # 2. Проверьте enclosures
            if hasattr(entry, 'enclosures') and entry.enclosures:
                for enc in entry.enclosures:
                    if enc.get('type', '').startswith('image'):
                        return enc.get('href')

            # 3. Проверьте links
            if hasattr(entry, 'links') and entry.links:
                for link in entry.links:
                    link_type = link.get('type', '')
                    if 'image' in link_type or link.get('rel') == 'image':
                        return link.get('href')

            # 4. Извлеките из summary (HTML img tag)
            if hasattr(entry, 'summary') and entry.summary:
                img_urls = re.findall(
                    r'<img[^>]+src=["\']([^"\']+)["\']',
                    entry.summary
                )
                if img_urls:
                    return img_urls[0]

            # 5. Проверьте поле image
            if hasattr(entry, 'image'):
                if isinstance(entry.image, dict):
                    return entry.image.get('href') or entry.image.get('url')
                elif isinstance(entry.image, str):
                    return entry.image

            # 6. Проверьте description для img
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
        """Парсьте RSS ленту"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        feed = feedparser.parse(content)
                        return feed.entries[:20]
        except asyncio.TimeoutError:
            print(f"⚠️ Timeout: {feed_url}")
        except Exception as e:
            print(f"❌ Ошибка: {feed_url}: {e}")

        return []

    async def get_all_news(self) -> List[Dict]:
        """Получите новости из всех источников с изображениями"""
        all_news = []

        for source_name, feed_url in self.feeds.items():
            entries = await self.fetch_feed(feed_url)

            for entry in entries:
                title = entry.get("title", "No title")
                link = entry.get("link", "")
                published = entry.get("published", "")
                summary = entry.get("summary", "")

                summary = clean_html(summary)

                if not self._is_relevant(title, summary):
                    continue

                # Определите язык
                lang = self._detect_language(title + " " + summary)

                # Извлеките изображение
                image_url = self._extract_image_from_entry(entry)

                all_news.append({
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "published": published,
                    "summary": summary[:300],
                    "language": lang,
                    "image_url": image_url,  # ✅ Новое поле
                    "raw_entry": entry,  # ✅ Сохраните оригинальный entry для дополнительной обработки
                })

        return all_news
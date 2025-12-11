# parser/rss_parser.py
import feedparser
import aiohttp
import asyncio
import re
from typing import List, Dict
from html import unescape

# ✅ ОСТАВЛЯЕМ ТОЛЬКО РАБОЧИЕ
RSS_FEEDS = {
    "Forklog": "https://forklog.com/feed/",
    "Coinspot": "https://coinspot.io/feed/",
}

TIER_1_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "The Block": "https://www.theblock.co/rss.xml",
}

# ✅ WHITELIST расширен
WHITELIST_KEYWORDS = [
    # Криптовалюты
    "bitcoin", "ethereum", "btc", "eth", "crypto", "blockchain",
    "solana", "cardano", "polygon", "bnb", "usdt", "usdc",
    "ripple", "xrp", "doge", "dogecoin", "shib", "ada", "dot",

    # Регуляция
    "sec", "regulation", "регуляция", "законодательство",
    "trump", "трамп", "biden", "байден", "congress", "конгресс",

    # Компании
    "coinbase", "binance", "bybit", "okx", "kraken",
    "microstrategy", "tesla", "blackrock", "grayscale",

    # События
    "etf", "listing", "листинг", "hack", "взлом",
    "trading", "торговля", "market", "рынок", "price", "цена",

    # Русский
    "крипто", "биткойн", "эфириум", "блокчейн",
    "биржа", "обмен", "майнинг",
]

BLACKLIST_KEYWORDS = [
    "nft collection", "airdrop", "presale", "promo", "giveaway",
    "casino", "gambling", "lottery", "scam", "ponzi",
    "гивэвей", "казино", "лотерея", "схема", "развод",
]

REMOVE_KEYWORDS = [
    "источник:", "джерело:", "source:", "via:", "read more:",
    "подробнее:", "читать далее:", "читать полностью:",
    "cryptoquant", "glassnode", "coindesk", "cointelegraph",
    "forklog", "bits.media", "rbc", "coinspot",
]


def clean_html(text: str) -> str:
    """Удалите HTML теги и расшифруйте HTML сущности"""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def remove_source_mentions(text: str) -> str:
    """Удалите упоминания источников из текста"""
    text_lower = text.lower()
    min_position = len(text)

    for keyword in REMOVE_KEYWORDS:
        pos = text_lower.find(keyword.lower())
        if pos != -1 and pos < min_position:
            min_position = pos

    if min_position < len(text):
        text = text[:min_position].strip()

    text = text.rstrip('.,;: ')
    return text


class RSSParser:
    def __init__(self, use_russian: bool = True, include_tier1: bool = True):
        """
        use_russian: русскоязычные источники
        include_tier1: добавить премиум англоязычные
        """
        self.feeds = {}

        if use_russian:
            self.feeds.update(RSS_FEEDS)

        if include_tier1:
            self.feeds.update(TIER_1_FEEDS)

    @staticmethod
    def _is_relevant(title: str, description: str = "") -> bool:
        """Проверьте релевантность новости"""
        text = (title + " " + description).lower()

        # Blacklist
        for keyword in BLACKLIST_KEYWORDS:
            if keyword in text:
                return False

        # Whitelist
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
            pass

        return None

    async def fetch_feed(self, feed_url: str) -> List[dict]:
        """Парсьте RSS ленту с улучшенной обработкой ошибок"""
        try:
            # ✅ ДОБАВЛЕН User-Agent (некоторые сайты блокируют без него)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                        feed_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        feed = feedparser.parse(content)
                        return feed.entries[:20]
                    else:
                        print(f"⚠️ HTTP {resp.status}: {feed_url}")

        except asyncio.TimeoutError:
            print(f"⏱️ Timeout (20s): {feed_url}")
        except aiohttp.ClientConnectorError:
            print(f"🔌 Connection error: {feed_url}")
        except Exception as e:
            print(f"❌ Error: {feed_url}: {e}")

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

                summary = clean_html(summary)
                summary = remove_source_mentions(summary)

                # Проверка релевантности
                if not self._is_relevant(title, summary):
                    continue

                lang = self._detect_language(title + " " + summary)
                image_url = self._extract_image_from_entry(entry)

                all_news.append({
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "published": published,
                    "summary": summary,
                    "language": lang,
                    "image_url": image_url,
                    "raw_entry": entry,
                })

        return all_news
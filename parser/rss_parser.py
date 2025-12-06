# parser/rss_parser.py
import feedparser
import aiohttp
import asyncio
import re
from typing import List, Dict
from html import unescape

RSS_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/feed",
    "Cointelegraph": "https://cointelegraph.com/feed",
    "Decrypt": "https://decrypt.co/feed",
}

WHITELIST_KEYWORDS = [
    "bitcoin", "ethereum", "btc", "eth", "crypto", "blockchain",
    "sec", "regulation", "trading", "market", "price", "exchange",
    "ripple", "xrp", "solana", "cardano", "polygon",
]

BLACKLIST_KEYWORDS = [
    "nft collection", "airdrop", "presale", "promo", "giveaway",
    "casino", "gambling", "lottery",
]


def clean_html(text: str) -> str:
    """Удалите HTML теги и расшифруйте HTML сущности"""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class RSSParser:
    def __init__(self):
        self.feeds = RSS_FEEDS

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

    async def fetch_feed(self, feed_url: str) -> List[Dict]:
        """Парсьте RSS ленту"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        feed = feedparser.parse(content)
                        return feed.entries[:15]
        except asyncio.TimeoutError:
            print(f"⚠️ Timeout: {feed_url}")
        except Exception as e:
            print(f"❌ Ошибка: {feed_url}: {e}")

        return []

    async def get_all_news(self) -> List[Dict]:
        """Получите новости из всех источников"""
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

                all_news.append({
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "published": published,
                    "summary": summary[:250],
                })

        return all_news
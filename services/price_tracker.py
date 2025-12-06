# services/price_tracker.py
import asyncio

import aiohttp
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class PriceTracker:
    """Получение актуальной цены Bitcoin"""

    @staticmethod
    async def get_bitcoin_price() -> Optional[Dict]:
        """
        Получите текущую цену BTC через CoinGecko API (бесплатный)
        Возвращает: {usd, change_24h}
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.coingecko.com/api/v3/simple/price"
                params = {
                    "ids": "bitcoin",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true"
                }

                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        btc_data = data.get("bitcoin", {})

                        price = btc_data.get("usd")
                        change = btc_data.get("usd_24h_change", 0)

                        if price:
                            return {
                                "price": int(price),
                                "change_24h": round(change, 2),
                                "emoji": "📈" if change >= 0 else "📉"
                            }
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout при получении цены BTC")
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены: {e}")

        return None

    @staticmethod
    def format_price(btc_data: Dict) -> str:
        """Форматируйте цену BTC для сообщения"""
        if not btc_data:
            return ""

        price = f"${btc_data['price']:,}"
        change = btc_data['change_24h']
        emoji = btc_data['emoji']

        change_str = f"{change:+.2f}%"
        return f"\n💰 BTC: {price} {emoji} {change_str} (24h)"
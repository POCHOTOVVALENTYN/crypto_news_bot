# services/price_tracker.py
import asyncio
import aiohttp
import logging
from typing import Optional, Dict
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger(__name__)


class PriceTracker:
    """Получение актуальной цены Bitcoin"""

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), 
           retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)))
    async def get_bitcoin_price() -> Optional[Dict]:
        """
        Получите текущую цену BTC через CoinGecko API (бесплатный)
        Возвращает: {usd, change_24h}
        """
        # Трай-эксепт убираем, чтобы tenacity могла ловить ошибки и делать повторы
        # Ошибка будет перехвачена вызывающим кодом после всех попыток
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
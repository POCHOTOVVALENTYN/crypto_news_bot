# parser/api_client.py
import aiohttp
import asyncio
from typing import List, Dict


class CryptoPanicAPI:
    """
    CryptoPanic API агрегатор (опционально, требует регистрации)
    Docs: https://cryptopanic.com/developers/api/
    """
    BASE_URL = "https://cryptopanic.com/api/v1/posts/"

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    async def get_latest_news(self, currency: str = "bitcoin") -> List[Dict]:
        """
        Получите последние новости по валюте
        Требует free API ключ с cryptopanic.com
        """
        if not self.api_key:
            return []

        try:
            params = {
                "auth_token": self.api_key,
                "kind": "news",
                "currency": currency,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(self.BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("results", [])
        except Exception as e:
            print(f"❌ CryptoPanic API error: {e}")

        return []
# services/exchange_monitor.py
import aiohttp

async def check_binance_listings():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    async with aiohttp.ClientSession() as session:
        data = await session.get(url)
        symbols = [s['symbol'] for s in data['symbols']]
        # Сравниваем с сохраненным списком. Если есть новый - АЛЕРТ!
        # ... логика сравнения ...
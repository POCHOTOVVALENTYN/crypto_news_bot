# services/webhook_receiver.py
from datetime import datetime

from aiohttp import web

from database import db


async def receive_emergency_news(request):
    """
    Внешний сервис может отправить POST:
    {
        "title": "SEC одобрил BTC ETF",
        "summary": "...",
        "urgency": "critical"
    }
    """
    data = await request.json()

    await db.add_news(
        url=f"webhook_{datetime.now().timestamp()}",
        title=data['title'],
        summary=data['summary'],
        source="⚡ WEBHOOK",
        published_at="Now",
        priority=1  # Молния
    )

    return web.Response(text="OK")


app = web.Application()
app.router.add_post('/emergency', receive_emergency_news)
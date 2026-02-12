#!/usr/bin/env python3
"""
Тестовый скрипт для проверки автопостинга с изображением
"""
import asyncio
import json
from database import db
from services.publish_helper import publish_single_news

async def test_autopost():
    """Создаёт и публикует тестовую новость"""
    
    # Тестовые данные новости
    test_news = {
        'url': 'test_autopost_' + str(asyncio.get_event_loop().time()),
        'title': 'Bitcoin достиг нового исторического максимума',
        'summary': 'Цена Bitcoin впервые превысила отметку в 100,000 долларов на фоне растущего институционального интереса. Аналитики прогнозируют дальнейший рост.',
        'source': '⚡ Insider',
        'published_at': 'Just now',
        'image_url': None,  # Будет использовано дефолтное изображение
        'priority': 10,
        'metadata': json.dumps({
            'is_telegram_source': True,
            'telegram_channel': 'Test Channel',
            'telegram_link': 'https://t.me/test'
        })
    }
    
    print("📝 Создаю тестовую новость в БД...")
    await db.add_news(**test_news)
    print("✅ Новость добавлена в БД")
    
    # Получаем созданную новость
    async with db.conn.execute(
        "SELECT * FROM news WHERE url = ?",
        (test_news['url'],)
    ) as cursor:
        cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        news_item = await cursor.fetchone()
    
    if news_item:
        print(f"📰 Публикую новость: {news_item['title'][:50]}...")
        message_id = await publish_single_news(news_item, is_breaking=True)
        
        if message_id:
            print(f"✅ Новость опубликована! Message ID: {message_id}")
            print(f"🔗 Ссылка: https://t.me/blexler_invest/{message_id}")
        else:
            print("❌ Ошибка публикации")
    else:
        print("❌ Новость не найдена в БД")

if __name__ == "__main__":
    asyncio.run(test_autopost())

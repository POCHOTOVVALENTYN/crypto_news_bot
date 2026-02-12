#!/usr/bin/env python3
"""
Тестовый скрипт для проверки автопостинга с ЛОКАЛЬНЫМ изображением
Этот скрипт имитирует работу Userbot с скачанным изображением
"""
import asyncio
import json
import shutil
from pathlib import Path
from database import db
from services.publish_helper import publish_single_news

async def test_autopost_with_image():
    """Создаёт и публикует тестовую новость с локальным изображением"""
    
    # Инициализируем БД
    await db.init()
    print("✅ База данных инициализирована")
    
    # Путь к тестовому изображению (используем сгенерированное)
    test_image_source = "/Users/valentin/.gemini/antigravity/brain/32fa2f20-6271-48b2-9625-0057bb97df4a/test_bitcoin_news_1770895688689.png"
    test_image_dest = "media/temp/test_bitcoin_news.png"
    
    # Создаём директорию если не существует
    Path("media/temp").mkdir(parents=True, exist_ok=True)
    
    # Копируем тестовое изображение
    if Path(test_image_source).exists():
        shutil.copy(test_image_source, test_image_dest)
        print(f"📸 Тестовое изображение скопировано: {test_image_dest}")
        image_url = test_image_dest
    else:
        print(f"⚠️ Тестовое изображение не найдено по пути: {test_image_source}")
        print("   Будет использовано дефолтное изображение")
        image_url = None
    
    # Тестовые данные новости с Markdown (для проверки очистки)
    test_news = {
        'url': 'test_autopost_' + str(int(asyncio.get_event_loop().time())),
        'title': '[BREAKING] Bitcoin достиг $100,000 - новый исторический максимум',
        'summary': 'Цена [Bitcoin](https://bitcoin.org) впервые превысила отметку в **100,000 долларов** на фоне растущего институционального интереса. Аналитики прогнозируют дальнейший рост к отметке $150,000.',
        'source': '⚡ Insider',
        'published_at': 'Just now',
        'image_url': image_url,
        'priority': 10,
        'metadata': json.dumps({
            'is_telegram_source': True,
            'telegram_channel': 'Test Crypto News',
            'telegram_link': 'https://t.me/test_channel/12345'
        })
    }
    
    print("\n📝 Создаю тестовую новость в БД...")
    print(f"   Заголовок: {test_news['title']}")
    print(f"   Изображение: {test_news['image_url']}")
    
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
        print(f"\n📰 Публикую новость...")
        print(f"   Оригинальный заголовок: {news_item['title']}")
        print(f"   Оригинальное описание: {news_item['summary'][:100]}...")
        
        message_id = await publish_single_news(news_item, is_breaking=True)
        
        if message_id:
            print(f"\n✅ Новость опубликована! Message ID: {message_id}")
            print(f"🔗 Ссылка: https://t.me/blexler_invest/{message_id}")
            print("\n🔍 Проверьте:")
            print("   1. Изображение - должно быть тестовое (Bitcoin $100k)")
            print("   2. Заголовок - без [BREAKING] и квадратных скобок")
            print("   3. Текст - без Markdown ([text](url), **bold**)")
        else:
            print("❌ Ошибка публикации")
    else:
        print("❌ Новость не найдена в БД")

if __name__ == "__main__":
    asyncio.run(test_autopost_with_image())

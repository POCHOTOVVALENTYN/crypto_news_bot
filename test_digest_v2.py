import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Импорты
from database import db
from services.digest_builder import digest_builder

async def test_digest_v2():
    print("🚀 Starting Digest 2.0 Test...")
    
    # 1. Инициализация БД
    await db.init()
    
    # 2. Мокаем AI Analyzer для теста
    digest_builder.ai_analyzer.analyze_text = AsyncMock(return_value={
        "category": "Bitcoin",
        "sentiment_score": 8,
        "why_it_matters": "Это важно, потому что цена биткоина влияет на весь рынок."
    })
    
    # 3. Создаем тестовые новости
    test_news = [
        {
            "url": "http://test1.com",
            "title": "Bitcoin Hits $100k",
            "summary": "BTC finally reached the moon.",
            "source": "Test Source",
            "published_at": "2024-01-01",
            "added_at": "2024-01-01 12:00:00",
            # Симулируем отсутствие данных (чтобы сработал Lazy Analysis)
            "category": None,
            "sentiment_score": None,
            "why_it_matters": None
        },
        {
            "url": "http://test2.com",
            "title": "SEC Approves Ethereum ETF",
            "summary": "Regulatory win for ETH.",
            "source": "Test Source",
            "published_at": "2024-01-01",
            "added_at": "2024-01-01 12:05:00",
            "category": "Regulation", # Уже есть категория
            "sentiment_score": 9,
            "why_it_matters": "Институционалы заходят в эфир."
        }
    ]
    
    print(f"📰 Processing {len(test_news)} test news items...")
    
    # 4. Запускаем категоризацию (Lazy Analysis)
    # Мы не можем вызвать _categorize_and_process напрямую с dict, так как он ожидает записи из БД
    # Но для теста мы передадим словари, так как DigestBuilder работает с dict (cursor.row_factory)
    
    categorized, sentiment_data = await digest_builder._categorize_and_process(test_news)
    
    print("\n✅ Categorization Result:")
    for cat, items in categorized.items():
        print(f"  Category: {cat} ({len(items)} items)")
        for item in items:
            print(f"    - {item['title']} (Score: {item.get('sentiment_score')})")
            
    print(f"\n📊 Sentiment Data: Average={sentiment_data['average']}")
    
    # 5. Формирование HTML
    digest_html = await digest_builder._format_digest(categorized, sentiment_data, len(test_news))
    
    print("\n📝 GENERATED DIGEST HTML:")
    print("="*40)
    print(digest_html)
    print("="*40)
    
    # Проверки
    assert "Настроение рынка" in digest_html, "Header language failed"
    assert "Bitcoin" in digest_html, "Category grouping failed"
    assert "Это важно" in digest_html, "Why it matters failed"
    
    print("\n✅ TEST PASSED!")

if __name__ == "__main__":
    asyncio.run(test_digest_v2())

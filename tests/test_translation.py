"""
Скрипт для тестирования перевода новостей
Проверяет, что английский текст переводится на русский
"""
import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_translation():
    """Тестирование перевода новости"""
    print("=" * 60)
    print("🧪 ТЕСТ ПЕРЕВОДА НОВОСТЕЙ")
    print("=" * 60)
    
    from database import db
    import aiosqlite
    
    # Инициализируем БД
    await db.init()
    
    # Получаем тестовую новость
    async with aiosqlite.connect(db.db_path) as conn:
        async with conn.execute(
            "SELECT * FROM news WHERE url = 'test_translation_fix_001'"
        ) as cursor:
            row = await cursor.fetchone()
            
            if not row:
                print("❌ Тестовая новость не найдена")
                print("💡 Запустите SQL команду для создания тестовой новости:")
                print("""
sqlite3 crypto_news.db "INSERT INTO news (url, title, summary, full_content, source, published_at, priority, posted_to_telegram) 
VALUES ('test_translation_fix_001', 
        'Bitcoin reaches new all-time high above \$100,000', 
        '<p>The cryptocurrency market is celebrating as <b>Bitcoin</b> (BTC) reaches \$100,000.</p>', 
        'The cryptocurrency market is celebrating as Bitcoin reaches \$100,000 for the first time.', 
        'Test Source', 
        '2026-02-10', 
        5, 
        0)"
                """)
                return False
            
            # Конвертируем row в dict
            columns = [desc[0] for desc in cursor.description]
            news_item = dict(zip(columns, row))
    
    print(f"\n📰 Тестовая новость найдена:")
    print(f"  URL: {news_item['url']}")
    print(f"  Title (до): {news_item['title']}")
    print(f"  Summary (до): {news_item.get('summary', '')[:100]}...")
    print(f"  Full_content (до): {news_item.get('full_content', '')[:100]}...")
    
    # Тестируем перевод через publish_helper
    print("\n🔄 Запуск тестового перевода...")
    
    from services.publish_helper import publish_single_news
    from services.translator import translator
    from services.message_builder import AdvancedMessageFormatter
    
    # Создаем копию для тестирования
    test_item = news_item.copy()
    
    # Симулируем часть логики publish_single_news для проверки
    loop = asyncio.get_event_loop()
    
    # Тест 1: Перевод title
    print("\n1️⃣ Тест перевода title...")
    if test_item.get('title'):
        detected_lang = await loop.run_in_executor(
            None, translator.detect_language, test_item['title']
        )
        print(f"  Определен язык: {detected_lang}")
        
        if detected_lang and detected_lang != 'ru':
            translated_title = await loop.run_in_executor(
                None, translator.translate_text, 
                test_item['title'], detected_lang, 'ru'
            )
            print(f"  ✅ Title переведен: {translated_title}")
        else:
            print(f"  ℹ️ Title уже на русском")
    
    # Тест 2: Очистка и перевод summary
    print("\n2️⃣ Тест очистки и перевода summary...")
    if test_item.get('summary'):
        summary_clean = AdvancedMessageFormatter.clean_text(test_item['summary'])
        print(f"  После clean_text: {summary_clean[:100]}")
        
        detected_lang = await loop.run_in_executor(
            None, translator.detect_language, summary_clean
        )
        print(f"  Определен язык: {detected_lang}")
        
        if detected_lang and detected_lang != 'ru':
            translated_summary = await loop.run_in_executor(
                None, translator.translate_text,
                summary_clean, detected_lang, 'ru'
            )
            print(f"  ✅ Summary переведен: {translated_summary[:100]}...")
    
    # Тест 3: Очистка и перевод full_content
    print("\n3️⃣ Тест очистки и перевода full_content...")
    if test_item.get('full_content'):
        content_clean = AdvancedMessageFormatter.clean_text(test_item['full_content'])
        print(f"  После clean_text: {content_clean[:100]}...")
        
        detected_lang = await loop.run_in_executor(
            None, translator.detect_language, content_clean[:500]
        )
        print(f"  Определен язык: {detected_lang}")
        
        if detected_lang and detected_lang != 'ru':
            translated_content = await loop.run_in_executor(
                None, translator.translate_text,
                content_clean, detected_lang, 'ru'
            )
            print(f"  ✅ Full_content переведен: {translated_content[:100]}...")
    
    print("\n" + "=" * 60)
    print("✅ ТЕСТ ЗАВЕРШЕН")
    print("=" * 60)
    
    # Очистка: удаляем тестовую новость
    print("\n🧹 Удаление тестовой новости...")
    await db.execute_query(
        "DELETE FROM news WHERE url = 'test_translation_fix_001'"
    )
    print("✅ Тестовая новость удалена")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_translation())
    sys.exit(0 if success else 1)

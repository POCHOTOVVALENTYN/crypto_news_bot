"""
Скрипт проверки рефакторинга системы постинга новостей
Проверяет миграции БД и наличие новых компонентов
"""
import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_database_migrations():
    """Проверка миграций БД"""
    print("🔍 Проверка миграций базы данных...")
    
    from database import db
    import aiosqlite
    
    # Инициализируем БД
    await db.init()
    
    # Проверяем колонки в таблице news
    async with aiosqlite.connect(db.db_path) as conn:
        async with conn.execute("PRAGMA table_info(news)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
            
            required_columns = {'metadata', 'digest_batch_id'}
            missing = required_columns - columns
            
            if missing:
                print(f"❌ Отсутствуют колонки: {missing}")
                return False
            else:
                print(f"✅ Все необходимые колонки присутствуют: {required_columns}")
        
        # Проверяем таблицу news_digests
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='news_digests'"
        ) as cursor:
            if not await cursor.fetchone():
                print("❌ Таблица news_digests не создана")
                return False
            else:
                print("✅ Таблица news_digests создана")
        
        # Проверяем таблицу pending_breaking_news
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_breaking_news'"
        ) as cursor:
            if not await cursor.fetchone():
                print("❌ Таблица pending_breaking_news не создана")
                return False
            else:
                print("✅ Таблица pending_breaking_news создана")
    
    return True


async def test_services_import():
    """Проверка импорта новых сервисов"""
    print("\n🔍 Проверка импорта сервисов...")
    
    try:
        from services.content_deduplicator import ContentDeduplicator
        print("✅ ContentDeduplicator импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта ContentDeduplicator: {e}")
        return False
    
    try:
        from services.digest_builder import digest_builder
        print("✅ digest_builder импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта digest_builder: {e}")
        return False
    
    try:
        from services.breaking_news_moderator import breaking_moderator
        print("✅ breaking_moderator импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта breaking_moderator: {e}")
        return False
    
    try:
        from services.publish_helper import publish_single_news
        print("✅ publish_helper импортирован")
    except Exception as e:
        print(f"❌ Ошибка импорта publish_helper: {e}")
        return False
    
    return True


async def test_deduplication():
    """Тест дедупликации контента"""
    print("\n🔍 Тест дедупликации контента...")
    
    from services.content_deduplicator import ContentDeduplicator
    
    # Тест 1: Title-Description overlap
    title = "Bitcoin достиг $50000"
    description = "Bitcoin достиг новой вершины в $50000"
    
    overlap = ContentDeduplicator.detect_title_description_overlap(title, description, threshold=0.7)
    print(f"  Тест overlap: {'✅ Обнаружено' if overlap else '❌ НЕ обнаружено'} (expected: True)")
    
    # Тест 2: Дедупликация key points
    key_points = [
        "Bitcoin достиг $50000 впервые за 6 месяцев",
        "Ethereum вырос на 5%",
        "Рынок криптовалют показывает позитивную динамику"
    ]
    
    filtered = ContentDeduplicator.deduplicate_key_points(title, key_points, threshold=0.5)
    print(f"  Тест key points: {len(key_points)} → {len(filtered)} ({'✅' if len(filtered) < len(key_points) else '⚠️'})")
    
    # Тест 3: Smart summarize
    result = await ContentDeduplicator.smart_summarize(title, description, key_points)
    print(f"  Smart summarize: {'✅ Дедупликация применена' if result['dedup_applied'] else '⚠️ Без изменений'}")
    
    return True


async def main():
    """Главная функция теста"""
    print("=" * 60)
    print("🧪 ПРОВЕРКА РЕФАКТОРИНГА СИСТЕМЫ ПОСТИНГА НОВОСТЕЙ")
    print("=" * 60)
    
    results = []
    
    # 1. Миграции БД
    results.append(await test_database_migrations())
    
    # 2. Импорт сервисов
    results.append(await test_services_import())
    
    # 3. Тест дедупликации
    results.append(await test_deduplication())
    
    # Итоги
    print("\n" + "=" * 60)
    if all(results):
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
    print("=" * 60)
    
    return all(results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

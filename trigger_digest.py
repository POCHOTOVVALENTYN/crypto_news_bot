import asyncio
import logging
import sys
from dotenv import load_dotenv

# Настройка логирования в stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Загружаем переменные окружения
load_dotenv()

from database import db
from services.digest_builder import digest_builder

async def trigger_digest():
    print("🚀 Запуск принудительного дайджеста (Final Check buttons)...")
    try:
        # 1. Инициализация БД
        await db.init()
        print("✅ БД подключена")
        
        # 1.5. СБРОС СТАТУСА ПУБЛИКАЦИИ ДЛЯ ПОСЛЕДНИХ 7 НОВОСТЕЙ (FORCE MODE)
        print("🔄 Сбрасываем статус последних 7 новостей для теста...")
        
        # Получаем ID последних новостей
        async with db.conn.execute("SELECT id FROM news ORDER BY id DESC LIMIT 7") as cursor:
            rows = await cursor.fetchall()
            ids = [row[0] for row in rows]
            
        if ids:
            placeholders = ','.join('?' * len(ids))
            sql = f"UPDATE news SET posted_to_telegram = 0, digest_batch_id = NULL WHERE id IN ({placeholders})"
            async with db.conn.execute(sql, ids) as cursor:
                await db.conn.commit()
                print(f"✅ Сброшено новостей: {cursor.rowcount}")
        else:
            print("⚠️ Нет новостей для сброса")

        # 2. Запуск сборки дайджеста
        await digest_builder.build_and_publish_digest()
        
        print("🏁 Процесс завершен")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        if db.conn:
            await db.conn.close()

if __name__ == "__main__":
    asyncio.run(trigger_digest())

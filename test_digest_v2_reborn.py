import asyncio
import logging
import sys
from services.digest_builder import digest_builder
from database import db
from config import config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_digest_v2():
    try:
        await db.init()
        
        # 1. Получаем новости
        logger.info("📥 Fetching last 15 news for test...")
        async with db.conn.execute(
            "SELECT * FROM news ORDER BY id DESC LIMIT 15"
        ) as cursor:
            cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            news_list = await cursor.fetchall()
            
        if not news_list:
            return

        # 2. Категоризация
        categorized_news, sentiment_data = await digest_builder._categorize_and_process(news_list)
        
        # 3. Форматирование
        digest_html = await digest_builder._format_digest(categorized_news, sentiment_data, len(news_list))
        
        # 4. Отправка в КАНАЛ
        CHANNEL_ID = config.telegram_channel_id
        from loader import bot
        
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=f"🧪 <b>TEST DIGEST 2.0 (UPDATED)</b>\n\n{digest_html}",
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
    finally:
        await db.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_digest_v2())

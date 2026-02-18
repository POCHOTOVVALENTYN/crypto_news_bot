import asyncio
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from loader import bot
from database import db
from services.publish_helper import publish_single_news

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SEARCH_QUERY = "Давление со стороны продавцов альткоинов"

async def publish_missed_news():
    print(f"🔍 Searching for news with query: '{SEARCH_QUERY}'...")
    
    await db.init()
    
    try:
        # Search in news table
        async with db.conn.execute(
            "SELECT * FROM news WHERE title LIKE ? OR summary LIKE ? OR full_content LIKE ?", 
            (f"%{SEARCH_QUERY}%", f"%{SEARCH_QUERY}%", f"%{SEARCH_QUERY}%")
        ) as cursor:
            # Convert row to dict
            columns = [description[0] for description in cursor.description]
            row = await cursor.fetchone()
            
            if row:
                news_item = dict(zip(columns, row))
                print(f"✅ Found news: {news_item['title']}")
                print(f"🔗 URL: {news_item['url']}")
                print("🚀 Publishing...")
                
                # Mock call to publish_single_news if needed, or real call
                # We need to make sure we are not running this locally if the user expects it on PROD
                # But since I cannot run on prod, I will just invoke the function.
                # WARNING: If local config ID is different, it might publish to test channel.
                
                msg_id = await publish_single_news(news_item, is_breaking=True)
                
                if msg_id:
                    print(f"🎉 Successfully published! Message ID: {msg_id}")
                else:
                    print("❌ Failed to publish.")
            else:
                print("⚠️ News not found in the local database.")
                print("ℹ️ If this is running locally, the DB might be outdated.")
                print("ℹ️ Please deploy this script to the server and run it there.")
                
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await db.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(publish_missed_news())

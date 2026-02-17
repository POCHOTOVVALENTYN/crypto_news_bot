import asyncio
import logging
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from database import db
from services.breaking_news_moderator import breaking_moderator
from loader import bot

# Mock bot.send_message
async def mock_send_message(*args, **kwargs):
    print(f"Mock send_message called with: {kwargs.get('text', 'No text')}")

bot.send_message = mock_send_message

async def test_moderation_timeout():
    print("🚀 Starting Timeout Logic Test...")
    
    # 1. Init DB
    await db.init()
    
    # 2. Prepare Test Data
    test_url = f"https://test.com/breaking_{int(datetime.now().timestamp())}"
    
    # Insert news item using helper method
    success = await db.add_news(
        url=test_url,
        title="TEST BREAKING NEWS",
        summary="Test Summary",
        source="Test Source",
        published_at=datetime.now().isoformat(),
        priority=10
    )
    print(f"News inserted success: {success}")

    print(f"DB Path: {db.db_path}")
    
    # Verify table exists
    tables = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_breaking_news'")
    if not tables:
        print("❌ ERROR: Table pending_breaking_news DOES NOT EXIST!")
        return
    else:
        print("✅ Table pending_breaking_news exists.")

    # Insert pending request OLDER than timeout (e.g. 10 mins ago)
    old_time = datetime.now() - timedelta(minutes=10)
    
    try:
        await db.conn.execute(
            """
            INSERT INTO pending_breaking_news (news_url, detected_at, admin_decision)
            VALUES (?, ?, 'pending')
            """,
            (test_url, old_time.isoformat())
        )
        await db.conn.commit()
        print("✅ Insert executed and COMMITTED")
    except Exception as e:
        print(f"❌ Insert FAILED with error: {e}")
    
    # Get ID
    rows = await db.execute("SELECT id FROM pending_breaking_news WHERE news_url = ?", (test_url,))
    print(f"Pending rows found: {rows}")
    
    if not rows:
        print("❌ ERROR: Pending request NOT found in DB")
        return

    pending_id = rows[0][0]
    print(f"📝 Created pending request #{pending_id} with time {old_time}")

    # 3. Running loop
    # Need to wait for processing to ensure async operations complete if any (though handle_expired_requests is awaited)
    
    # 3. Run Expiration Check
    print("🔄 Running handle_expired_requests()...")
    await breaking_moderator.handle_expired_requests()
    
    # 4. Verify Results
    rows = await db.execute("SELECT admin_decision, auto_published FROM pending_breaking_news WHERE id = ?", (pending_id,))
    result = rows[0]
    decision = result[0]
    auto_published = result[1]
    
    print(f"📊 Result: Decision='{decision}', AutoPublished={auto_published}")
    
    if decision == 'expired' and not auto_published:
        print("✅ TEST PASSED: Request expired correctly.")
    else:
        print("❌ TEST FAILED: Request NOT expired or auto_published.")

    # Cleanup
    await db.execute("DELETE FROM pending_breaking_news WHERE id = ?", (pending_id,))
    await db.execute("DELETE FROM news WHERE url = ?", (test_url,))
    await db.conn.close()

if __name__ == "__main__":
    asyncio.run(test_moderation_timeout())

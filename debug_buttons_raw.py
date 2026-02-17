import asyncio
import logging
from aiogram import Bot
from config import config

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    bot = Bot(token=config.telegram_bot_token, parse_mode="HTML")
    
    chat_id = config.telegram_channel_id # Trying channel first, or admin_id if preferred
    # Override to admin_id for safety if needed, but user pointed to channel message.
    # Let's send to admin_id to avoid spamming channel if possible, but user wants to see it.
    # User referenced channel msg 8195. Let's try sending to ADMIN first to verify.
    target_id = config.admin_id
    
    logger.info(f"Sending raw JSON button test to {target_id}...")

    # Raw Dict Markup - circumventing aiogram types completely
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "🔵 Raw Primary (Blue)",
                    "url": "https://t.me/+514GO2tFjAtkMWRi",
                    "style": "primary"
                }
            ],
            [
                {
                    "text": "🟢 Raw Success (Green)",
                    "url": "https://t.me/blexler_invest",
                    "style": "success"
                }
            ],
             [
                {
                    "text": "🔴 Raw Danger (Red)",
                    "url": "https://google.com",
                    "style": "danger"
                }
            ]
        ]
    }

    try:
        # aiogram send_message accepts Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply, Dict[str, Any], None]
        await bot.send_message(
            chat_id=target_id,
            text="🧪 Тест цветных кнопок (Raw JSON payload)",
            reply_markup=reply_markup
        )
        logger.info("✅ Raw JSON message sent!")
    except Exception as e:
        logger.error(f"❌ Error sending raw JSON: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())

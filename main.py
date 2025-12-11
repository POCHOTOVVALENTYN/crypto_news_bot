# main.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from database import db
from parser.rss_parser import RSSParser
# Теперь этот импорт сработает корректно
from services.message_builder import (
    AdvancedMessageFormatter,
    RichMediaMessage,
    FearGreedIndexTracker,
    get_multiple_crypto_prices,
    ImageExtractor
)
from services.ai_summary import NewsAnalyzer
from services.rate_limiter import RateLimiter
from services.telegram_listener import listener

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()  # ✅ ДОБАВЛЕН Dispatcher
router = Router()
rss_parser = RSSParser(use_russian=True)
scheduler = AsyncIOScheduler()
ai_analyzer = NewsAnalyzer()
rate_limiter = RateLimiter(min_interval_seconds=300)  # 5 минут


# --- Команды бота ---
@router.message(Command("stats"))
async def cmd_stats(message):
    total = await db.execute("SELECT COUNT(*) FROM news")
    posted = await db.execute("SELECT COUNT(*) FROM news WHERE posted_to_telegram=1")
    # Используем cursor.fetchone() для получения значения
    # (в вашем прошлом коде это не сработало бы, т.к. execute возвращает курсор)
    async with aiosqlite.connect(db.db_path) as conn:
        async with conn.execute("SELECT COUNT(*) FROM news") as cursor:
            total = (await cursor.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM news WHERE posted_to_telegram=1") as cursor:
            posted = (await cursor.fetchone())[0]

    await message.answer(f"📊 Статистика:\nВсего: {total}\nОпубликовано: {posted}\nВ очереди: {total - posted}")


dp.include_router(router)  # ✅ Подключаем роутер


# --- Логика парсинга и постинга ---
async def scheduled_parsing():
    """Сбор новостей"""
    try:
        logger.info("🔍 Парсер: ищу свежие новости...")
        news_list = await rss_parser.get_all_news()
        count = 0
        for news in news_list:
            if not await db.news_exists(news['link']):
                await db.add_news(
                    url=news['link'],
                    title=news['title'],
                    summary=news['summary'],
                    source=news['source'],
                    published_at=news['published'],
                    image_url=news['image_url']
                )
                count += 1
        if count > 0: logger.info(f"📥 Добавлено {count} новостей")
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")


async def check_queue_and_post():
    """Проверка очереди"""
    try:
        # 1. Горячие новости (вне очереди)
        hot_news = await db.get_hot_news()
        is_hot = False

        if hot_news:
            news_item = hot_news
            is_hot = True
            logger.info("🔥 Молния! Публикую вне очереди.")
        else:
            # 2. Обычные новости (по таймеру)
            if not rate_limiter.can_post():
                return
            news_item = await db.get_oldest_unposted_news()

        if not news_item: return

        # Публикация
        logger.info(f"🚀 Публикация: {news_item['title'][:30]}")

        # Подготовка данных
        ai_data = None
        if "Insider" in news_item['source']:
            ai_data = await ai_analyzer.analyze_text(news_item['title'] + " " + news_item['summary'])
        else:
            ai_result = await ai_analyzer.translate_and_analyze(news_item['title'], news_item['summary'])
            if ai_result:
                news_item['title'] = ai_result.get('clean_title', news_item['title'])
                news_item['summary'] = ai_result.get('clean_summary', news_item['summary'])
                ai_data = ai_result

        prices = await get_multiple_crypto_prices()
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()

        msg_data = AdvancedMessageFormatter.format_professional_news(
            title=news_item['title'],
            summary=news_item['summary'],
            source=news_item['source'],
            source_url=news_item['url'],
            prices=prices,
            fear_greed=fear_greed,
            image_url=news_item['image_url'],
            ai_data=ai_data
        )

        rich_msg = RichMediaMessage(msg_data['text'], msg_data['image_url'])
        if await rich_msg.send(bot, TELEGRAM_CHANNEL_ID):
            await db.mark_as_posted(news_item['url'])
            if not is_hot:
                rate_limiter.mark_posted()

    except Exception as e:
        logger.error(f"Ошибка в постере: {e}", exc_info=True)


# --- Startup ---
async def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        logger.error("❌ Нет токена или ID канала в .env")
        return

    await db.init()
    logger.info("✅ БД подключена")

    # Запуск Userbot
    asyncio.create_task(listener.start())

    # Планировщик
    scheduler.add_job(scheduled_parsing, IntervalTrigger(minutes=10))
    scheduler.add_job(check_queue_and_post, IntervalTrigger(seconds=30))
    scheduler.start()

    # Первый прогон
    asyncio.create_task(scheduled_parsing())
    asyncio.create_task(check_queue_and_post())

    # ✅ Запуск Polling (блокирует выполнение, держит бота активным)
    logger.info("🚀 Бот запущен (Polling)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Импорт aiosqlite нужен внутри cmd_stats, добавим его если нет в глобальных
    import aiosqlite

    asyncio.run(main())
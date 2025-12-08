# main.py
import asyncio
import logging
import os
from datetime import datetime, timedelta
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from database import db
from parser.rss_parser import RSSParser
from services.message_builder import (
    AdvancedMessageFormatter,
    RichMediaMessage,
    FearGreedIndexTracker,
    get_multiple_crypto_prices
)
from services.ai_summary import NewsAnalyzer
# Импортируем наш RateLimiter (он у вас уже есть в файлах)
from services.rate_limiter import RateLimiter

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

bot = Bot(token=TELEGRAM_BOT_TOKEN)
rss_parser = RSSParser(use_russian=True)
scheduler = AsyncIOScheduler()
ai_analyzer = NewsAnalyzer()

# ✅ НАСТРОЙКА ИНТЕРВАЛОВ
# Как часто искать новые новости на сайтах (минуты)
PARSING_INTERVAL_MINUTES = 10
# Как часто публиковать новости в канал (минуты)
POSTING_INTERVAL_MINUTES = 5

# Инициализируем лимитер (300 секунд = 5 минут)
rate_limiter = RateLimiter(min_interval_seconds=POSTING_INTERVAL_MINUTES * 60)


async def scheduled_parsing():
    """Сбор новостей в базу"""
    try:
        logger.info("🔍 Парсер: ищу свежие новости...")
        news_list = await rss_parser.get_all_news()

        new_count = 0
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
                new_count += 1
                logger.info(f"📥 В очередь: {news['title'][:30]}...")

        if new_count > 0:
            logger.info(f"💾 Сохранено {new_count} новых новостей. Очередь пополнена.")
        else:
            logger.info("💤 Новых новостей на сайтах нет.")

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга: {e}")


async def check_queue_and_post():
    """
    Эта функция запускается КАЖДУЮ МИНУТУ.
    Она проверяет, можно ли уже постить (прошло ли 5 минут) и есть ли что постить.
    """
    try:
        # 1. Проверяем таймер (прошло ли 5 минут с прошлого поста?)
        if not rate_limiter.can_post():
            wait_time = rate_limiter.get_wait_time()
            # Логируем только раз в минуту, чтобы видеть, что бот жив
            logger.info(f"⏳ Ждем таймер: осталось {wait_time} сек")
            return

        # 2. Проверяем БД на наличие новостей
        news_item = await db.get_oldest_unposted_news()

        if not news_item:
            logger.info("📭 Очередь пуста. Ждем новых новостей от парсера.")
            return

        # ================= НАЧАЛО ПУБЛИКАЦИИ =================
        logger.info(f"🚀 Время пришло! Публикую: {news_item['title'][:30]}...")

        # Данные из БД
        title = news_item['title']
        summary = news_item['summary'] or ""
        source = news_item['source']
        url = news_item['url']
        image_url = news_item['image_url']

        # 3. ИИ Обработка (Gemini)
        ai_result = await ai_analyzer.translate_and_analyze(title, summary)

        if ai_result:
            logger.info("✨ ИИ улучшил текст")
            title = ai_result.get("clean_title", title)
            summary = ai_result.get("clean_summary", summary)
        else:
            logger.warning("⚠️ ИИ пропущен, используем оригинал")

        # 4. Рыночные данные
        prices = await get_multiple_crypto_prices()
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()

        # 5. Сборка сообщения
        formatted_msg = AdvancedMessageFormatter.format_professional_news(
            title=title,
            summary=summary,
            source=source,
            source_url=url,
            prices=prices,
            fear_greed=fear_greed,
            image_url=image_url,
        )

        # 6. Отправка
        rich_msg = RichMediaMessage(
            text=formatted_msg["text"],
            image_url=formatted_msg["image_url"],
        )

        success = await rich_msg.send(bot, TELEGRAM_CHANNEL_ID)

        if success:
            # Отмечаем как отправленное
            await db.mark_as_posted(url)
            # Сбрасываем таймер (засекаем следующие 5 минут)
            rate_limiter.mark_posted()
            logger.info(f"✅ Опубликовано. Следующий пост через {POSTING_INTERVAL_MINUTES} мин.")
        else:
            logger.error("❌ Ошибка API Telegram при отправке")
            # Можно добавить логику: если ошибка, попробовать через минуту, не отмечая posted

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в постере: {e}", exc_info=True)


async def startup():
    """Инициализация"""
    logger.info("🚀 Запуск бота v5.0 (Smart Queue)...")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise ValueError("Ошибка конфига: нет токена или ID")

    await db.init()
    logger.info("✅ БД подключена")

    # === РАСПИСАНИЕ ===

    # 1. Сбор новостей (Раз в 10 минут)
    scheduler.add_job(
        scheduled_parsing,
        IntervalTrigger(minutes=PARSING_INTERVAL_MINUTES),
        id="parsing_job",
        replace_existing=True
    )

    # 2. Проверка очереди (Каждую минуту) - Это реализует вашу логику
    scheduler.add_job(
        check_queue_and_post,
        IntervalTrigger(seconds=60),  # Проверяем часто
        id="queue_checker",
        replace_existing=True
    )

    logger.info(f"⏰ Парсинг: каждые {PARSING_INTERVAL_MINUTES} мин")
    logger.info(f"⏰ Постинг: очередь раз в {POSTING_INTERVAL_MINUTES} мин")

    scheduler.start()

    # Первый прогон парсинга сразу
    asyncio.create_task(scheduled_parsing())
    # И сразу пробуем запостить что-то, если есть в базе (не ждем минуту)
    asyncio.create_task(check_queue_and_post())


async def shutdown():
    logger.info("🛑 Остановка...")
    if scheduler.running:
        scheduler.shutdown()
    await bot.session.close()


async def main():
    try:
        await startup()
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Бот остановлен")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
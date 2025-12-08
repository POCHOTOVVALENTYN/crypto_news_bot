# main.py
import asyncio
import logging
import os
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
# Импортируем ИИ анализатор
from services.ai_summary import NewsAnalyzer

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
ai_analyzer = NewsAnalyzer()  # Инициализация ИИ


# 1. Функция ПАРСИНГА (Только сохраняет в БД)
async def scheduled_parsing():
    """Только собирает новости в базу, ничего не отправляет"""
    try:
        logger.info("🔍 Запуск парсера (сбор новостей)...")
        news_list = await rss_parser.get_all_news()

        new_count = 0
        for news in news_list:
            # Если новости нет в базе - добавляем
            if not await db.news_exists(news['link']):
                # Сохраняем С КАРТИНКОЙ И ТЕКСТОМ
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
            logger.info(f"💾 Добавлено в базу: {new_count} новостей")
        else:
            logger.info("💤 Новых новостей пока нет")

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга: {e}")


# 2. Функция ПУБЛИКАЦИИ (Берет из БД, обрабатывает ИИ и отправляет)
async def scheduled_posting():
    """Берет одну новость из очереди, обрабатывает и отправляет"""
    try:
        # 1. Берем одну старую новость
        news_item = await db.get_oldest_unposted_news()

        if not news_item:
            logger.info("📭 Очередь пуста, нечего публиковать")
            return

        logger.info(f"📤 Подготовка публикации: {news_item['title'][:30]}...")

        # Данные из БД
        title = news_item['title']
        summary = news_item['summary'] or ""
        source = news_item['source']
        url = news_item['url']
        image_url = news_item['image_url']

        # 2. Обработка через ИИ (Gemini)
        # Пробуем улучшить текст и убрать мусор
        ai_result = await ai_analyzer.translate_and_analyze(title, summary)

        if ai_result:
            logger.info("✨ ИИ обработал новость")
            # Если ИИ вернул результат, используем его
            title = ai_result.get("clean_title", title)
            summary = ai_result.get("clean_summary", summary)
        else:
            logger.warning("⚠️ ИИ недоступен или ошибка, публикуем как есть (с базовой очисткой)")

        # 3. Получаем рыночные данные
        prices = await get_multiple_crypto_prices()
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()

        # 4. Формируем сообщение
        formatted_msg = AdvancedMessageFormatter.format_professional_news(
            title=title,
            summary=summary,  # Тут внутри уже сработает clean_text
            source=source,
            source_url=url,
            prices=prices,
            fear_greed=fear_greed,
            image_url=image_url,
        )

        # 5. Отправляем
        rich_msg = RichMediaMessage(
            text=formatted_msg["text"],
            image_url=formatted_msg["image_url"],
        )

        success = await rich_msg.send(bot, TELEGRAM_CHANNEL_ID)

        if success:
            await db.mark_as_posted(url)
            logger.info(f"✅ Успешно опубликовано: {title[:40]}")
        else:
            logger.error("❌ Не удалось отправить сообщение в Telegram")

    except Exception as e:
        logger.error(f"❌ Ошибка в процессе публикации: {e}", exc_info=True)


async def startup():
    """Инициализация при запуске"""
    logger.info("🚀 Запуск бота...")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise ValueError("Проверьте .env: нет токена или ID канала")

    await db.init()
    logger.info("✅ БД подключена")

    # НАСТРОЙКА РАСПИСАНИЯ

    # 1. Сбор новостей каждые 10 минут
    scheduler.add_job(
        scheduled_parsing,
        IntervalTrigger(minutes=10),
        id="parsing_job",
        name="Сбор новостей в базу",
        replace_existing=True
    )

    # 2. Публикация в канал каждые 15 минут (строго по одной)
    scheduler.add_job(
        scheduled_posting,
        IntervalTrigger(minutes=15),
        id="posting_job",
        name="Публикация одной новости",
        replace_existing=True
    )

    logger.info("⏰ Расписание:")
    logger.info("   📥 Парсинг: каждые 10 мин")
    logger.info("   📤 Постинг: каждые 15 мин")

    scheduler.start()

    # Первый прогон сразу при запуске (чтобы не ждать 10 мин)
    asyncio.create_task(scheduled_parsing())


async def shutdown():
    logger.info("🛑 Остановка...")
    if scheduler.running:
        scheduler.shutdown()
    await bot.session.close()


async def main():
    try:
        await startup()
        # Бесконечный цикл, чтобы бот не закрылся
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Бот остановлен вручную")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
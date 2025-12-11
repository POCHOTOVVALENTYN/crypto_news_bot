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
    Проверяет очередь.
    ПРИОРИТЕТ 1 (Инсайд) -> Публикует МГНОВЕННО, игнорируя таймер.
    ПРИОРИТЕТ 0 (RSS)    -> Публикует только если прошел таймер (5 мин).
    """
    try:
        # 1. Сначала ищем ГОРЯЧИЕ новости (Priority = 1)
        hot_news = await db.get_hot_news()

        if hot_news:
            logger.info(f"🔥 НАЙДЕНА ВАЖНАЯ НОВОСТЬ! Пропуск таймера: {hot_news['title'][:30]}")
            news_item = hot_news
            is_hot = True
        else:
            # 2. Если горячих нет, проверяем таймер для обычных
            if not rate_limiter.can_post():
                # Логируем редко, чтобы не спамить
                if datetime.now().second < 5:
                    logger.info(f"⏳ Ждем таймер...")
                return

            # Берем обычную новость
            news_item = await db.get_oldest_unposted_news()
            is_hot = False

        if not news_item:
            return

        # ================= ПУБЛИКАЦИЯ =================
        logger.info(f"🚀 Публикация: {news_item['title'][:30]}...")

        title = news_item['title']
        summary = news_item['summary'] or ""
        source = news_item['source']
        url = news_item['url']
        image_url = news_item['image_url']

        # 3. ИИ Анализ (получаем настроение и монету для оформления)
        # Так как Listener уже перевел текст, мы просим ИИ просто дать метаданные
        # Или, если это RSS, переводим.

        ai_data = None
        if "Insider" in source:
            # Инсайд уже переведен, просто анализируем для тегов
            ai_data = await ai_analyzer.analyze_text(title + " " + summary)
        else:
            # RSS требует перевода и анализа
            ai_result = await ai_analyzer.translate_and_analyze(title, summary)
            if ai_result:
                title = ai_result.get("clean_title", title)
                summary = ai_result.get("clean_summary", summary)
                ai_data = ai_result  # тут есть coin и sentiment

        # 4. Рыночные данные
        prices = await get_multiple_crypto_prices()
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()

        # 5. Сборка
        formatted_msg = AdvancedMessageFormatter.format_professional_news(
            title=title,
            summary=summary,
            source=source,
            source_url=url,
            prices=prices,
            fear_greed=fear_greed,
            image_url=image_url,
            ai_data=ai_data  # Передаем метаданные
        )

        # 6. Отправка
        rich_msg = RichMediaMessage(
            text=formatted_msg["text"],
            image_url=formatted_msg["image_url"],
        )

        success = await rich_msg.send(bot, TELEGRAM_CHANNEL_ID)

        if success:
            await db.mark_as_posted(url)

            if is_hot:
                logger.info("⚡️ Молния отправлена вне очереди!")
                # Мы НЕ сбрасываем таймер rate_limiter.mark_posted()
                # Это позволит обычной новости выйти по своему расписанию, не задерживаясь из-за молнии
                # ИЛИ можно сбросить, чтобы не частить. Давайте сбросим для безопасности.
                rate_limiter.mark_posted()
            else:
                rate_limiter.mark_posted()
                logger.info("✅ Обычный пост отправлен.")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в постере: {e}", exc_info=True)


async def startup():
    """Инициализация при запуске"""
    logger.info("🚀 Запуск бота v6.0 (Alpha Hunter)...")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise ValueError("Ошибка конфига: нет токена или ID")

    await db.init()
    logger.info("✅ БД подключена")

    # --- ЗАПУСК USERBOT LISTENER ---
    # Запускаем прослушку каналов
    asyncio.create_task(listener.start())
    # -------------------------------

    # === РАСПИСАНИЕ (Остается прежним) ===
    # 1. Сбор новостей (Раз в 10 минут) - RSS всё равно нужен для фона
    scheduler.add_job(
        scheduled_parsing,
        IntervalTrigger(minutes=PARSING_INTERVAL_MINUTES),
        id="parsing_job",
        replace_existing=True
    )

    # 2. Проверка очереди - СДЕЛАЕМ ЧАЩЕ для быстрых новостей
    # Проверяем каждые 30 секунд, чтобы инсайды вылетали быстрее
    scheduler.add_job(
        check_queue_and_post,
        IntervalTrigger(seconds=30),
        id="queue_checker",
        replace_existing=True
    )

    logger.info(f"⏰ Парсинг RSS: каждые {PARSING_INTERVAL_MINUTES} мин")
    logger.info(f"⏰ Проверка очереди: каждые 30 сек")

    scheduler.start()

    asyncio.create_task(scheduled_parsing())
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
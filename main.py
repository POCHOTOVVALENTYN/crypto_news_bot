# main.py
import asyncio
import logging
import os
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, PARSE_INTERVAL
from database import db
from parser.rss_parser import RSSParser
from services.message_builder import (
    AdvancedMessageFormatter,
    ImageExtractor,
    RichMediaMessage,
    TelegramGIFLibrary,
    get_multiple_crypto_prices
)

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


async def send_rich_news(
        title: str,
        summary: str,
        source: str,
        source_url: str,
        entry: dict = None,
) -> bool:
    """
    Отправьте новость с максимумом деталей:
    ✅ Полный текст summary (не обрезанный)
    ✅ Фото вместе с текстом (не отдельное сообщение)
    ✅ Ссылка встроена в слово "источник"
    ✅ Цены BTC, ETH, SOL
    ✅ "Настроение рынка"
    ✅ GIF для визуализации
    """
    try:
        # ✅ Получите цены нескольких крипто (BTC, ETH, SOL)
        prices = await get_multiple_crypto_prices()

        # Определите настроение на основе заголовка
        title_lower = title.lower()
        if any(word in title_lower for word in ["surge", "pump", "rally", "взлет", "рост"]):
            sentiment = "bullish"
        elif any(word in title_lower for word in ["crash", "dump", "fall", "падение", "обвал"]):
            sentiment = "bearish"
        elif any(word in title_lower for word in ["moon", "луна"]):
            sentiment = "moon"
        else:
            sentiment = "neutral"

        # Извлеките изображение если есть
        image_url = None
        if entry and isinstance(entry, dict):
            image_url = ImageExtractor.extract_image_from_entry(entry)

        # ✅ Форматируйте сообщение (с полным текстом и несколькими ценами)
        formatted_msg = AdvancedMessageFormatter.format_professional_news(
            title=title,
            summary=summary,  # ✅ ПОЛНЫЙ текст, не обрезанный
            source=source,
            source_url=source_url,
            prices=prices,  # ✅ Несколько цен: BTC, ETH, SOL
            sentiment=sentiment,
            image_url=image_url,
        )

        # ✅ Создайте сообщение (фото отправляется ВМЕСТЕ с текстом)
        rich_msg = RichMediaMessage(
            text=formatted_msg["text"],
            image_url=formatted_msg["image_url"],
            gif_query=formatted_msg["gif_query"],
        )

        # Отправьте сообщение
        success = await rich_msg.send(bot, TELEGRAM_CHANNEL_ID)

        if success:
            logger.info(f"✅ Отправлено: {title[:50]}...")

        return success

    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        return False


async def parse_and_post_news():
    """Основной парсинг и постинг новостей"""
    try:
        logger.info("🔍 Парсинг новостей...")

        news_list = await rss_parser.get_all_news()
        logger.info(f"📊 Найдено {len(news_list)} новостей")

        for news in news_list:
            # Проверка на дубликаты
            if await db.news_exists(news['link']):
                logger.debug(f"⏭️ Уже в БД: {news['title'][:30]}...")
                continue

            # Добавьте в БД
            added = await db.add_news(
                url=news['link'],
                title=news['title'],
                source=news['source'],
                published_at=news['published']
            )

            if not added:
                continue

            logger.info(f"➕ Добавлена: {news['title'][:30]}...")

            # Отправьте в Telegram
            success = await send_rich_news(
                title=news['title'],
                summary=news['summary'],
                source=news['source'],
                source_url=news['link'],
                entry=news.get('raw_entry'),
            )

            if success:
                await db.mark_as_posted(news['link'])

            # Rate limiting
            await asyncio.sleep(2)

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга: {e}")


async def startup():
    """Инициализация при запуске"""
    logger.info("🚀 Запуск бота...")

    await db.init()
    logger.info("✅ БД инициализирована")

    try:
        me = await bot.get_me()
        logger.info(f"✅ Бот подключен: @{me.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
        raise

    logger.info("✅ Русскоязычные источники включены")
    logger.info("✅ Поддержка изображений включена (отправляется вместе с текстом)")
    logger.info("✅ Цены: BTC, ETH, SOL включены")
    logger.info("✅ Ссылка встроена в слово [источник](...)")
    logger.info("✅ GIF визуализация включена")

    scheduler.add_job(
        parse_and_post_news,
        IntervalTrigger(seconds=PARSE_INTERVAL),
        id="news_parser",
        name="Парсинг криптовалютных новостей",
        replace_existing=True
    )
    logger.info(f"⏰ Интервал проверки: {PARSE_INTERVAL}с")

    scheduler.start()


async def shutdown():
    """Очистка при остановке"""
    logger.info("🛑 Остановка бота...")
    if scheduler.running:
        scheduler.shutdown()
    await bot.session.close()
    logger.info("✅ Бот остановлен")


async def main():
    """Главная функция"""
    try:
        await startup()
        await parse_and_post_news()

        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("⌨️ Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        await shutdown()


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    logger.info("=" * 70)
    logger.info("🎯 CRYPTO NEWS TELEGRAM BOT - PROFESSIONAL V3")
    logger.info("=" * 70)
    logger.info("📸 Фото вместе с текстом: ✅")
    logger.info("💰 Цены BTC, ETH, SOL: ✅")
    logger.info("🔗 Ссылка в слове: ✅")
    logger.info("📄 Полный текст новости: ✅")
    logger.info("🎬 GIF визуализация: ✅")
    logger.info("=" * 70)

    asyncio.run(main())
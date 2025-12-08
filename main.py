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
    FearGreedIndexTracker,
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
    Отправьте новость с полными деталями:
    ✅ Полный текст summary
    ✅ Фото вместе с текстом
    ✅ Ссылка встроена в слово источника
    ✅ Цены BTC, ETH, SOL
    ✅ Индекс страха и жадности
    ✅ BLEXLER ЧАТ со ссылкой
    """
    try:
        # Получите цены криптовалют (с кэшированием)
        prices = await get_multiple_crypto_prices()

        # ✅ НОВОЕ: Получите индекс страха
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()

        # Извлеките изображение если есть
        image_url = None
        if entry and isinstance(entry, dict):
            image_url = ImageExtractor.extract_image_from_entry(entry)

        # Форматируйте сообщение
        formatted_msg = AdvancedMessageFormatter.format_professional_news(
            title=title,
            summary=summary,
            source=source,
            source_url=source_url,
            prices=prices,
            fear_greed=fear_greed,  # ✅ НОВОЕ
            image_url=image_url,
        )

        # ✅ ИСПРАВЛЕНО: Убраны GIF
        rich_msg = RichMediaMessage(
            text=formatted_msg["text"],
            image_url=formatted_msg["image_url"],
        )

        # Отправьте сообщение
        success = await rich_msg.send(bot, TELEGRAM_CHANNEL_ID)

        if success:
            logger.info(f"✅ Отправлено: {title[:50]}...")

        return success

    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}", exc_info=True)
        return False


async def parse_and_post_news():
    """Основной парсинг и постинг новостей"""
    try:
        logger.info("🔍 Парсинг новостей...")

        news_list = await rss_parser.get_all_news()
        logger.info(f"📊 Найдено {len(news_list)} релевантных новостей")

        if not news_list:
            logger.warning("⚠️ Нет новостей для публикации")
            return

        posted_count = 0

        for news in news_list:
            # ИСПРАВЛЕНИЕ: Проверяем, была ли новость ОТПРАВЛЕНА, а не просто добавлена
            if await db.news_exists(news['link']):
                if await db.is_posted(news['link']):
                    logger.debug(f"⏭️ Уже отправлено: {news['title'][:30]}...")
                    continue
                else:
                    logger.info(f"♻️ Найдена неотправленная новость: {news['title'][:30]}...")
                    # Новость есть в БД, но не отправлена. Идем дальше к отправке.
            else:
                # Если новости нет в БД, добавляем её
                added = await db.add_news(
                    url=news['link'],
                    title=news['title'],
                    source=news['source'],
                    published_at=news['published']
                )
                if not added:
                    continue
                logger.info(f"➕ Добавлена в БД: {news['title'][:50]}...")




            logger.info(f"➕ Добавлена: {news['title'][:50]}...")

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
                posted_count += 1

            # ✅ Rate limiting между постами (5 секунд)
            await asyncio.sleep(5)

        logger.info(f"✅ Опубликовано {posted_count} новостей")

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга: {e}", exc_info=True)


async def startup():
    """Инициализация при запуске"""
    logger.info("🚀 Запуск бота...")

    # ✅ Проверка .env переменных
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_token_here":
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен в .env")
        raise ValueError("TELEGRAM_BOT_TOKEN обязателен")

    if TELEGRAM_CHANNEL_ID == -100000000000:
        logger.error("❌ TELEGRAM_CHANNEL_ID не установлен в .env")
        raise ValueError("TELEGRAM_CHANNEL_ID обязателен")

    await db.init()
    logger.info("✅ БД инициализирована")

    try:
        me = await bot.get_me()
        logger.info(f"✅ Бот подключен: @{me.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
        raise

    logger.info("✅ Русскоязычные источники: Forklog, Bits.media")
    logger.info("✅ Фото вместе с текстом")
    logger.info("✅ Цены: BTC, ETH, SOL (с кэшированием)")
    logger.info("✅ Индекс страха и жадности")
    logger.info("✅ Ссылка встроена в слово источника")
    logger.info("✅ BLEXLER ЧАТ со ссылкой")

    # ✅ ИСПРАВЛЕНО: Увеличен интервал scheduler для предотвращения пропусков
    scheduler.add_job(
        parse_and_post_news,
        IntervalTrigger(seconds=PARSE_INTERVAL),
        id="news_parser",
        name="Парсинг криптовалютных новостей",
        replace_existing=True,
        max_instances=1,  # ✅ Только один экземпляр одновременно
        coalesce=True,  # ✅ Объединить пропущенные запуски
    )
    logger.info(f"⏰ Интервал проверки: {PARSE_INTERVAL}с ({PARSE_INTERVAL / 60:.0f} минут)")

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

        # ✅ Первый парсинг сразу после запуска
        await parse_and_post_news()

        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("⌨️ Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        await shutdown()


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    logger.info("=" * 80)
    logger.info("🎯 CRYPTO NEWS TELEGRAM BOT - FINAL V4")
    logger.info("=" * 80)
    logger.info("📸 Фото вместе с текстом: ✅")
    logger.info("💰 Цены BTC, ETH, SOL: ✅ (с кэшированием)")
    logger.info("🔗 Ссылка в слове: ✅")
    logger.info("📄 Полный текст новости: ✅")
    logger.info("😱 Индекс страха и жадности: ✅")
    logger.info("💬 BLEXLER ЧАТ: ✅")
    logger.info("🚫 GIF убраны: ✅")
    logger.info("🧹 Упоминания источников удалены: ✅")
    logger.info("=" * 80)

    asyncio.run(main())
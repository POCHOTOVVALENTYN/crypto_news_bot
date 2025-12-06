# main.py
import asyncio
import logging
import os
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, PARSE_INTERVAL, OPENAI_API_KEY
from database import db
from parser.rss_parser import RSSParser
from services.ai_summary import NewsAnalyzer, format_sentiment_emoji
from services.price_tracker import PriceTracker

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
rss_parser = RSSParser()
ai_analyzer = NewsAnalyzer(api_key=OPENAI_API_KEY)
price_tracker = PriceTracker()
scheduler = AsyncIOScheduler()


async def send_to_telegram(title: str, summary: str, link: str, source: str, source_link: str,
                           sentiment: str = "⚪", ai_data=None):
    """
    Отправьте новость в Telegram с красивым форматированием

    ai_data = {title_ru, summary_ru, sentiment, key_points}
    """
    try:
        # Используйте AI перевод если доступен
        if ai_data:
            title_text = ai_data.get("title_ru", title)
            summary_text = ai_data.get("summary_ru", summary)
            sentiment = format_sentiment_emoji(ai_data.get("sentiment", "Neutral"))
        else:
            title_text = title
            summary_text = summary[:150]

        # Получите текущую цену BTC
        btc_data = await price_tracker.get_bitcoin_price()
        btc_price_str = PriceTracker.format_price(btc_data)

        # Создайте сообщение с ссылкой на источник в названии
        message_text = f"""🔔 *{title_text}*

_{summary_text}_

{sentiment}

📰 *Источник:* [{source}]({source_link}){btc_price_str}
        """

        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=message_text,
            parse_mode="Markdown",
            disable_web_page_preview=False
        )

        logger.info(f"✅ Отправлено: {title_text[:50]}...")
        return True

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

            # AI обработка (перевод + анализ)
            ai_data = None
            if ai_analyzer.client:
                ai_data = await ai_analyzer.translate_and_analyze(
                    news['title'],
                    news['summary']
                )

            # Отправьте в Telegram
            success = await send_to_telegram(
                title=news['title'],
                summary=news['summary'],
                link=news['link'],
                source=news['source'],
                source_link=news['link'],  # Используйте ссылку источника для клика
                sentiment="⚪",
                ai_data=ai_data
            )

            if success:
                await db.mark_as_posted(news['link'])

            # Rate limiting
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга: {e}")


async def startup():
    """Инициализация при запуске"""
    logger.info("🚀 Запуск бота...")

    # Инициализируйте БД
    await db.init()
    logger.info("✅ БД инициализирована")

    # Проверьте Telegram подключение
    try:
        me = await bot.get_me()
        logger.info(f"✅ Бот подключен: @{me.username}")
    except Exception as e:
        logger.error(f"❌ Ошибка Telegram: {e}")
        raise

    # Проверьте OpenAI подключение
    if ai_analyzer.client:
        logger.info("✅ OpenAI подключен (AI переводы включены)")
    else:
        logger.warning("⚠️ OpenAI не подключен (используются оригинальные тексты)")

    # Запланируйте парсинг
    scheduler.add_job(
        parse_and_post_news,
        IntervalTrigger(seconds=PARSE_INTERVAL),
        id="news_parser",
        name="Парсинг криптовалютных новостей",
        replace_existing=True
    )
    logger.info(f"⏰ Интервал парсинга: {PARSE_INTERVAL}с")

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

        # Первый парсинг сразу при запуске
        await parse_and_post_news()

        # Держите бота в живых
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
    logger.info("🎯 CRYPTO NEWS TELEGRAM BOT - REFACTORED")
    logger.info("=" * 70)

    asyncio.run(main())
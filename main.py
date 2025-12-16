# main.py
import asyncio
import logging
import sys
from pathlib import Path
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Импорт нового конфига
from config import config
from database import db
from parser.rss_parser import RSSParser
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

# === НОВОЕ: Система обработки ошибок ===
from utils.error_handling import safe_task, alert_manager, critical_error_handler

# Создаем папку для логов
Path("logs").mkdir(exist_ok=True)

# Логирование
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=config.telegram_bot_token)
dp = Dispatcher()
router = Router()
rss_parser = RSSParser(use_russian=True)
scheduler = AsyncIOScheduler()
ai_analyzer = NewsAnalyzer()
rate_limiter = RateLimiter(min_interval_seconds=300)

# === НАСТРОЙКА ALERT MANAGER ===
alert_manager.bot = bot
alert_manager.admin_id = config.admin_id


# === КОМАНДЫ БОТА ===
@router.message(Command("stats"))
async def cmd_stats(message):
    """Статистика бота"""
    try:
        total = await db.execute("SELECT COUNT(*) FROM news")
        posted = await db.execute("SELECT COUNT(*) FROM news WHERE posted_to_telegram=1")

        await message.answer(
            f"📊 <b>Статистика:</b>\n"
            f"Всего новостей: {total}\n"
            f"Опубликовано: {posted}\n"
            f"В очереди: {total - posted}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка stats: {e}")
        await message.answer("⚠️ Ошибка получения статистики")


@router.message(Command("sources"))
async def cmd_sources(message):
    """Список источников"""
    try:
        rows = await db.execute(
            "SELECT source, COUNT(*) as cnt FROM news GROUP BY source "
            "ORDER BY cnt DESC LIMIT 10"
        )
        text = "📡 <b>Топ источников:</b>\n\n"
        for source, count in rows:
            text += f"▪️ {source}: {count}\n"

        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка sources: {e}")
        await message.answer("⚠️ Ошибка получения источников")


@router.message(Command("health"))
async def cmd_health(message):
    """Проверка здоровья бота"""
    try:
        # Проверяем БД
        total = await db.execute("SELECT COUNT(*) FROM news")

        # Проверяем Userbot
        userbot_status = "✅ Активен" if listener.is_running else "❌ Неактивен"

        # Проверяем Rate Limiter
        can_post = "✅ Готов" if rate_limiter.can_post() else f"⏳ Ждем {rate_limiter.get_wait_time()}с"

        await message.answer(
            f"🏥 <b>Состояние бота:</b>\n\n"
            f"БД: ✅ {total} записей\n"
            f"Userbot: {userbot_status}\n"
            f"Rate Limiter: {can_post}\n"
            f"Scheduler: ✅ Запущен ({len(scheduler.get_jobs())} задач)",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка health: {e}")
        await message.answer("⚠️ Ошибка проверки здоровья")


dp.include_router(router)


# === ЗАДАЧИ ПЛАНИРОВЩИКА (С ЗАЩИТОЙ) ===
@safe_task("RSS Parsing")
async def scheduled_parsing():
    """Сбор новостей (защищено декоратором)"""
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

    if count > 0:
        logger.info(f"📥 Добавлено {count} новостей")


@safe_task("Queue Poster")
async def check_queue_and_post():
    """Проверка очереди и публикация (защищено декоратором)"""
    # 1. Горячие новости
    hot_news = await db.get_hot_news()
    is_hot = False

    if hot_news:
        news_item = hot_news
        is_hot = True
        logger.info("🔥 Молния! Публикую вне очереди.")
    else:
        # 2. Обычная очередь
        if not rate_limiter.can_post():
            return
        news_item = await db.get_oldest_unposted_news()

    if not news_item:
        return

    # Публикация
    logger.info(f"🚀 Публикация: {news_item['title'][:30]}")

    # Подготовка данных
    ai_data = None
    if "Insider" in news_item['source']:
        ai_data = await ai_analyzer.analyze_text(
            news_item['title'] + " " + news_item['summary']
        )
    else:
        ai_result = await ai_analyzer.translate_and_analyze(
            news_item['title'],
            news_item['summary']
        )
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
    if await rich_msg.send(bot, config.telegram_channel_id):
        await db.mark_as_posted(news_item['url'])
        if not is_hot:
            rate_limiter.mark_posted()


# === МОНИТОРИНГ ЗДОРОВЬЯ ===
@safe_task("Health Monitor")
async def monitor_health():
    """Проверка состояния бота каждые 10 минут"""
    from datetime import datetime, timedelta

    # Проверяем давность последнего поста
    if rate_limiter.last_post_time:
        delta = datetime.now() - rate_limiter.last_post_time
        if delta > timedelta(hours=2):
            await alert_manager.send_alert(
                f"Бот не публиковал новости {delta.total_seconds() / 3600:.1f} часов!\n"
                f"Последний пост: {rate_limiter.last_post_time}",
                level="WARNING"
            )

    # Проверяем статус Userbot
    if config.tg_api_id and not listener.is_running:
        await alert_manager.send_alert(
            "Userbot не запущен, хотя TG_API_ID настроен!",
            level="ERROR"
        )


# === ГЛАВНАЯ ФУНКЦИЯ ===
async def main():
    """Главная функция с глобальной обработкой ошибок"""
    try:
        logger.info("=" * 60)
        logger.info("🚀 CRYPTO NEWS BOT - ЗАПУСК")
        logger.info("=" * 60)

        # 1. Инициализация БД
        logger.info("📦 Инициализация базы данных...")
        try:
            await db.init()
            logger.info("✅ БД подключена")
        except Exception as e:
            await critical_error_handler("Не удалось инициализировать БД", e)
            raise

        # 2. Запуск Userbot
        if config.tg_api_id and config.tg_api_hash:
            logger.info("🎧 Запуск Telegram Userbot...")
            asyncio.create_task(listener.start())
        else:
            logger.warning("⚠️ Userbot отключен (нет TG_API_ID/TG_API_HASH)")

        # 3. Настройка планировщика
        logger.info("⏰ Настройка планировщика задач...")
        scheduler.add_job(
            scheduled_parsing,
            IntervalTrigger(minutes=10),
            id="rss_parsing",
            name="RSS Parsing"
        )
        scheduler.add_job(
            check_queue_and_post,
            IntervalTrigger(seconds=30),
            id="queue_poster",
            name="Queue Poster"
        )
        scheduler.add_job(
            monitor_health,
            IntervalTrigger(minutes=10),
            id="health_monitor",
            name="Health Monitor"
        )
        scheduler.start()
        logger.info("✅ Планировщик запущен")

        # 4. Первый прогон задач
        logger.info("🔄 Запуск начальных задач...")
        asyncio.create_task(scheduled_parsing())
        asyncio.create_task(check_queue_and_post())

        # 5. Отправляем уведомление админу о старте
        if config.admin_id:
            await alert_manager.send_alert(
                f"Бот успешно запущен!\n"
                f"Userbot: {'✅ Активен' if listener.is_running else '❌ Отключен'}\n"
                f"Задач в планировщике: {len(scheduler.get_jobs())}",
                level="INFO"
            )

        # 6. Запуск Polling (блокирует выполнение)
        logger.info("🤖 Запуск Telegram Bot (Long Polling)...")
        logger.info("=" * 60)
        await dp.start_polling(bot)

    except KeyboardInterrupt:
        logger.info("\n🛑 Получен сигнал остановки (Ctrl+C)")

    except Exception as e:
        await critical_error_handler("Критическая ошибка в main()", e)
        sys.exit(1)

    finally:
        logger.info("🧹 Очистка ресурсов...")

        # Остановка планировщика
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("✅ Планировщик остановлен")

        # Остановка Userbot
        if listener.is_running:
            await listener.stop()

        # Закрытие бота
        await bot.session.close()
        logger.info("✅ Bot session закрыт")

        logger.info("=" * 60)
        logger.info("👋 БОТ ОСТАНОВЛЕН")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Завершение по Ctrl+C")
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {e}", exc_info=True)
        sys.exit(1)
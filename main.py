# main.py
import asyncio
import logging
import sys
import warnings
from pathlib import Path

# Подавляем Pydantic warnings о shadowing attributes
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic._internal._fields")
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
from services.translator import translator

# === НОВОЕ: Система обработки ошибок ===
from utils.error_handling import safe_task, alert_manager, critical_error_handler
from services.priority_calculator import PriorityCalculator
from utils.news_validator import NewsValidator

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

# ДОБАВЬТЕ ПРОВЕРКУ:
if not config.admin_id:
    logger.warning("⚠️ ADMIN_ID не установлен - алерты будут только в логах!")
else:
    logger.info(f"✅ AlertManager настроен (Admin ID: {config.admin_id})")





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
    """Сбор новостей с предварительным анализом и валидацией"""
    logger.info("🔍 Парсер: ищу свежие новости...")
    news_list = await rss_parser.get_all_news()
    count = 0
    high_priority_count = 0
    filtered_count = 0

    fresh_count = 0
    duplicate_count = 0
    validation_failed_count = 0
    priority_zero_count = 0
    
    for news in news_list:
        # Валидация
        is_valid, error = NewsValidator.validate_news_item(news)
        if not is_valid:
            validation_failed_count += 1
            logger.debug(f"❌ Новость не прошла валидацию: {error}")
            filtered_count += 1
            continue
        
        # Проверка свежести (новости не старше 24 часов)
        if not NewsValidator.is_today_news(news):
            fresh_count += 1
            filtered_count += 1
            continue
        
        # Проверка дубликатов
        if await db.news_exists(news['link']):
            duplicate_count += 1
            continue
        
        # Расчет приоритета БЕЗ AI (быстро, без запросов к API)
        # AI анализ будет выполняться только при публикации для перевода и улучшения
        priority = PriorityCalculator.calculate_priority(news, None)
        
        # Фильтруем только нулевой приоритет (совсем нерелевантные новости)
        # Priority используется для сортировки, а не для жесткой фильтрации
        if priority == 0:
            priority_zero_count += 1
            logger.debug(f"⏭️ Пропуск нулевой приоритет (priority={priority}): {news['title'][:50]}")
            filtered_count += 1
            continue
        
        # Сохраняем
        success = await db.add_news(
            url=news['link'],
            title=news['title'],
            summary=news.get('summary', ''),
            source=news['source'],
            published_at=news['published'],
            image_url=news.get('image_url'),
            priority=priority,
            full_content=news.get('full_content', '')  # ✅ НОВОЕ: Сохраняем полный текст
        )
        
        if success:
            count += 1
            if priority >= 6:
                high_priority_count += 1
                logger.info(f"🔥 Высокоприоритетная (priority={priority}): {news['title'][:50]}")

    logger.info(f"📥 RSS: найдено {len(news_list)}, добавлено {count} ({high_priority_count} высокоприоритетных), "
                f"отфильтровано {filtered_count} (дубликаты: {duplicate_count}, старые: {fresh_count}, "
                f"валидация: {validation_failed_count}, приоритет 0: {priority_zero_count})")


@safe_task("Queue Poster", timeout_seconds=300)  # ✅ ИСПРАВЛЕНО: Таймаут 5 минут для предотвращения зависаний
async def check_queue_and_post():
    """Проверка очереди и публикация (защищено декоратором)"""
    # 1. Горячие новости (приоритет >= 6)
    hot_news = await db.get_hot_news(min_priority=6)
    is_hot = False

    if hot_news:
        news_item = hot_news
        is_hot = True
        priority = news_item.get('priority', 0)
        logger.info(f"🔥 Молния! Публикую вне очереди (priority={priority}).")
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
    technical_analysis = None
    
    # ✅ НОВОЕ: Получаем полный текст статьи (приоритет: full_content > summary)
    full_content = news_item.get('full_content') or news_item.get('summary', '')
    
    # ✅ НОВОЕ: Создаем выжимку из полного текста (для экономии токенов ИИ)
    from services.content_summarizer import ContentSummarizer
    
    # Если текст длинный (>1000 символов), создаем выжимку для ИИ
    text_for_ai = full_content
    if len(full_content) > 1000:
        summary_for_ai = ContentSummarizer.create_extractive_summary(full_content, sentences_count=5)
        if summary_for_ai and len(summary_for_ai) > 200:
            text_for_ai = summary_for_ai
            logger.debug(f"✅ Создана выжимка для ИИ: {len(full_content)} → {len(summary_for_ai)} символов")
    
    # Шаг 1: Перевод (если нужен) через Google Translate (быстро и дешево)
    translated_data = None
    try:
        translated_data = await translator.translate_news(
            news_item['title'],
            text_for_ai  # ✅ Используем выжимку для перевода
        )
        if translated_data:
            # Используем переведенные данные
            news_item['title'] = translated_data.get('ru_title', news_item['title'])
            # Для публикации используем полный контент, но переводим выжимку
            if 'ru_summary' in translated_data:
                # Обновляем full_content если была переведена выжимка
                # (в реальности лучше переводить полный текст, но для экономии токенов используем выжимку)
                pass
            logger.debug(f"✅ Новость переведена через Google Translate")
    except Exception as e:
        logger.debug(f"⚠️ Ошибка перевода через Google Translate: {e}")
    
    # Шаг 2: AI анализ (sentiment, coin, importance) - только если нужен
    # Smart Filtering: Проверяем нужен ли AI анализ
    needs_ai = PriorityCalculator.needs_ai_processing(news_item)
    
    if needs_ai:
        try:
            if "Insider" in news_item['source']:
                # Для Insider новостей - полный AI анализ
                ai_data = await ai_analyzer.analyze_text(
                    news_item['title'] + " " + text_for_ai  # ✅ Используем выжимку
                )
                if not ai_data:
                    logger.warning(f"⚠️ AI анализ вернул None для Insider новости: {news_item['title'][:50]}")
            else:
                # Для обычных новостей - только анализ (без перевода, он уже сделан через Google Translate)
                # Используем analyze_text для получения sentiment, coin, importance
                ai_data = await ai_analyzer.analyze_text(
                    news_item['title'] + " " + text_for_ai  # ✅ Используем выжимку (экономия токенов!)
                )
                if not ai_data:
                    logger.debug(f"ℹ️ AI анализ не выполнен для: {news_item['title'][:50]}")
        except Exception as e:
            logger.error(f"❌ Ошибка AI обработки: {e}", exc_info=True)
            # Продолжаем публикацию с переведенными/оригинальными данными
    else:
        logger.info(f"⏭️ Smart Filtering: пропуск AI обработки для новости: {news_item['title'][:50]}")
    
    # ✅ НОВОЕ: Извлекаем ключевые моменты для bullet points
    key_points = ContentSummarizer.extract_key_points(full_content, points_count=3) if full_content else []
    
    # ✅ ИСПРАВЛЕНО: Переводим key_points если новость была переведена
    if translated_data and key_points:
        logger.debug(f"🔄 Перевожу ключевые моменты ({len(key_points)} пунктов)...")
        translated_points = []
        import asyncio
        loop = asyncio.get_event_loop()
        for point in key_points:
            try:
                # translate_text - синхронный метод, оборачиваем в executor
                translated_point = await loop.run_in_executor(
                    None, translator.translate_text, point, 'auto', 'ru'
                )
                if translated_point:
                    translated_points.append(translated_point)
                else:
                    translated_points.append(point)  # Fallback на оригинал
            except Exception as e:
                logger.debug(f"⚠️ Ошибка перевода ключевого момента: {e}")
                translated_points.append(point)  # Fallback на оригинал
        key_points = translated_points
        logger.debug(f"✅ Ключевые моменты переведены")
    
    # Получаем технический анализ если есть информация о монете
    coin_from_ai = ai_data.get('coin') if ai_data else None
    if coin_from_ai and coin_from_ai != 'Market':
        try:
            from services.technical_analysis import TechnicalAnalysis
            technical_analysis = await TechnicalAnalysis.get_technical_analysis(coin_from_ai)
        except Exception as e:
            logger.debug(f"⚠️ Ошибка получения тех. анализа для {coin_from_ai}: {e}")
            technical_analysis = None

    # Получение цен и индекса с обработкой ошибок
    try:
        prices = await get_multiple_crypto_prices()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка получения цен: {e}")
        prices = None

    try:
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()
    except Exception as e:
        logger.warning(f"⚠️ Ошибка получения индекса страха: {e}")
        fear_greed = None

    msg_data = AdvancedMessageFormatter.format_professional_news(
        title=news_item['title'],
        summary=news_item.get('summary', ''),
        source=news_item['source'],
        source_url=news_item['url'],
        prices=prices,
        fear_greed=fear_greed,
        image_url=news_item.get('image_url'),
        ai_data=ai_data,
        technical_analysis=technical_analysis,
        key_points=key_points,  # ✅ НОВОЕ: Ключевые моменты для bullet points
        full_content=full_content  # ✅ НОВОЕ: Полный текст для fallback
    )

    # ✅ НОВОЕ: Создаем inline-кнопки
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    keyboard_builder = InlineKeyboardBuilder()
    keyboard_builder.button(text="💬 Открытый общий чат", url="https://t.me/+514GO2tFjAtkMWRi")
    keyboard_builder.button(text="📢 Подписаться", url="https://t.me/blexler_invest")
    keyboard_builder.adjust(1)  # Кнопки в одну колонку
    inline_keyboard = keyboard_builder.as_markup()
    
    rich_msg = RichMediaMessage(msg_data['text'], msg_data['image_url'], reply_markup=inline_keyboard)
    if await rich_msg.send(bot, config.telegram_channel_id):
        await db.mark_as_posted(news_item['url'])
        rate_limiter.mark_posted()  # Обновляем для всех постов
        if is_hot:
            logger.info("🔥 Молния опубликована вне очереди")


# === БЕЗОПАСНЫЙ ЗАПУСК LISTENER ===
async def safe_start_listener():
    """Безопасный запуск listener с обработкой ошибок"""
    try:
        await listener.start()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка запуска Userbot: {e}", exc_info=True)
        if alert_manager.bot and alert_manager.admin_id:
            try:
                await alert_manager.send_alert(
                    f"Не удалось запустить Userbot: {str(e)[:200]}",
                    level="ERROR"
                )
            except Exception as alert_error:
                logger.error(f"❌ Не удалось отправить алерт: {alert_error}")


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
    background_tasks = []  # Отслеживаем фоновые задачи для правильного cleanup
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
            # Ожидаем завершения запуска для правильной проверки статуса
            await safe_start_listener()
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
            IntervalTrigger(seconds=60),  # Увеличено до 60 секунд для снижения нагрузки
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

        # Отменяем фоновые задачи
        if background_tasks:
            for task in background_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

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
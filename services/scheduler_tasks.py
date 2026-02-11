import logging
import asyncio
from datetime import datetime, timedelta

from loader import bot
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
from utils.error_handling import safe_task, alert_manager
from services.priority_calculator import PriorityCalculator
from utils.news_validator import NewsValidator
from services.content_summarizer import ContentSummarizer
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)

# Инициализация сервисов
rss_parser = RSSParser(use_russian=True)
ai_analyzer = NewsAnalyzer()
rate_limiter = RateLimiter(min_interval_seconds=300)

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


@safe_task("Queue Poster", timeout_seconds=300)
async def check_queue_and_post():
    """
    ⚠️ УСТАРЕВШАЯ ФУНКЦИЯ - НЕ ИСПОЛЬЗУЕТСЯ
    Заменена на систему 3-часовых дайджестов и модерацию breaking news.
    Оставлено для обратной совместимости.
    """
    # ⚠️ ФУНКЦИЯ ОТКЛЮЧЕНА - используется новая система дайджестов
    return
    
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
                pass
            logger.debug(f"✅ Новость переведена через Google Translate")
    except Exception as e:
        logger.debug(f"⚠️ Ошибка перевода через Google Translate: {e}")
    
    # Шаг 2: AI анализ (coin, importance)
    needs_ai = PriorityCalculator.needs_ai_processing(news_item)
    
    if needs_ai:
        try:
            if "Insider" in news_item['source']:
                # Для Insider новостей - полный AI анализ
                ai_data = await ai_analyzer.analyze_text(
                    news_item['title'] + " " + text_for_ai
                )
                if not ai_data:
                    logger.warning(f"⚠️ AI анализ вернул None для Insider новости: {news_item['title'][:50]}")
            else:
                # Для обычных новостей - только анализ
                ai_data = await ai_analyzer.analyze_text(
                    news_item['title'] + " " + text_for_ai
                )
                if not ai_data:
                    logger.debug(f"ℹ️ AI анализ не выполнен для: {news_item['title'][:50]}")
        except Exception as e:
            logger.error(f"❌ Ошибка AI обработки: {e}", exc_info=True)
    else:
        logger.info(f"⏭️ Smart Filtering: пропуск AI обработки для новости: {news_item['title'][:50]}")
    
    # ✅ НОВОЕ: Извлекаем ключевые моменты для bullet points
    key_points = ContentSummarizer.extract_key_points(full_content, points_count=3) if full_content else []
    
    # ✅ ИСПРАВЛЕНО: Переводим key_points НЕЗАВИСИМО от перевода основной новости
    if key_points:
        logger.debug(f"🔄 Проверка языка ключевых моментов ({len(key_points)} пунктов)...")
        translated_points = []
        loop = asyncio.get_event_loop()
        
        for point in key_points:
            try:
                # 1. Определяем язык пункта
                detected_lang = await loop.run_in_executor(None, translator.detect_language, point)
                
                # 2. Если не русский - переводим
                if detected_lang != 'ru':
                    translated_point = await loop.run_in_executor(
                        None, translator.translate_text, point, detected_lang or 'auto', 'ru'
                    )
                    if translated_point:
                        translated_points.append(translated_point)
                    else:
                        translated_points.append(point)
                else:
                    translated_points.append(point)
                    
            except Exception as e:
                logger.debug(f"⚠️ Ошибка перевода ключевого момента: {e}")
                translated_points.append(point)
                
        key_points = translated_points
        logger.debug(f"✅ Обработка ключевых моментов завершена")
    
    # Получаем технический анализ
    coin_from_ai = ai_data.get('coin') if ai_data else None
    if coin_from_ai and coin_from_ai != 'Market':
        try:
            from services.technical_analysis import TechnicalAnalysis
            technical_analysis = await TechnicalAnalysis.get_technical_analysis(coin_from_ai)
        except Exception as e:
            logger.debug(f"⚠️ Ошибка получения тех. анализа для {coin_from_ai}: {e}")
            technical_analysis = None

    # Получение цен и индекса
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

    # Получаем шаблон футера
    footer_template = await db.get_setting("footer_template")

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
        key_points=key_points,
        full_content=full_content,
        footer_template=footer_template
    )

    # Inline-кнопки
    keyboard_builder = InlineKeyboardBuilder()
    keyboard_builder.button(text="💬 Открытый общий чат", url="https://t.me/+514GO2tFjAtkMWRi")
    keyboard_builder.button(text="📢 Подписаться", url="https://t.me/blexler_invest")
    keyboard_builder.adjust(1)
    inline_keyboard = keyboard_builder.as_markup()
    
    rich_msg = RichMediaMessage(msg_data['text'], msg_data['image_url'], reply_markup=inline_keyboard)
    sent_message = await rich_msg.send(bot, config.telegram_channel_id)
    
    if sent_message:
        # ✅ НОВОЕ: Сохраняем ID сообщения для внутренних ссылок
        message_id = sent_message.message_id
        await db.mark_as_posted(news_item['url'], message_id=message_id)
        
        rate_limiter.mark_posted()
        if is_hot:
            logger.info(f"🔥 Молния опубликована вне очереди (MsgID: {message_id})")


@safe_task("Daily Digest")
async def daily_digest_task():
    """Ежедневный дайджест (за 24 часа)"""
    logger.info("📅 Запуск генерации ежедневного дайджеста...")
    news_list = await db.get_news_for_period(hours=24, min_priority=5) # Только важные
    
    logger.info(f"📊 Найдены новости для Daily Digest: {len(news_list)}")
    
    if len(news_list) < 3:
        logger.info("⚠️ Мало важных новостей для дайджеста (<3), пропускаем.")
        return

    digest_html = await ai_analyzer.generate_digest(news_list, period_name="сутки")
    
    if digest_html:
        try:
            # Получаем шаблон футера
            footer = await db.get_setting("footer_template", "")
            if footer:
                digest_html += f"\n\n{footer}"
            
            # ✅ НОВОЕ: Кнопки для дайджеста
            keyboard_builder = InlineKeyboardBuilder()
            keyboard_builder.button(text="💬 Открытый общий чат", url="https://t.me/+514GO2tFjAtkMWRi")
            keyboard_builder.button(text="📢 Подписаться", url="https://t.me/blexler_invest")
            keyboard_builder.adjust(1)
            
            await bot.send_message(
                chat_id=config.telegram_channel_id,
                text=digest_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard_builder.as_markup()
            )
            logger.info("✅ Ежедневный дайджест опубликован")
        except Exception as e:
            logger.error(f"❌ Ошибка публикации дайджеста: {e}")


@safe_task("Weekly Digest")
async def weekly_digest_task():
    """Еженедельный дайджест (за 7 дней)"""
    logger.info("📅 Запуск генерации недельного дайджеста...")
    news_list = await db.get_news_for_period(hours=24*7, min_priority=6) # Только очень важные
    
    logger.info(f"📊 Найдены новости для Weekly Digest: {len(news_list)}")
    
    if len(news_list) < 5:
        logger.info("⚠️ Мало важных новостей для недельного дайджеста (<5), пропускаем.")
        return

    digest_html = await ai_analyzer.generate_digest(news_list, period_name="неделю")
    
    if digest_html:
        try:
             # Получаем шаблон футера
            footer = await db.get_setting("footer_template", "")
            if footer:
                digest_html += f"\n\n{footer}"
                
            # ✅ НОВОЕ: Кнопки для дайджеста
            keyboard_builder = InlineKeyboardBuilder()
            keyboard_builder.button(text="💬 Открытый общий чат", url="https://t.me/+514GO2tFjAtkMWRi")
            keyboard_builder.button(text="📢 Подписаться", url="https://t.me/blexler_invest")
            keyboard_builder.adjust(1)
            
            await bot.send_message(
                chat_id=config.telegram_channel_id,
                text=digest_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard_builder.as_markup()
            )
            logger.info("✅ Недельный дайджест опубликован")
        except Exception as e:
            logger.error(f"❌ Ошибка публикации дайджеста: {e}")


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

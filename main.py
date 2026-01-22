# main.py
import asyncio
import logging
import sys
import warnings
from pathlib import Path

# Подавляем Pydantic warnings о shadowing attributes
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic._internal._fields")

from aiogram import Router
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Импорт конфигурации и загрузчика
from config import config
from loader import bot, dp
from database import db

from services.telegram_listener import listener
from services.rate_limiter import RateLimiter

# === НОВОЕ: Система обработки ошибок ===
from utils.error_handling import alert_manager, critical_error_handler

# === НОВОЕ: Сервисный слой задач ===
from services.scheduler_tasks import (
    scheduled_parsing,
    check_queue_and_post,
    monitor_health,
    safe_start_listener,
    rate_limiter as tasks_rate_limiter  # Импортируем rate_limiter из tasks чтобы использовать его в health check
)

# Создаем папку для логов
Path("logs").mkdir(exist_ok=True)

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/bot.log') # Changed from 'bot.log' to 'logs/bot.log' to match original intent
    ]
)

# 📝 ОТДЕЛЬНЫЙ ЛОГГЕР ДЛЯ ПЛАТЕЖЕЙ (для аудита и безопасности)
payment_logger = logging.getLogger("payments")
payment_handler = logging.FileHandler("logs/payments.log")
payment_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
)
payment_logger.addHandler(payment_handler)
payment_logger.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Инициализация
router = Router()
scheduler = AsyncIOScheduler()

# === НАСТРОЙКА ALERT MANAGER ===
alert_manager.bot = bot
alert_manager.admin_id = config.admin_id

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

        # Проверяем Rate Limiter (берем из scheduler_tasks)
        can_post = "✅ Готов" if tasks_rate_limiter.can_post() else f"⏳ Ждем {tasks_rate_limiter.get_wait_time()}с"

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




# Импорт роутеров
from handlers import admin_menu, user_start, user_menu, payments, ai_chat, gamification, admin_dashboard

# Импорт middleware
from middlewares.subscription_check import SubscriptionCheckMiddleware

# 🔒 Регистрация middleware (автоматическая проверка подписок)
dp.message.middleware(SubscriptionCheckMiddleware())
logger.info("✅ Subscription check middleware зарегистрирован")

# Регистрация роутеров (порядок важен!)
dp.include_router(admin_menu.router)       # Админ-команды (высший приоритет)
dp.include_router(admin_dashboard.router)  # Админ-dashboard
dp.include_router(user_start.router)       # /start, /help
dp.include_router(payments.router)         # Платежи и воронка продаж
dp.include_router(ai_chat.router)          # AI-чат (с FSM states)
dp.include_router(gamification.router)     # Геймификация (лидерборд, XP)
dp.include_router(user_menu.router)        # Кнопки меню
dp.include_router(router)                  # Общие команды (stats, sources, health)



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
            if config.admin_id:
                await alert_manager.send_alert(
                    f"Не удалось инициализировать БД: {e}",
                    level="CRITICAL"
                )
            logger.critical(f"Не удалось инициализировать БД: {e}", exc_info=True)
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
            IntervalTrigger(seconds=60),
            id="queue_poster",
            name="Queue Poster"
        )
        scheduler.add_job(
            monitor_health,
            IntervalTrigger(minutes=10),
            id="health_monitor",
            name="Health Monitor"
        )
        
        # Задачи дайджестов (Cron)
        from apscheduler.triggers.cron import CronTrigger
        
        # Ежедневный дайджест в 21:00
        from services.scheduler_tasks import daily_digest_task, weekly_digest_task
        
        scheduler.add_job(
            daily_digest_task,
            CronTrigger(hour=21, minute=0),
            id="daily_digest",
            name="Daily Digest"
        )
        
        # Еженедельный дайджест в Воскресенье 22:00
        scheduler.add_job(
            weekly_digest_task,
            CronTrigger(day_of_week='sun', hour=22, minute=0),
            id="weekly_digest",
            name="Weekly Digest"
        )
        
        # Проверка истекающих подписок каждый день в 10:00
        from services.subscription_notifier import check_expiring_subscriptions
        scheduler.add_job(
            check_expiring_subscriptions,
            CronTrigger(hour=10, minute=0),
            id="subscription_check",
            name="Subscription Expiry Check"
        )
        
        # Авто-дожим продаж каждый час
        from services.sales_followup import check_abandoned_purchases
        scheduler.add_job(
            check_abandoned_purchases,
            IntervalTrigger(hours=1),
            id="sales_followup",
            name="Sales Follow-up"
        )
        logger.info("✅ Авто-дожим настроен")
        
        # Личный планировщик в 8:00
        from services.personal_assistant import personal_assistant
        
        async def send_daily_plan():
            try:
                plan = await personal_assistant.generate_daily_plan()
                await bot.send_message(config.admin_id, f"📋 <b>План на день</b>\n\n{plan}", parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка плана: {e}")
        
        scheduler.add_job(send_daily_plan, CronTrigger(hour=8, minute=0), id="daily_plan", name="Daily Plan")
        logger.info("✅ Планировщик настроен")
        
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
        if config.admin_id:
            await alert_manager.send_alert(
                f"Критическая ошибка в main(): {e}",
                level="CRITICAL"
            )
            logger.critical(f"Критическая ошибка в main(): {e}", exc_info=True)
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

        # Закрытие БД
        await db.close()

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
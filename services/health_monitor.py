# services/health_monitor.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from database import db
from utils.error_handling import alert_manager

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Расширенный мониторинг здоровья бота.

    Отслеживает:
    - Давность последнего поста
    - Количество ошибок
    - Статус БД
    - Статус Userbot
    """

    def __init__(self):
        self.last_post_time: Optional[datetime] = None
        self.error_count = 0
        self.max_errors_before_alert = 10
        self.last_db_check: Optional[datetime] = None
        self.is_running = False

    def update_last_post_time(self):
        """Обновляет время последнего поста"""
        self.last_post_time = datetime.now()
        logger.debug(f"⏱️ Последний пост: {self.last_post_time}")

    def increment_error(self):
        """Увеличивает счетчик ошибок"""
        self.error_count += 1
        logger.warning(f"⚠️ Счетчик ошибок: {self.error_count}")

    def reset_error_count(self):
        """Сбрасывает счетчик ошибок"""
        if self.error_count > 0:
            logger.info(f"✅ Сброс счетчика ошибок (было: {self.error_count})")
            self.error_count = 0

    async def check_posting_activity(self) -> bool:
        """
        Проверяет давность последнего поста.

        Returns:
            True если всё нормально, False если давно не было постов
        """
        if not self.last_post_time:
            # Первый запуск - проверяем БД
            try:
                last_posted = await db.execute(
                    "SELECT MAX(added_at) FROM news WHERE posted_to_telegram = 1"
                )
                if last_posted and last_posted[0][0]:
                    # TODO: конвертировать timestamp из БД в datetime
                    logger.info("📅 Бот ранее публиковал новости")
            except Exception as e:
                logger.error(f"❌ Ошибка проверки истории постов: {e}")
            return True

        # Проверяем давность
        delta = datetime.now() - self.last_post_time
        hours_since_last = delta.total_seconds() / 3600

        if hours_since_last > 2:
            await alert_manager.send_alert(
                f"⏰ БОТ НЕ ПУБЛИКОВАЛ {hours_since_last:.1f} ЧАСОВ\n"
                f"Последний пост: {self.last_post_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Возможные причины:\n"
                f"• Нет новых новостей в очереди\n"
                f"• Проблемы с RSS источниками\n"
                f"• Ошибки в AI обработке",
                level="WARNING"
            )
            return False

        return True

    async def check_database_health(self) -> bool:
        """
        Проверяет доступность БД.

        Returns:
            True если БД доступна, False если проблемы
        """
        try:
            # Простой запрос для проверки
            count = await db.execute("SELECT COUNT(*) FROM news")
            self.last_db_check = datetime.now()
            logger.debug(f"✅ БД здорова ({count} записей)")
            return True

        except Exception as e:
            await alert_manager.send_alert(
                f"🗄️ КРИТИЧЕСКАЯ ОШИБКА БД\n"
                f"Ошибка: {type(e).__name__}: {e}\n\n"
                f"БД может быть повреждена или заблокирована!",
                level="CRITICAL"
            )
            return False

    async def check_error_threshold(self) -> bool:
        """
        Проверяет превышение порога ошибок.

        Returns:
            True если порог превышен, False если всё нормально
        """
        if self.error_count >= self.max_errors_before_alert:
            await alert_manager.send_alert(
                f"🚨 МНОГО ОШИБОК: {self.error_count}\n\n"
                f"Бот испытывает проблемы со стабильностью!\n"
                f"Проверьте логи: tail -100 logs/bot.log",
                level="CRITICAL"
            )
            # Сбрасываем после отправки алерта
            self.reset_error_count()
            return True

        return False

    async def run_full_check(self):
        """Полная проверка здоровья (вызывается периодически)"""
        logger.info("🏥 Запуск проверки здоровья бота...")

        checks = {
            "Активность постинга": await self.check_posting_activity(),
            "База данных": await self.check_database_health(),
            "Порог ошибок": not await self.check_error_threshold()
        }

        # Логируем результаты
        for check_name, is_ok in checks.items():
            status = "✅" if is_ok else "❌"
            logger.info(f"  {status} {check_name}")

        # Если все проверки прошли - сбрасываем счетчик ошибок
        if all(checks.values()):
            self.reset_error_count()

    async def start_monitoring(self, interval_minutes: int = 10):
        """
        Запускает мониторинг в фоновом режиме.

        Args:
            interval_minutes: Интервал проверки в минутах
        """
        self.is_running = True
        logger.info(f"🏥 Health Monitor запущен (интервал: {interval_minutes} мин)")

        while self.is_running:
            await asyncio.sleep(interval_minutes * 60)
            await self.run_full_check()

    def stop(self):
        """Останавливает мониторинг"""
        self.is_running = False
        logger.info("🛑 Health Monitor остановлен")


# Глобальный экземпляр
health_monitor = HealthMonitor()
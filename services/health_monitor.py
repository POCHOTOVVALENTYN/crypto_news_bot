# services/health_monitor.py

import asyncio
from datetime import datetime, timedelta

from database import logger


class HealthMonitor:
    def __init__(self):
        self.last_post_time = None
        self.error_count = 0

    async def check_health(self):
        """Проверка каждые 10 минут"""
        while True:
            await asyncio.sleep(600)

            # Если давно не было постов - АЛЕРТ
            if self.last_post_time:
                delta = datetime.now() - self.last_post_time
                if delta > timedelta(hours=2):
                    logger.error("🚨 БОТ НЕ ПОСТИТ 2 ЧАСА!")
                    # Отправить уведомление админу

            # Если много ошибок - АЛЕРТ
            if self.error_count > 10:
                logger.error(f"🚨 МНОГО ОШИБОК: {self.error_count}")
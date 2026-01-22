"""
Личный ИИ-планировщик для админа
Анализирует рынок и новости, формирует план на день
"""
import logging
from typing import Optional
from datetime import datetime

from services.ai_manager import AIProviderManager
from database import db

logger = logging.getLogger(__name__)


class PersonalAssistant:
    """Личный ассистент трейдера - генерирует ежедневный план"""
    
    def __init__(self):
        self.ai_manager = AIProviderManager()
    
    async def generate_daily_plan(self) -> str:
        """Генерирует план на день на основе новостей и рынка"""
        
        try:
            # Получаем топ-новости за последние 24 часа
            top_news = await self._fetch_top_news(limit=10)
            
            # Анализируем рынок (упрощённо - можно расширить)
            market_summary = await self._analyze_market_trends()
            
            # Генерируем план через ИИ
            plan = await self._generate_plan_with_ai(top_news, market_summary)
            
            return plan
            
        except Exception as e:
            logger.error(f"Ошибка генерации плана: {e}", exc_info=True)
            return "⚠️ Не удалось сгенерировать план. Попробуйте позже."
    
    async def _fetch_top_news(self, limit: int = 10) -> str:
        """Получает топ-новости за 24 часа"""
        try:
            # Используем БД для получения последних новостей
            from datetime import timedelta
            date_from = (datetime.now() - timedelta(days=1)).isoformat()
            
            async import aiosqlite
            async with aiosqlite.connect(db.db_path) as conn:
                async with conn.execute(
                    """SELECT title, summary, priority 
                       FROM news 
                       WHERE published_date > ?
                       ORDER BY priority DESC, published_date DESC
                       LIMIT ?""",
                    (date_from, limit)
                ) as cursor:
                    rows = await cursor.fetchall()
            
            if not rows:
                return "Новостей за последние 24 часа не найдено."
            
            news_text = ""
            for idx, (title, summary, priority) in enumerate(rows, 1):
                news_text += f"{idx}. [{priority}⭐] {title}\n"
                if summary:
                    news_text += f"   {summary[:100]}...\n"
                news_text += "\n"
            
            return news_text
            
        except Exception as e:
            logger.error(f"Ошибка получения новостей: {e}")
            return "Не удалось загрузить новости."
    
    async def _analyze_market_trends(self) -> str:
        """Анализ рыночных трендов (упрощённая версия)"""
        # TODO: Можно добавить интеграцию с CoinGecko API или TradingView
        # Пока возвращаем заглушку
        return (
            "BTC: стабильность в районе $95k-$100k\n"
            "ETH: консолидация перед возможным ростом\n"
            "Рынок: нейтральные настроения"
        )
    
    async def _generate_plan_with_ai(self, news: str, market: str) -> str:
        """Генерирует план дня через ИИ"""
        
        system_prompt = """Ты личный ассистент профессионального криптотрейдера и аналитика.
Твоя задача - создать структурированный план действий на день на основе:
1. Последних крипто-новостей
2. Текущей рыночной ситуации

Формат ответа:
📋 ПЛАН НА [ДАТА]

🎯 Приоритеты:
• [3-5 главных задач]

📊 Мониторинг:
• [Что отслеживать]

💼 Работа:
• [Задачи по контенту/сообществу]

⚠️ Риски:
• [На что обратить внимание]

Будь конкретным и практичным. Используй эмодзи для наглядности."""

        user_prompt = f"""Сегодня: {datetime.now().strftime('%d.%m.%Y')}

ТОП-НОВОСТИ ЗА 24Ч:
{news}

РЫНОЧНАЯ СИТУАЦИЯ:
{market}

Составь план на день."""

        try:
            response = await self.ai_manager.generate_text(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=800
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка генерации плана через ИИ: {e}")
            return "⚠️ Ошибка при генерации плана через ИИ."


# Глобальный экземпляр
personal_assistant = PersonalAssistant()

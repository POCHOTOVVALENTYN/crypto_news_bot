import logging
from database import db
from services.ai.manager import ai_manager

logger = logging.getLogger(__name__)

class PersonalAssistant:
    """Сервис личного ассистента для админа"""
    
    async def generate_daily_plan(self) -> str:
        """Генерирует план действий на день на основе новостей"""
        try:
            # 1. Получаем топ новости за 24 часа
            top_news = await db.get_news_for_period(hours=24, min_priority=7)
            
            if not top_news:
                return "📭 Недостаточно важных новостей для составления плана."
            
            # Формируем контекст
            news_context = "\n".join([
                f"- {n['title']} (Impact: {n.get('impact_score', 'N/A')})" 
                for n in top_news[:10]
            ])
            
            prompt = (
                f"Ты - личный бизнес-ассистент крипто-трейдера.\n"
                f"Проанализируй эти топ-новости за сутки:\n\n{news_context}\n\n"
                f"Составь краткий и четкий план действий на сегодня (4-5 пунктов):\n"
                f"1. На чем сфокусировать внимание (тренды).\n"
                f"2. Какие моменты требуют немедленной реакции.\n"
                f"3. Идеи для контента в канал (о чем написать).\n"
                f"Отвечай структурированно, с эмодзи. Не лей воду."
            )
            
            # 2. Запрашиваем AI
            response = await ai_manager.generate_text(
                prompt=prompt,
                system_prompt="Ты - профессиональный крипто-аналитик и ассистент.",
                temperature=0.7
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка генерации плана: {e}", exc_info=True)
            return "⚠️ Ошибка генерации плана. Проверьте логи."

personal_assistant = PersonalAssistant()

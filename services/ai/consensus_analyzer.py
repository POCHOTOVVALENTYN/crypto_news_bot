"""
ИИ-Консенсус анализатор
Использует 3 модели параллельно для повышения точности
"""
import asyncio
import logging
from typing import Dict, List
from statistics import median, stdev

from services.ai.manager import AIProviderManager

logger = logging.getLogger(__name__)


class ConsensusAnalyzer:
    """Анализирует новости через несколько ИИ-моделей для консенсуса"""
    
    def __init__(self):
        self.ai_manager = AIProviderManager()
    
    async def analyze_with_consensus(self, news_text: str, title: str) -> Dict:
        """
        Анализирует новость через 3 модели параллельно
        
        Returns:
            {
                'consensus_score': float (1-10),
                'agreement': 'high' | 'medium' | 'low',
                'individual_scores': List[Dict],
                'avg_score': float
            }
        """
        
        try:
            # Запускаем 3 анализа параллельно
            results = await asyncio.gather(
                self._analyze_single(news_text, title, model="gemini"),
                self._analyze_single(news_text, title, model="deepseek"),
                self._analyze_single(news_text, title, model="gpt"),
                return_exceptions=True
            )
            
            # Фильтруем успешные результаты
            valid_results = [r for r in results if isinstance(r, dict) and 'score' in r]
            
            if not valid_results:
                logger.warning("Все модели консенсуса провалились, fallback к одной")
                return await self._fallback_single_model(news_text, title)
            
            # Извлекаем оценки
            scores = [r['score'] for r in valid_results]
            
            # Вычисляем консенсус
            consensus_score = median(scores)
            avg_score = sum(scores) / len(scores)
            
            # Уровень согласованности
            if len(scores) > 1:
                std_deviation = stdev(scores)
                if std_deviation < 1.5:
                    agreement = 'high'
                elif std_deviation < 3.0:
                    agreement = 'medium'
                else:
                    agreement = 'low'
            else:
                agreement = 'single'
            
            logger.info(
                f"📊 Консенсус: {consensus_score:.1f} "
                f"(scores: {scores}, agreement: {agreement})"
            )
            
            return {
                'consensus_score': round(consensus_score, 1),
                'agreement': agreement,
                'individual_scores': valid_results,
                'avg_score': round(avg_score, 1),
                'models_used': len(valid_results)
            }
            
        except Exception as e:
            logger.error(f"Критическая ошибка консенсуса: {e}", exc_info=True)
            return await self._fallback_single_model(news_text, title)
    
    async def _analyze_single(self, news_text: str, title: str, model: str) -> Dict:
        """Анализ одной моделью"""
        
        system_prompt = """Ты эксперт-аналитик крипто-новостей.
Оцени важность новости по шкале 1-10:
1-3: Незначительная
4-6: Средней важности  
7-8: Важная
9-10: Критически важная

Отвечай ТОЛЬКО числом от 1 до 10."""

        prompt = f"Заголовок: {title}\n\nТекст: {news_text[:500]}"
        
        try:
            # Указываем предпочтительную модель если возможно
            response = await self.ai_manager.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=50
            )
            
            # Парсим оценку
            import re
            match = re.search(r'\b([1-9]|10)\b', response)
            if match:
                score = int(match.group(1))
            else:
                score = 5  # Дефолт если не распарсили
            
            return {
                'model': model,
                'score': score,
                'raw_response': response[:100]
            }
            
        except Exception as e:
            logger.error(f"Ошибка модели {model}: {e}")
            raise
    
    async def _fallback_single_model(self, news_text: str, title: str) -> Dict:
        """Fallback на одну модель если консенсус не сработал"""
        try:
            result = await self._analyze_single(news_text, title, "gemini")
            return {
                'consensus_score': result['score'],
                'agreement': 'single',
                'individual_scores': [result],
                'avg_score': result['score'],
                'models_used': 1
            }
        except:
            # Последний fallback
            return {
                'consensus_score': 5.0,
                'agreement': 'fallback',
                'individual_scores': [],
                'avg_score': 5.0,
                'models_used': 0
            }


# Глобальный экземпляр
consensus_analyzer = ConsensusAnalyzer()

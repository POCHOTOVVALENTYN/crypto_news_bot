# services/priority_calculator.py
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PriorityCalculator:
    """Калькулятор приоритетов для новостей"""
    
    # Ключевые слова с весами важности
    CRITICAL_KEYWORDS = {
        # Критические события
        'hack': 10, 'hacked': 10, 'взлом': 10, 'взломали': 10,
        'exploit': 9, 'breach': 9, 'security breach': 10,
        'bankruptcy': 9, 'банкротство': 9, 'bankrupt': 9,
        
        # ETF и регуляция
        'etf approved': 9, 'etf approval': 9, 'etf одобрен': 9,
        'sec approval': 9, 'sec одобрил': 9,
        'sec rejects': 8, 'etf rejected': 8, 'etf отклонен': 8,
        'regulation': 6, 'регуляция': 6, 'regulatory': 6,
        
        # Листинги
        'listing': 7, 'листинг': 7, 'listed': 7,
        'coinbase listing': 8, 'binance listing': 8,
        'delisting': 6, 'делистинг': 6,
        
        # Институциональные
        'blackrock': 8, 'microstrategy': 8, 'grayscale': 7,
        'institutional': 7, 'институционалы': 7,
        'fidelity': 7, 'vanguard': 7,
        
        # Персоны
        'elon musk': 8, 'маск': 8, 'elon': 7,
        'michael saylor': 7, 'сайлор': 7,
        'gary gensler': 7, 'sec chairman': 7,
        'jerome powell': 6, 'джером пауэлл': 6,
        'cz binance': 6, 'changpeng zhao': 6,
    }
    
    # Влиятельные персоны (дополнительные бонусы)
    INFLUENTIAL_PERSONS = [
        'elon musk', 'маск', 'michael saylor', 'сайлор',
        'gary gensler', 'джером пауэлл', 'jerome powell',
        'cz binance', 'changpeng zhao', 'brian armstrong',
        'sam bankman-fried', 'sbf',
    ]
    
    # Премиум источники
    PREMIUM_SOURCES = [
        'coindesk', 'cointelegraph', 'the block', 'decrypt',
        'forklog', 'bits.media',
    ]
    
    @staticmethod
    def calculate_priority(news_item: Dict, ai_data: Optional[Dict] = None) -> int:
        """
        Вычисляет приоритет новости от 0 до 10
        
        Args:
            news_item: Словарь с новостью (title, summary, source)
            ai_data: Результат AI анализа (опционально)
        
        Returns:
            Приоритет от 0 до 10
        """
        priority = 0
        text = (news_item.get('title', '') + ' ' + news_item.get('summary', '')).lower()
        source = news_item.get('source', '').lower()
        
        # 1. Критические ключевые слова
        for keyword, weight in PriorityCalculator.CRITICAL_KEYWORDS.items():
            if keyword in text:
                priority = max(priority, weight)
                logger.debug(f"Найдено ключевое слово '{keyword}' → приоритет {weight}")
        
        # 2. Влиятельные персоны (дополнительный бонус)
        for person in PriorityCalculator.INFLUENTIAL_PERSONS:
            if person in text:
                priority = max(priority, 6)
                logger.debug(f"Упомянута персона '{person}' → приоритет минимум 6")
        
        # 3. Премиум источники
        if any(ps in source for ps in PriorityCalculator.PREMIUM_SOURCES):
            priority = max(priority, 4)
            logger.debug(f"Премиум источник '{source}' → приоритет минимум 4")
        
        # 4. AI анализ важности
        if ai_data:
            importance = ai_data.get('importance', '').lower()
            importance_score = ai_data.get('importance_score', 0)
            
            if importance == 'critical':
                priority = max(priority, 9)
            elif importance == 'very high':
                priority = max(priority, 8)
            elif importance == 'high':
                priority = max(priority, 7)
            elif importance == 'medium':
                priority = max(priority, 5)
            
            # Используем score если доступен
            if isinstance(importance_score, (int, float)) and importance_score > 0:
                priority = max(priority, min(int(importance_score), 10))
        
        # 5. Insider источники - максимальный приоритет
        if 'insider' in source:
            priority = 10
            logger.debug("Insider источник → приоритет 10")
        
        return min(priority, 10)  # Ограничиваем максимумом 10


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
        
        # 3. Премиум источники - минимальный приоритет для всех новостей
        if any(ps in source for ps in PriorityCalculator.PREMIUM_SOURCES):
            priority = max(priority, 3)  # Минимум 3 для премиум источников
            logger.debug(f"Премиум источник '{source}' → приоритет минимум 3")
        
        # 4. Базовый приоритет - если нет ключевых слов, но новость валидна, даем минимум 1
        if priority == 0 and text:
            # Новости от известных источников имеют минимальный приоритет
            priority = 1
        
        # 5. AI анализ важности
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
        
        # 6. Insider источники - максимальный приоритет
        if 'insider' in source:
            priority = 10
            logger.debug("Insider источник → приоритет 10")
        
        return min(priority, 10)  # Ограничиваем максимумом 10

    @staticmethod
    def needs_ai_processing(news_item: Dict) -> bool:
        """
        Определяет, нужен ли AI анализ для новости (Smart Filtering).
        
        Критерии для "AI НЕ нужен":
        - Новость короткая (< 300 символов) И содержит кириллицу (русский язык)
        - Новость содержит только ценовую информацию (price action) без важного контекста
        - Простые анонсы листинга без деталей
        
        Args:
            news_item: Словарь с новостью (title, summary, source)
        
        Returns:
            True если нужен AI анализ, False если можно обойтись без него
        """
        import re
        
        title = news_item.get('title', '')
        summary = news_item.get('summary', '')
        source = news_item.get('source', '').lower()
        
        full_text = (title + ' ' + summary).strip()
        text_length = len(full_text)
        text_lower = full_text.lower()
        
        # Проверяем наличие кириллицы (русский язык)
        has_cyrillic = bool(re.search(r'[а-яА-ЯёЁ]', full_text))
        
        # Критерий 1: Короткая новость + русский язык = не нужен AI
        if text_length < 300 and has_cyrillic:
            logger.info(f"⏭️ Smart Filtering: пропуск AI (короткая русская новость, {text_length} символов)")
            return False
        
        # Критерий 2: Price action (только движение цены) - не нужен AI
        price_action_patterns = [
            r'\b(price|jumped|dropped|increased|decreased|rose|fell)\s+[0-9.%]+',
            r'[0-9.]+%\s+(up|down|higher|lower)',
            r'\$[0-9,]+',
        ]
        is_price_action = any(re.search(pattern, text_lower, re.I) for pattern in price_action_patterns)
        
        # Если это только движение цены без контекста - не нужен AI
        if is_price_action and text_length < 400:
            # Проверяем что нет важных ключевых слов (взлом, ETF и т.д.)
            important_keywords = ['hack', 'etf', 'sec', 'regulation', 'взлом', 'одобр', 'листинг', 'банкрот']
            has_important_keywords = any(kw in text_lower for kw in important_keywords)
            
            if not has_important_keywords:
                logger.info(f"⏭️ Smart Filtering: пропуск AI (price action новость, {text_length} символов)")
                return False
        
        # Критерий 3: Простые анонсы (listing, delisting) - можно без AI если короткие
        if text_length < 250 and any(kw in text_lower for kw in ['listing', 'delisting', 'листинг', 'делистинг']):
            # Если это просто анонс листинга без деталей - не нужен AI
            if 'details' not in text_lower and 'подробности' not in text_lower:
                logger.info(f"⏭️ Smart Filtering: пропуск AI (простой анонс листинга, {text_length} символов)")
                return False
        
        # Во всех остальных случаях нужен AI
        return True



# utils/news_validator.py
import re
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class NewsValidator:
    """Валидатор новостей"""
    
    MAX_AGE_HOURS = 48  # Максимальный возраст новости в часах
    
    @staticmethod
    def is_news_relevant(news_item: Dict, max_age_hours: int = None) -> bool:
        """
        Проверяет актуальность новости
        
        Args:
            news_item: Словарь с новостью
            max_age_hours: Максимальный возраст в часах (по умолчанию MAX_AGE_HOURS)
        
        Returns:
            True если новость актуальна, False если устарела
        """
        if max_age_hours is None:
            max_age_hours = NewsValidator.MAX_AGE_HOURS
        
        try:
            published_at = news_item.get('published_at', '')
            if not published_at:
                # Если даты нет, считаем актуальной
                return True
            
            # Различные форматы дат
            date_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%S%z',
                '%a, %d %b %Y %H:%M:%S %Z',
                '%a, %d %b %Y %H:%M:%S %z',
                '%d %b %Y %H:%M:%S',
            ]
            
            pub_date = None
            for fmt in date_formats:
                try:
                    pub_date = datetime.strptime(published_at, fmt)
                    break
                except ValueError:
                    continue
            
            if not pub_date:
                # Если не удалось распарсить, считаем актуальной
                logger.warning(f"⚠️ Не удалось распарсить дату: {published_at}")
                return True
            
            age = datetime.now() - pub_date.replace(tzinfo=None) if pub_date.tzinfo else datetime.now() - pub_date
            
            if age > timedelta(hours=max_age_hours):
                logger.debug(f"⏰ Новость устарела ({age.total_seconds()/3600:.1f}ч): {news_item.get('title', '')[:50]}")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки актуальности: {e}")
            return True  # В случае ошибки считаем актуальной
    
    @staticmethod
    def validate_news_item(news_item: Dict) -> tuple[bool, Optional[str]]:
        """
        Валидация новости перед сохранением
        
        Returns:
            (is_valid, error_message)
        """
        # Проверка заголовка
        title = news_item.get('title', '').strip()
        if not title or len(title) < 5:
            return False, "Заголовок слишком короткий"
        
        if len(title) > 500:
            return False, "Заголовок слишком длинный"
        
        # Проверка URL
        url = news_item.get('url', '').strip()
        if not url:
            return False, "URL не указан"
        
        # Проверка источника
        source = news_item.get('source', '').strip()
        if not source:
            return False, "Источник не указан"
        
        # Проверка на подозрительные символы
        if any(char in title for char in ['--', ';', '/*', '*/']):
            return False, "Подозрительные символы в заголовке"
        
        return True, None


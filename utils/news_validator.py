# utils/news_validator.py
import re
import time
from time import mktime
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class NewsValidator:
    """Валидатор новостей"""
    
    MAX_AGE_HOURS = 48  # Максимальный возраст новости в часах
    
    @staticmethod
    def is_today_news(news_item: Dict, max_age_hours: int = 24) -> bool:
        """
        Проверяет что новость свежая (не старше max_age_hours часов)
        
        Args:
            news_item: Словарь с новостью
            max_age_hours: Максимальный возраст в часах (по умолчанию 24)
            
        Returns:
            True если новость свежая (не старше max_age_hours), False если устарела
        """
        try:
            published_at = news_item.get('published_at', '') or news_item.get('published', '')
            if not published_at:
                # Если даты нет, считаем актуальной (на всякий случай)
                logger.debug(f"⚠️ Дата публикации отсутствует, считаем актуальной: {news_item.get('title', '')[:50]}")
                return True
            
            pub_date = None
            
            # Feedparser может вернуть time.struct_time - конвертируем в datetime
            if isinstance(published_at, time.struct_time):
                try:
                    pub_date = datetime.fromtimestamp(mktime(published_at))
                except (ValueError, TypeError, OSError):
                    pass
            
            # Если это datetime объект
            if isinstance(published_at, datetime):
                pub_date = published_at
            
            # Если это строка - парсим
            if not pub_date:
                # Различные форматы дат (включая форматы из feedparser)
                date_formats = [
                    '%a, %d %b %Y %H:%M:%S %z',  # RFC 822 с timezone (feedparser)
                    '%a, %d %b %Y %H:%M:%S %Z',  # RFC 822 с timezone name
                    '%a, %d %b %Y %H:%M:%S',     # RFC 822 без timezone
                    '%Y-%m-%dT%H:%M:%S%z',       # ISO 8601 с timezone
                    '%Y-%m-%dT%H:%M:%S',         # ISO 8601 без timezone
                    '%Y-%m-%d %H:%M:%S',         # Простой формат
                    '%d %b %Y %H:%M:%S',         # Альтернативный формат
                    '%Y-%m-%d',                  # Только дата
                ]
                
                for fmt in date_formats:
                    try:
                        pub_date = datetime.strptime(str(published_at).strip(), fmt)
                        break
                    except (ValueError, AttributeError):
                        continue
            
            if not pub_date:
                # Если не удалось распарсить, считаем актуальной (на всякий случай)
                logger.debug(f"⚠️ Не удалось распарсить дату '{published_at}' (тип: {type(published_at)}) для проверки свежести, считаем актуальной: {news_item.get('title', '')[:50]}")
                return True
            
            # Убираем timezone info если есть, для корректного сравнения
            if pub_date.tzinfo:
                pub_date_no_tz = pub_date.replace(tzinfo=None)
            else:
                pub_date_no_tz = pub_date
            
            # Проверяем возраст новости
            now = datetime.now()
            age = now - pub_date_no_tz
            
            is_fresh = age <= timedelta(hours=max_age_hours)
            
            if not is_fresh:
                age_hours = age.total_seconds() / 3600
                logger.debug(f"⏰ Новость устарела (возраст: {age_hours:.1f}ч, порог: {max_age_hours}ч): {news_item.get('title', '')[:50]}")
            
            return is_fresh
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки свежести новости: {e}", exc_info=True)
            return True  # В случае ошибки считаем актуальной

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
        
        # Проверка URL (поддерживаем и 'url', и 'link' для совместимости)
        url = news_item.get('url') or news_item.get('link', '')
        if url:
            url = str(url).strip()
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



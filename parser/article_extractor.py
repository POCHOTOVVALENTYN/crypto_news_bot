# parser/article_extractor.py
import logging
import re
import asyncio
from typing import Optional
from html import unescape

logger = logging.getLogger(__name__)


def clean_html(text: str) -> str:
    """Удаляет HTML теги и декодирует HTML сущности"""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def extract_full_article_html(url: str) -> Optional[str]:
    """
    Извлекает полный текст статьи по URL используя HTML парсинг
    
    Args:
        url: URL статьи
    
    Returns:
        Полный текст статьи или None
    """
    try:
        # Используем newspaper3k для извлечения статьи
        # newspaper3k синхронный, оборачиваем в executor
        import asyncio
        from newspaper import Article
        
        def _extract():
            article = Article(url, language='ru')
            article.download()
            article.parse()
            return article.text if article.text and len(article.text) > 200 else None
        
        # Запускаем синхронный код в executor
        text = await asyncio.wait_for(
            asyncio.to_thread(_extract),
            timeout=15.0
        )
        
        if text:
            logger.debug(f"✅ Извлечен полный текст статьи ({len(text)} символов): {url}")
            return text
        else:
            logger.debug(f"⚠️ Статья слишком короткая или пустая: {url}")
            
    except asyncio.TimeoutError:
        logger.debug(f"⚠️ Timeout при извлечении статьи: {url}")
    except Exception as e:
        logger.debug(f"⚠️ Ошибка извлечения статьи {url}: {e}")
    
    return None


async def get_article_content(entry: dict, url: str) -> str:
    """
    Получает контент статьи используя комбинированный подход:
    1. RSS content:encoded / content
    2. HTML парсинг статьи
    3. Fallback на summary
    
    Args:
        entry: RSS entry объект
        url: URL статьи
    
    Returns:
        Полный текст статьи или summary
    """
    # 1. Проверяем RSS content:encoded или content
    content = None
    
    # Пробуем content (list of dicts)
    if 'content' in entry:
        if isinstance(entry.content, list) and len(entry.content) > 0:
            content = entry.content[0].get('value', '')
    
    # Пробуем content_encoded (string)
    if not content and hasattr(entry, 'content_encoded'):
        content = entry.content_encoded
    
    # Пробуем description (иногда содержит полный текст)
    if not content and 'description' in entry:
        description = entry.description
        # Если description достаточно длинный, используем его
        if len(clean_html(description)) > 500:
            content = description
    
    # Очищаем HTML из RSS content
    if content:
        cleaned_content = clean_html(content)
        if len(cleaned_content) > 500:
            logger.debug(f"✅ Использован RSS content ({len(cleaned_content)} символов)")
            return cleaned_content
    
    # 2. Парсим HTML статьи
    full_text = await extract_full_article_html(url)
    if full_text and len(full_text) > 500:
        return full_text
    
    # 3. Fallback на summary
    summary = entry.get("summary", "")
    if summary:
        cleaned_summary = clean_html(summary)
        logger.debug(f"⚠️ Использован summary ({len(cleaned_summary)} символов)")
        return cleaned_summary
    
    return ""


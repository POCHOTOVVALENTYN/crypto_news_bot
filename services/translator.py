# services/translator.py
"""
Сервис для перевода текста с использованием Google Translate через deep-translator.
Используется для быстрого и дешевого перевода новостей.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Попытка импорта deep-translator
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    logger.warning("⚠️ deep-translator не установлен. Перевод отключен. Установите: pip install deep-translator")


class NewsTranslator:
    """Класс для перевода новостей"""
    
    def __init__(self):
        self.translator_available = TRANSLATOR_AVAILABLE
        if TRANSLATOR_AVAILABLE:
            logger.info("✅ Google Translator доступен (deep-translator)")
    
    def detect_language(self, text: str) -> Optional[str]:
        """
        Определяет язык текста
        
        Args:
            text: Текст для определения языка
        
        Returns:
            Код языка (например, 'en', 'ru') или None
        """
        if not text:
            return None
        
        try:
            # Простая проверка кириллицы (быстро и надежно)
            import re
            if re.search(r'[а-яА-ЯёЁ]', text):
                return 'ru'
            
            # Если нет кириллицы - скорее всего английский
            # deep-translator не имеет встроенного detect, используем простую эвристику
            return 'en'
        except Exception as e:
            logger.debug(f"⚠️ Ошибка определения языка: {e}")
            # Fallback: простая проверка кириллицы
            import re
            if re.search(r'[а-яА-ЯёЁ]', text):
                return 'ru'
            return 'en'  # По умолчанию английский
    
    def translate_text(self, text: str, source_lang: str = 'auto', target_lang: str = 'ru') -> Optional[str]:
        """
        Переводит текст на целевой язык (синхронный метод)
        
        Args:
            text: Текст для перевода
            source_lang: Исходный язык ('auto' для автоопределения)
            target_lang: Целевой язык (по умолчанию 'ru')
        
        Returns:
            Переведенный текст или None при ошибке
        """
        if not self.translator_available or not text:
            return None
        
        try:
            # deep-translator синхронный
            if source_lang == 'auto':
                # Для auto определяем язык вручную
                detected = self.detect_language(text)
                source_lang = detected if detected else 'en'
            
            # Если уже на русском - не переводим
            if source_lang == 'ru' or source_lang == target_lang:
                return text
            
            # Создаем переводчик для конкретных языков
            translator = GoogleTranslator(source=source_lang, target=target_lang)
            translated_text = translator.translate(text)
            
            if translated_text:
                logger.debug(f"✅ Переведено: {len(text)} → {len(translated_text)} символов")
                return translated_text
            else:
                logger.warning(f"⚠️ Переводчик вернул пустой результат")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка перевода: {e}")
            return None
    
    async def translate_news(self, title: str, summary: str) -> Optional[dict]:
        """
        Переводит заголовок и описание новости (асинхронная обертка)
        
        Args:
            title: Заголовок новости
            summary: Описание новости
        
        Returns:
            Словарь с переведенными полями или None
        """
        if not self.translator_available:
            return None
        
        import asyncio
        
        # Запускаем синхронные методы в executor
        loop = asyncio.get_event_loop()
        
        try:
            # Определяем язык
            full_text = f"{title} {summary}"
            detected_lang = await loop.run_in_executor(None, self.detect_language, full_text)
            
            # Если уже на русском - не переводим
            if detected_lang == 'ru':
                logger.debug("ℹ️ Новость уже на русском языке, перевод не требуется")
                return None
            
            # Переводим (синхронные вызовы в executor)
            translated_title = await loop.run_in_executor(
                None, self.translate_text, title, detected_lang or 'auto', 'ru'
            )
            translated_summary = await loop.run_in_executor(
                None, self.translate_text, summary, detected_lang or 'auto', 'ru'
            ) if summary else None
            
            if translated_title:
                result = {
                    'ru_title': translated_title,
                    'ru_summary': translated_summary or summary,
                    'source_lang': detected_lang or 'auto'
                }
                logger.info(f"✅ Новость переведена с {detected_lang or 'auto'} на ru")
                return result
            
            return None
        except Exception as e:
            logger.warning(f"⚠️ Ошибка перевода новости: {e}")
            return None


# Глобальный экземпляр
translator = NewsTranslator()


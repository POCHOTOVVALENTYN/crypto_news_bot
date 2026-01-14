# services/content_summarizer.py
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class ContentSummarizer:
    """Копирайтер-выжимка: создает краткую выжимку из текста БЕЗ использования ИИ"""
    
    @staticmethod
    def create_extractive_summary(
        text: str, 
        sentences_count: int = 5,
        language: str = "russian"
    ) -> str:
        """
        Создает выжимку из текста используя extractive summarization (БЕЗ ИИ)
        
        Args:
            text: Полный текст статьи
            sentences_count: Количество предложений в выжимке
            language: Язык текста ("russian" или "english")
        
        Returns:
            Выжимка из sentences_count предложений
        """
        if not text or len(text) < 200:
            return text
        
        try:
            # Используем sumy для extractive summarization
            from sumy.parsers.plaintext import PlaintextParser
            from sumy.nlp.tokenizers import Tokenizer
            from sumy.summarizers.text_rank import TextRankSummarizer
            
            # Парсим текст
            parser = PlaintextParser.from_string(text, Tokenizer(language))
            
            # Используем TextRank (лучше для новостей)
            summarizer = TextRankSummarizer()
            
            # Создаем выжимку
            summary_sentences = summarizer(parser.document, sentences_count)
            
            # Объединяем в текст
            summary_text = " ".join([str(sentence) for sentence in summary_sentences])
            
            logger.debug(f"✅ Создана выжимка: {len(text)} → {len(summary_text)} символов")
            return summary_text.strip()
            
        except ImportError:
            logger.warning("⚠️ sumy не установлен, используется fallback метод")
            # Fallback: первые N предложений
            return ContentSummarizer._fallback_summary(text, sentences_count)
        except Exception as e:
            logger.warning(f"⚠️ Ошибка создания выжимки: {e}, используется fallback")
            # Fallback: первые N предложений
            return ContentSummarizer._fallback_summary(text, sentences_count)
    
    @staticmethod
    def _fallback_summary(text: str, sentences_count: int) -> str:
        """Fallback метод: берет первые N предложений"""
        sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 30]
        selected = sentences[:sentences_count]
        return '. '.join(selected) + '.' if selected else text[:500]
    
    @staticmethod
    def extract_key_points(text: str, points_count: int = 3) -> List[str]:
        """
        Извлекает ключевые моменты из текста (для bullet points в сообщениях)
        
        Args:
            text: Полный текст статьи
            points_count: Количество ключевых моментов
        
        Returns:
            Список ключевых предложений
        """
        if not text or len(text) < 200:
            return [text] if text else []
        
        try:
            from sumy.parsers.plaintext import PlaintextParser
            from sumy.nlp.tokenizers import Tokenizer
            from sumy.summarizers.text_rank import TextRankSummarizer
            
            parser = PlaintextParser.from_string(text, Tokenizer("russian"))
            summarizer = TextRankSummarizer()
            
            key_sentences = summarizer(parser.document, points_count)
            return [str(sentence).strip() for sentence in key_sentences]
            
        except Exception:
            # Fallback: выбираем предложения по длине
            sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 50]
            # Сортируем по длине (более длинные обычно более информативные)
            sentences.sort(key=len, reverse=True)
            return sentences[:points_count] if sentences else [text[:200]]


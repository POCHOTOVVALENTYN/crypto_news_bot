"""
Умная дедупликация контента новостей
Удаляет повторяющуюся информацию между заголовком, описанием и ключевыми моментами
"""
import re
import logging
from typing import List, Dict, Set, Optional
from thefuzz import fuzz

logger = logging.getLogger(__name__)

# Стоп-слова для русского и английского языков
STOP_WORDS_RU = {
    'в', 'на', 'и', 'с', 'по', 'для', 'не', 'от', 'до', 'из', 'к', 'о', 'это',
    'что', 'как', 'было', 'был', 'была', 'были', 'будет', 'за', 'или', 'у', 'а'
}

STOP_WORDS_EN = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'it'
}

STOP_WORDS = STOP_WORDS_RU | STOP_WORDS_EN


class ContentDeduplicator:
    """Умная дедупликация контента"""
    
    @staticmethod
    def tokenize(text: str, remove_stop_words: bool = True) -> Set[str]:
        """
        Токенизация текста
        
        Args:
            text: Исходный текст
            remove_stop_words: Удалить стоп-слова
            
        Returns:
            Множество токенов (слов в нижнем регистре)
        """
        # Приводим к нижнему регистру
        text = text.lower()
        
        # Удаляем HTML теги
        text = re.sub(r'<[^>]+>', '', text)
        
        # Извлекаем слова (только буквы и цифры)
        words = re.findall(r'\b[а-яёa-z0-9]+\b', text)
        
        # Удаляем стоп-слова если нужно
        if remove_stop_words:
            words = [w for w in words if w not in STOP_WORDS and len(w) > 2]
        
        return set(words)
    
    @staticmethod
    def calculate_jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
        """
        Вычисляет Jaccard сходство между двумя множествами
        
        Returns:
            Значение от 0 до 1 (1 = полное совпадение)
        """
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def detect_title_description_overlap(title: str, description: str, threshold: float = 0.7) -> bool:
        """
        Проверяет пересечение title и description
        
        Args:
            title: Заголовок
            description: Описание
            threshold: Порог сходства (0.7 = 70%)
            
        Returns:
            True если сходство выше порога
        """
        if not title or not description:
            return False
        
        title_tokens = ContentDeduplicator.tokenize(title)
        desc_tokens = ContentDeduplicator.tokenize(description)
        
        similarity = ContentDeduplicator.calculate_jaccard_similarity(title_tokens, desc_tokens)
        
        logger.debug(f"Title-Description similarity: {similarity:.2f} (threshold: {threshold})")
        
        return similarity >= threshold
    
    @staticmethod
    def deduplicate_key_points(title: str, key_points: List[str], threshold: float = 0.5) -> List[str]:
        """
        Удаляет key points, дублирующие title
        
        Args:
            title: Заголовок
            key_points: Список ключевых моментов
            threshold: Порог сходства (0.5 = 50%)
            
        Returns:
            Отфильтрованный список ключевых моментов
        """
        if not key_points or not title:
            return key_points
        
        title_tokens = ContentDeduplicator.tokenize(title)
        filtered_points = []
        
        for point in key_points:
            point_tokens = ContentDeduplicator.tokenize(point)
            
            # Вычисляем overlap как процент от title
            if not title_tokens:
                filtered_points.append(point)
                continue
                
            overlap = len(title_tokens & point_tokens) / len(title_tokens)
            
            logger.debug(f"Point overlap with title: {overlap:.2f} - '{point[:50]}...'")
            
            if overlap < threshold:
                filtered_points.append(point)
            else:
                logger.info(f"🗑️ Удален дублирующий key point: '{point[:80]}...'")
        
        return filtered_points
    
    @staticmethod
    def deduplicate_key_points_among_themselves(key_points: List[str], threshold: float = 0.8) -> List[str]:
        """
        Удаляет дублирующиеся ключевые моменты между собой
        
        Args:
            key_points: Список ключевых моментов
            threshold: Порог сходства (0.8 = 80%)
            
        Returns:
            Список уникальных ключевых моментов
        """
        if not key_points or len(key_points) < 2:
            return key_points
        
        unique_points = []
        
        for i, point in enumerate(key_points):
            is_duplicate = False
            point_tokens = ContentDeduplicator.tokenize(point)
            
            # Проверяем с уже добавленными точками
            for existing_point in unique_points:
                existing_tokens = ContentDeduplicator.tokenize(existing_point)
                similarity = ContentDeduplicator.calculate_jaccard_similarity(point_tokens, existing_tokens)
                
                if similarity >= threshold:
                    logger.info(f"🗑️ Удален дублирующий key point: '{point[:80]}...'")
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_points.append(point)
        
        return unique_points
    
    @staticmethod
    async def smart_summarize(
        title: str,
        description: str,
        key_points: Optional[List[str]] = None,
        dedup_threshold: float = 0.6
    ) -> Dict:
        """
        Создает оптимальный контент без дублирования
        
        Args:
            title: Заголовок
            description: Описание
            key_points: Ключевые моменты
            dedup_threshold: Порог дедупликации (0.6 = 60%)
            
        Returns:
            Словарь с оптимизированным контентом
        """
        result = {
            'title': title,
            'content': description,
            'key_points': key_points or [],
            'dedup_applied': False
        }
        
        # 1. Проверяем пересечение title и description
        title_desc_overlap = ContentDeduplicator.detect_title_description_overlap(
            title, description, threshold=dedup_threshold
        )
        
        if title_desc_overlap:
            logger.info(f"⚠️ Обнаружено сильное пересечение title-description ({dedup_threshold*100:.0f}%+)")
            # Если description дублирует title - используем только key_points
            result['content'] = ""
            result['dedup_applied'] = True
        
        # 2. Фильтруем key points от дублирования с title
        if key_points:
            filtered_points = ContentDeduplicator.deduplicate_key_points(
                title, key_points, threshold=0.5
            )
            
            # 3. Фильтруем key points между собой
            filtered_points = ContentDeduplicator.deduplicate_key_points_among_themselves(
                filtered_points, threshold=0.8
            )
            
            result['key_points'] = filtered_points
            
            if len(filtered_points) < len(key_points):
                result['dedup_applied'] = True
                logger.info(f"📊 Дедупликация: {len(key_points)} → {len(filtered_points)} ключевых моментов")
        
        return result
    
    @staticmethod
    def get_dedup_stats(original_key_points: int, filtered_key_points: int, title_desc_overlap: bool) -> str:
        """
        Возвращает статистику дедупликации
        
        Returns:
            Строка с описанием примененных изменений
        """
        stats = []
        
        if title_desc_overlap:
            stats.append("Title-Description overlap detected")
        
        if original_key_points > filtered_key_points:
            removed = original_key_points - filtered_key_points
            stats.append(f"Removed {removed} duplicate key point(s)")
        
        return " | ".join(stats) if stats else "No duplicates detected"

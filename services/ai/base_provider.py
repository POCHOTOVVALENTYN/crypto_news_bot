from abc import ABC, abstractmethod
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

class AIProvider(ABC):
    """
    Абстрактный базовый класс для всех AI провайдеров.
    Определяет интерфейс для генерации текста и анализа JSON.
    """
    
    def __init__(self, api_key: str = None, **kwargs):
        self.api_key = api_key
        self.name = self.__class__.__name__.replace("Provider", "")
        self.logger = logging.getLogger(f"services.ai.providers.{self.name}")

    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        """
        Генерирует текст на основе промпта.
        
        Args:
            prompt: Основной запрос пользователя
            system_prompt: Системная инструкция (опционально)
            **kwargs: Дополнительные параметры (temperature, max_tokens и т.д.)
            
        Returns:
            Сгенерированный текст или None в случае ошибки
        """
        pass

    @abstractmethod
    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        """
        Анализирует текст и возвращает структурированный JSON.
        
        Args:
            prompt: Запрос
            system_prompt: Системная инструкция
            schema: Ожидаемая схема JSON (опционально, для валидации)
            
        Returns:
            Dictionary с данными или None
        """
        pass
    
    def _clean_json_response(self, text: str) -> Optional[Dict]:
        """Хелпер для очистки JSON от Markdown"""
        import json
        import re
        
        try:
            # 1. Удаляем блоки кода ```json ... ```
            text = text.replace('```json', '').replace('```', '')

            # 2. Ищем JSON структуру с помощью regex (от первой { до последней })
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)

            # 3. Если regex не нашел, пробуем распарсить весь текст
            return json.loads(text.strip())
        except Exception as e:
            self.logger.error(f"⚠️ Ошибка парсинга JSON: {e}")
            return None

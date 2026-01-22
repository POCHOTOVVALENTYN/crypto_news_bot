"""
Сервис проверки Instagram Stories через Gemini Vision API
"""
import logging
import base64
from typing import Dict, Optional
from io import BytesIO

from loader import bot
from services.ai.manager import AIProviderManager

logger = logging.getLogger(__name__)


class StoryVerificator:
    """Проверка скриншотов Stories на наличие упоминания @blexler_invest"""
    
    def __init__(self):
        self.ai_manager = AIProviderManager()
        self.target_mention = "@blexler_invest"
    
    async def verify_story_screenshot(self, photo_file_id: str, user_id: int) -> Dict:
        """
        Проверяет скриншот Stories через Gemini Vision
        
        Returns:
            {
                'verified': bool,
                'confidence': float,
                'xp_earned': int,
                'reason': str
            }
        """
        try:
            # Скачиваем фото от пользователя
            file = await bot.get_file(photo_file_id)
            file_bytes = BytesIO()
            await bot.download_file(file.file_path, file_bytes)
            photo_bytes = file_bytes.getvalue()
            
            # Конвертируем в base64 для Gemini
            photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
            
            # Отправляем на проверку в Gemini Vision
            result = await self._check_with_gemini_vision(photo_base64, user_id)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка проверки Stories для {user_id}: {e}", exc_info=True)
            return {
                'verified': False,
                'confidence': 0.0,
                'xp_earned': 0,
                'reason': 'Ошибка обработки изображения'
            }
    
    async def _check_with_gemini_vision(self, photo_base64: str, user_id: int) -> Dict:
        """Проверка через Gemini Vision API"""
        
        prompt = f"""Проанализируй это изображение Instagram Stories.

Твоя задача: найти упоминание аккаунта "{self.target_mention}" в тексте или визуально.

Что проверить:
1. Есть ли текст "{self.target_mention}" на изображении?
2. Есть ли визуальная отметка (тег) этого аккаунта?
3. Видна ли иконка Instagram с упоминанием?

Ответь строго в формате JSON:
{{
    "found": true/false,
    "confidence": 0.0-1.0,
    "location": "описание где найдено" или null,
    "reasoning": "краткое объяснение"
}}

Будь строгим: если сомневаешься - найди = false."""

        try:
            # Используем Gemini для Vision анализа
            # Примечание: ai_manager.generate_text() не поддерживает изображения напрямую
            # Нужно использовать специальный метод или прямой вызов Gemini API
            
            # Для упрощения используем прямой вызов к Gemini
            import google.generativeai as genai
            from config import config
            
            genai.configure(api_key=config.gemini_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Отправляем изображение и промпт
            import PIL.Image
            import io
            
            # Декодируем base64 обратно в bytes для PIL
            image_bytes = base64.b64decode(photo_base64)
            image = PIL.Image.open(io.BytesIO(image_bytes))
            
            response = model.generate_content([prompt, image])
            response_text = response.text
            
            # Парсим JSON ответ
            import json
            # Извлекаем JSON из ответа (может быть в markdown блоке)
            if '```json' in response_text:
                json_str = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                json_str = response_text.split('```')[1].split('```')[0].strip()
            else:
                json_str = response_text.strip()
            
            result = json.loads(json_str)
            
            # Формируем ответ
            verified = result.get('found', False)
            confidence = float(result.get('confidence', 0.0))
            
            # Даём +100 XP только если found=True и confidence >= 0.7
            xp_earned = 100 if (verified and confidence >= 0.7) else 0
            
            return {
                'verified': verified and confidence >= 0.7,
                'confidence': confidence,
                'xp_earned': xp_earned,
                'reason': result.get('reasoning', 'Проверка завершена'),
                'location': result.get('location')
            }
            
        except Exception as e:
            logger.error(f"Ошибка Gemini Vision для {user_id}: {e}", exc_info=True)
            return {
                'verified': False,
                'confidence': 0.0,
                'xp_earned': 0,
                'reason': f'Ошибка AI анализа: {str(e)}'
            }


# Глобальный экземпляр
story_verificator = StoryVerificator()

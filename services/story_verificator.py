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
                'reason': str,
                'verification_status': str,
                'local_file_path': str,
                'image_hash': str
            }
        """
        try:
            from datetime import datetime
            from services.image_storage import image_storage
            
            # Скачиваем фото
            file = await bot.get_file(photo_file_id)
            file_bytes = BytesIO()
            await bot.download_file(file.file_path, file_bytes)
            photo_bytes = file_bytes.getvalue()
            
            # Сохраняем локально
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            local_path, image_hash = await image_storage.save_image(
                user_id, photo_bytes, timestamp
            )
            
            # Проверка на дубликат
            is_duplicate = await image_storage.check_duplicate(image_hash, user_id)
            if is_duplicate:
                return {
                    'verified': False,
                    'confidence': 0.0,
                    'xp_earned': 0,
                    'reason': 'Дубликат: этот скриншот уже был отправлен',
                    'verification_status': 'auto_rejected',
                    'local_file_path': local_path,
                    'image_hash': image_hash
                }
            
            # Конвертируем в base64 для Gemini
            photo_base64 = base64.b64encode(photo_bytes).decode('utf-8')
            
            # Отправляем на проверку в Gemini Vision
            result = await self._check_with_gemini_vision(photo_base64, user_id)
            
            # Добавляем пути
            result['local_file_path'] = local_path
            result['image_hash'] = image_hash
            
            # Определяем статус
            if result.get('location') == 'Fallback' or result.get('location') == 'Error Fallback':
                # AI недоступен - на модерацию
                result['verification_status'] = 'pending_review'
                result['xp_earned'] = 0  # Временно 0, начислим после одобрения
                result['reason'] = 'Отправлено на проверку модератором (AI недоступен)'
            elif result['confidence'] < 0.7:
                # Низкая уверенность - на модерацию
                result['verification_status'] = 'pending_review'
                result['xp_earned'] = 0
                result['reason'] = 'Отправлено на проверку модератором (низкая уверенность AI)'
            elif result['verified']:
                result['verification_status'] = 'auto_approved'
            else:
                result['verification_status'] = 'auto_rejected'
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка проверки Stories для {user_id}: {e}", exc_info=True)
            return {
                'verified': False,
                'confidence': 0.0,
                'xp_earned': 0,
                'reason': 'Ошибка обработки изображения',
                'verification_status': 'auto_rejected',
                'local_file_path': None,
                'image_hash': None
            }
    
    async def _check_with_gemini_vision(self, photo_base64: str, user_id: int) -> Dict:
        """Проверка через Gemini Vision API"""
        
        prompt = f"""Ты - эксперт по проверке Instagram Stories.

ЗАДАЧА: Найти упоминание аккаунта "{self.target_mention}" на скриншоте.

ЧТО ИСКАТЬ:
1. Текстовая отметка "{self.target_mention}" (может быть в любом месте)
2. Визуальный тег Instagram (иконка профиля + имя аккаунта)
3. Упоминание в подписи или стикере

КРИТЕРИИ УСПЕХА:
- Отметка ЧЕТКО видна и читаема
- Это действительно Instagram Stories (характерный интерфейс)
- Скриншот не обрезан критично

ОТВЕТ СТРОГО В JSON:
{{
    "found": true/false,
    "confidence": 0.0-1.0,
    "location": "где найдено (например: 'в центре экрана', 'в подписи')" или null,
    "reasoning": "почему принято решение",
    "is_instagram": true/false,
    "quality_ok": true/false
}}

ВАЖНО: Если сомневаешься - ставь confidence < 0.7"""

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
            
            # --- FAULT TOLERANT LOGIC ---
            from google.api_core import exceptions
            
            # Try multiple Gemini models in order of preference
            # Using stable model names that are actually available
            models_to_try = [
                "gemini-1.5-flash-latest",  # Stable, fast
                "gemini-1.5-pro-latest",    # More capable
                "gemini-pro-vision"         # Fallback
            ]
            
            response = None
            last_error = None
            
            for model_name in models_to_try:
                try:
                    logger.info(f"Trying Vision model: {model_name}")
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content([prompt, image])
                    break # Success
                except exceptions.NotFound:
                    logger.warning(f"Model {model_name} not found, trying next...")
                    continue
                except Exception as e:
                    logger.error(f"Error with model {model_name}: {e}")
                    last_error = e
                    # Если ошибка не критичная (не 404), можно попробовать другую
                    continue
            
            if not response:
                # Try OpenAI GPT-4V as final fallback
                # Check if OpenAI Vision is enabled
                from config import OPENAI_VISION_ENABLED
                
                if not OPENAI_VISION_ENABLED:
                    logger.warning("⚠️ OpenAI Vision disabled (quota exceeded). Sending to moderation.")
                else:
                    logger.warning("⚠️ All Gemini models failed. Trying OpenAI GPT-4V...")
                    try:
                        openai_result = await self._check_with_openai_vision(photo_base64, prompt)
                        if openai_result:
                            return openai_result
                    except Exception as openai_error:
                        logger.error(f"❌ OpenAI Vision also failed: {openai_error}")
                
                # --- FINAL FALLBACK: Если все модели недоступны ---
                logger.error("❌ All Vision models failed. Activating FALLBACK MODE.")
                return {
                    'verified': True,
                    'confidence': 1.0, 
                    'xp_earned': 100,
                    'reason': 'Авто-подтверждение (AI недоступен, модератор проверит позже)',
                    'location': 'Fallback',
                    'ai_response': None,
                    'ai_provider': 'fallback'
                }

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
                'location': result.get('location'),
                'ai_response': json.dumps(result, ensure_ascii=False),  # Полный ответ AI
                'ai_provider': 'gemini',
                'is_instagram': result.get('is_instagram', True),
                'quality_ok': result.get('quality_ok', True)
            }
            
        except Exception as e:
            logger.error(f"Critical Error in Vision logic for {user_id}: {e}", exc_info=True)
            # FALLBACK на случай ошибок парсинга или других сбоев
            return {
                'verified': True,
                'confidence': 0.5, # Помечаем как сомнительное
                'xp_earned': 100,
                'reason': 'Ошибка анализатора (Начислено авансом)',
                'location': 'Error Fallback',
                'ai_response': str(e),
                'ai_provider': 'error'
            }
    
    async def _check_with_openai_vision(self, photo_base64: str, prompt: str) -> Dict:
        """Проверка через OpenAI GPT-4V API"""
        try:
            from config import config
            import aiohttp
            import json
            
            if not config.openai_api_key:
                logger.warning("⚠️ OpenAI API key not configured")
                return None
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.openai_api_key}"
            }
            
            payload = {
                "model": "gpt-4o",  # gpt-4o has vision capabilities
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{photo_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenAI API error: {response.status} - {error_text}")
                        return None
                    
                    data = await response.json()
                    response_text = data['choices'][0]['message']['content']
                    
                    # Парсим JSON
                    if '```json' in response_text:
                        json_str = response_text.split('```json')[1].split('```')[0].strip()
                    elif '```' in response_text:
                        json_str = response_text.split('```')[1].split('```')[0].strip()
                    else:
                        json_str = response_text.strip()
                    
                    result = json.loads(json_str)
                    
                    verified = result.get('found', False)
                    confidence = float(result.get('confidence', 0.0))
                    xp_earned = 100 if (verified and confidence >= 0.7) else 0
                    
                    logger.info(f"✅ OpenAI GPT-4V response: found={verified}, confidence={confidence}")
                    
                    return {
                        'verified': verified and confidence >= 0.7,
                        'confidence': confidence,
                        'xp_earned': xp_earned,
                        'reason': result.get('reasoning', 'Проверка завершена'),
                        'location': result.get('location'),
                        'ai_response': json.dumps(result, ensure_ascii=False),
                        'ai_provider': 'openai-gpt4v',
                        'is_instagram': result.get('is_instagram', True),
                        'quality_ok': result.get('quality_ok', True)
                    }
                    
        except Exception as e:
            logger.error(f"Error in OpenAI Vision: {e}", exc_info=True)
            return None


# Глобальный экземпляр
story_verificator = StoryVerificator()

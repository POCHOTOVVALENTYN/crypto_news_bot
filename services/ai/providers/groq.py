"""
Groq AI Provider

Groq предоставляет самый быстрый inference (500+ tokens/sec)
с щедрым бесплатным тиром: 750k токенов/день

API совместим с OpenAI
"""

import logging
import json
from typing import Optional, Dict
from openai import AsyncOpenAI
from openai import OpenAIError

from services.ai.base_provider import AIProvider

logger = logging.getLogger(__name__)


class GroqProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "llama-3.1-70b-versatile"):
        super().__init__(api_key)
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        
    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        """
        Генерация текста через Groq API
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', 0.7),
                max_tokens=kwargs.get('max_tokens', 1000)
            )
            
            result = response.choices[0].message.content
            logger.info(f"✅ Groq Generate Success (model: {self.model})")
            return result
            
        except OpenAIError as e:
            logger.error(f"❌ Groq Generate Error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Groq Unexpected Error: {e}", exc_info=True)
            raise
    
    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        """
        Получение JSON ответа от Groq
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # Добавляем инструкцию для JSON в промпт
            json_instruction = "\n\nОТВЕТЬ СТРОГО В ФОРМАТЕ JSON. Без дополнительных комментариев."
            if schema:
                json_instruction += f"\n\nСхема JSON:\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
            
            messages.append({"role": "user", "content": prompt + json_instruction})
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', 0.3),
                max_tokens=kwargs.get('max_tokens', 2000),
                response_format={"type": "json_object"}  # Принудительный JSON mode
            )
            
            content = response.choices[0].message.content
            
            # Парсим JSON
            try:
                result = json.loads(content)
                logger.info(f"✅ Groq JSON Success (model: {self.model})")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"❌ Groq JSON Parse Error: {e}")
                logger.error(f"Response content: {content}")
                raise ValueError(f"Invalid JSON response: {content[:200]}")
                
        except OpenAIError as e:
            logger.error(f"❌ Groq JSON Error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Groq JSON Unexpected Error: {e}", exc_info=True)
            raise

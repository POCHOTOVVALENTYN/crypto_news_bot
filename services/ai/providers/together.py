"""
Together AI Provider

OpenAI-compatible API
$25 free credits on sign up
"""

import logging
from typing import Optional, Dict
from openai import AsyncOpenAI, OpenAIError
import json

from services.ai.base_provider import AIProvider

logger = logging.getLogger(__name__)

class TogetherProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "meta-llama/Llama-3-70b-chat-hf"):
        super().__init__(api_key)
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.together.xyz/v1"
        )
        
    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
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
            logger.info(f"✅ TogetherAI Generate Success (model: {self.model})")
            return result
            
        except OpenAIError as e:
            logger.error(f"❌ TogetherAI Generate Error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ TogetherAI Unexpected Error: {e}", exc_info=True)
            raise

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            json_instruction = "\n\nOutput strictly in JSON format."
            if schema:
                json_instruction += f"\nSchema:\n{json.dumps(schema, indent=2)}"
            
            messages.append({"role": "user", "content": prompt + json_instruction})
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', 0.2),
                max_tokens=kwargs.get('max_tokens', 2000),
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            try:
                result = json.loads(content)
                logger.info(f"✅ TogetherAI JSON Success")
                return result
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON: {content[:100]}")
                
        except Exception as e:
            logger.error(f"❌ TogetherAI JSON Error: {e}")
            raise

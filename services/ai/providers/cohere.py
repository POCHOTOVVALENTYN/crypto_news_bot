"""
Cohere AI Provider

Free Tier: 1000 calls / month
Model: command-r-plus (excellent RAG and reasoning)
"""

import logging
from typing import Optional, Dict
import cohere
import json

from services.ai.base_provider import AIProvider

logger = logging.getLogger(__name__)

class CohereProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "command-r-plus"):
        super().__init__(api_key)
        self.model = model
        self.client = cohere.AsyncClient(api_key)
        
    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        try:
            # Cohere chat API
            chat_history = []
            if system_prompt:
                # Cohere uses 'preamble' for system prompt in some endpoints, 
                # but in chat API we can put it as first message or preamble
                # For simplicity we put it in preamble if supported or first message
                pass 

            response = await self.client.chat(
                message=prompt,
                model=self.model,
                preamble=system_prompt,
                temperature=kwargs.get('temperature', 0.5),
                max_tokens=kwargs.get('max_tokens', 1000)
            )
            
            logger.info(f"✅ Cohere Generate Success (model: {self.model})")
            return response.text
            
        except Exception as e:
            logger.error(f"❌ Cohere Generate Error: {e}")
            raise

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        try:
            json_prompt = prompt + "\n\nOUPUT JSON ONLY."
            if schema:
                json_prompt += f"\nSchema:\n{json.dumps(schema)}"
            
            response = await self.client.chat(
                message=json_prompt,
                model=self.model,
                preamble=system_prompt,
                temperature=0.1,
                response_format={"type": "json_object"} # Cohere supports this
            )
            
            text = response.text
            try:
                result = json.loads(text)
                logger.info(f"✅ Cohere JSON Success")
                return result
            except json.JSONDecodeError:
                # Fallback implementation if JSON mode fails or returns text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1]
                return json.loads(text.strip())

        except Exception as e:
            logger.error(f"❌ Cohere JSON Error: {e}")
            raise

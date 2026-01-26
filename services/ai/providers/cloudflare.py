"""
Cloudflare Workers AI Provider

Free forever (~100k tokens per day limit)
Uses REST API
"""

import logging
import httpx
import json
from typing import Optional, Dict

from services.ai.base_provider import AIProvider

logger = logging.getLogger(__name__)

class CloudflareProvider(AIProvider):
    def __init__(self, account_id: str, api_token: str, model: str = "@cf/meta/llama-3-8b-instruct"):
        super().__init__(api_token)
        self.account_id = account_id
        self.model = model
        self.api_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
        
    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        full_prompt = prompt
        if system_prompt:
            # Cloudflare chat models usually handle system prompts via messages list
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        else:
            messages = [
                {"role": "user", "content": prompt}
            ]
            
        payload = {
            "messages": messages,
            "max_tokens": kwargs.get('max_tokens', 1000)
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=headers, json=payload, timeout=60.0)
                
            if response.status_code != 200:
                logger.error(f"❌ Cloudflare Error {response.status_code}: {response.text}")
                return None
                
            data = response.json()
            if not data.get("success", False):
                logger.error(f"❌ Cloudflare API Error: {data}")
                return None
                
            result = data["result"]["response"]
            logger.info(f"✅ Cloudflare Generate Success")
            return result
            
        except Exception as e:
            logger.error(f"❌ Cloudflare Unexpected Error: {e}")
            raise

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        # Cloudflare doesn't strictly support JSON mode in all models, so we prompt engineer it
        json_prompt = prompt + "\n\nOUPUT STRICTLY VALID JSON. NO MARKDOWN. NO COMMENTS."
        if schema:
            json_prompt += f"\nSchema:\n{json.dumps(schema)}"
            
        text_result = await self.generate_text(json_prompt, system_prompt, **kwargs)
        if not text_result:
            return None
            
        try:
            # Clean up potential markdown code blocks
            clean_text = text_result.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()
            
            return json.loads(clean_text)
        except Exception as e:
            logger.error(f"❌ Cloudflare JSON Parse Error: {e} | Text: {text_result[:100]}")
            raise

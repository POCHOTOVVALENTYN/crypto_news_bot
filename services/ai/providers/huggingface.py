import asyncio
import json
import logging
import aiohttp
from typing import Optional, Dict

from services.ai.base_provider import AIProvider

class HuggingFaceProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "meta-llama/Meta-Llama-3-8B-Instruct"):
        super().__init__(api_key)
        self.model = model
        self.api_url = f"https://api-inference.huggingface.co/models/{model}"
        self._last_call_time = 0
        self._delay_seconds = 2.0 # Rate limit for free tier is strict
        
        self.headers = {"Authorization": f"Bearer {api_key}"}
        if self.api_key:
             self.logger.info(f"✅ HuggingFace Provider initialized (Model: {self.model})")

    async def _wait_rate_limit(self):
        import time
        current_time = time.time()
        time_since_last = current_time - self._last_call_time
        if time_since_last < self._delay_seconds:
            await asyncio.sleep(self._delay_seconds - time_since_last)
        self._last_call_time = time.time()

    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        if not self.api_key:
            return None
            
        await self._wait_rate_limit()
        
        # Llama 3 format
        full_prompt = prompt
        if system_prompt:
             full_prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        
        payload = {
            "inputs": full_prompt,
            "parameters": {
                "max_new_tokens": kwargs.get("max_tokens", 1024),
                "temperature": kwargs.get("temperature", 0.7),
                "return_full_text": False
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=self.headers, json=payload, timeout=kwargs.get("timeout", 30)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"❌ HF Error {response.status}: {error_text}")
                        if "loading" in error_text.lower():
                            self.logger.warning("⏳ Model is loading, waiting...")
                            await asyncio.sleep(5) # Simple retry logic handled by manager? No, just returning None for specific provider failure
                        return None
                    
                    result = await response.json()
                    if isinstance(result, list) and len(result) > 0:
                        return result[0].get("generated_text", "").strip()
                    elif isinstance(result, dict) and "generated_text" in result:
                        return result.get("generated_text", "").strip()
                        
        except Exception as e:
            self.logger.error(f"❌ HF Request Error: {e}")
            return None
        
        return None

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        # Append instruction to prompt
        json_prompt = f"{prompt}\n\nIMPORTANT: Output ONLY valid JSON."
        text = await self.generate_text(json_prompt, system_prompt, **kwargs)
        if text:
            return self._clean_json_response(text)
        return None

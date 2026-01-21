import asyncio
import logging
from typing import Optional, Dict
from google import genai
import aiohttp

# Monkeypatch for google-genai
if not hasattr(aiohttp, "ClientConnectorDNSError"):
    aiohttp.ClientConnectorDNSError = aiohttp.ClientConnectorError

from services.ai.base_provider import AIProvider

class GeminiProvider(AIProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.client = None
        self.model_name = "gemini-2.5-flash"
        self._last_call_time = 0
        self._delay_seconds = 4.5 # Free tier limit
        
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.logger.info(f"✅ Gemini Provider initialized (Model: {self.model_name})")
            except Exception as e:
                self.logger.error(f"❌ Gemini init error: {e}")

    async def _wait_rate_limit(self):
        import time
        current_time = time.time()
        time_since_last = current_time - self._last_call_time
        if time_since_last < self._delay_seconds:
            await asyncio.sleep(self._delay_seconds - time_since_last)
        self._last_call_time = time.time()

    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        if not self.client:
            return None
        
        await self._wait_rate_limit()
        
        try:
            full_prompt = prompt
            if system_prompt:
                # Gemini recommends putting instructions in the prompt or system_instruction
                # For simplicity with the new API, we can prepend it or pass as config if supported
                # Here we just prepend for safety
                full_prompt = f"{system_prompt}\n\n{prompt}"

            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=full_prompt
                ),
                timeout=kwargs.get("timeout", 90.0)
            )
            
            if hasattr(response, 'text'):
                return response.text
                
        except Exception as e:
            self.logger.error(f"❌ Gemini Generate Error: {e}")
            if "RESOURCE_EXHAUSTED" in str(e):
                self.logger.warning("⚠️ Gemini Quota Exceeded")
            return None
            
        return None

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        text = await self.generate_text(prompt, system_prompt, timeout=kwargs.get("timeout", 30.0))
        if text:
            return self._clean_json_response(text)
        return None

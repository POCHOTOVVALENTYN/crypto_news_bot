import asyncio
import json
from typing import Optional, Dict
from openai import AsyncOpenAI

from services.ai.base_provider import AIProvider

class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        super().__init__(api_key)
        self.model = model
        self.client = None
        self._last_call_time = 0
        self._delay_seconds = 1.0
        
        if self.api_key:
            self.client = AsyncOpenAI(api_key=self.api_key)
            self.logger.info(f"✅ OpenAI Provider initialized (Model: {self.model})")

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
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                timeout=kwargs.get("timeout", 60.0)
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"❌ OpenAI Generate Error: {e}")
            return None

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        if not self.client:
            return None

        await self._wait_rate_limit()

        messages = []
        if system_prompt:
             messages.append({"role": "system", "content": system_prompt + " Output valid JSON."})
        else:
             messages.append({"role": "system", "content": "You are a helpful assistant. Output valid JSON."})
             
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=kwargs.get("timeout", 30.0)
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            self.logger.error(f"❌ OpenAI JSON Error: {e}")
            return None

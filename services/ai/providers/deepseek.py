import asyncio
from typing import Optional, Dict
from openai import AsyncOpenAI

from services.ai.base_provider import AIProvider

class DeepSeekProvider(AIProvider):
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        super().__init__(api_key)
        self.base_url = base_url
        self.client = None
        self.model = "deepseek-chat"
        self._last_call_time = 0
        self._delay_seconds = 0.5
        
        if self.api_key:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self.logger.info(f"✅ DeepSeek Provider initialized")

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
            self.logger.error(f"❌ DeepSeek Generate Error: {e}")
            return None

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        # DeepSeek supports JSON mode via instruction usually, but let's send standard prompt
        # and clean using base class helper
        text = await self.generate_text(prompt, system_prompt, timeout=kwargs.get("timeout", 30.0))
        if text:
            return self._clean_json_response(text)
        return None

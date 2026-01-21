import asyncio
import json
import logging
import aiohttp
from typing import Optional, Dict

from services.ai.base_provider import AIProvider

class OllamaProvider(AIProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        super().__init__(api_key="") # No API key needed
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.api_url = f"{self.base_url}/api/chat"
        # Ollama local is usually fast but depends on hardware. No strict rate limit needed but concurrency might be an issue.
        # We assume queue handles it or OS handles it.
        self.logger.info(f"✅ Ollama Provider initialized (URL: {self.base_url}, Model: {self.model})")

    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "num_predict": kwargs.get("max_tokens", 2048)
            }
        }
        
        try:
             async with aiohttp.ClientSession() as session:
                # Short timeout for connection check, long for generation
                async with session.post(self.api_url, json=payload, timeout=kwargs.get("timeout", 120)) as response:
                    if response.status != 200:
                        self.logger.error(f"❌ Ollama Error {response.status}")
                        return None
                    
                    result = await response.json()
                    if "message" in result:
                        return result["message"].get("content", "").strip()
                        
        except aiohttp.ClientConnectorError:
             self.logger.warning(f"⚠️ Ollama is not reachable at {self.base_url}")
             return None
        except Exception as e:
            self.logger.error(f"❌ Ollama Request Error: {e}")
            return None
        
        return None

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        messages = []
        if system_prompt:
             messages.append({"role": "system", "content": system_prompt + " Output JSON."})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "format": "json", # Ollama supports json mode
            "stream": False,
             "options": {
                "temperature": 0.2
            }
        }

        try:
             async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=kwargs.get("timeout", 60)) as response:
                    if response.status != 200:
                         return None
                    result = await response.json()
                    content = result.get("message", {}).get("content", "")
                    return json.loads(content)
        except Exception as e:
            self.logger.error(f"❌ Ollama JSON Error: {e}")
            # Fallback to text generation and cleaning if JSON mode fails or model doesn't support it well
            return await super().analyze_json(prompt, system_prompt, schema, **kwargs)

import logging
import asyncio
from typing import Optional, Dict, List

from config import (
    GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
    HUGGINGFACE_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL
)
from services.ai.base_provider import AIProvider
from services.ai.providers.gemini import GeminiProvider
from services.ai.providers.openai import OpenAIProvider
from services.ai.providers.deepseek import DeepSeekProvider
from services.ai.providers.huggingface import HuggingFaceProvider
from services.ai.providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)

class AIProviderManager:
    """
    Управляет списком AI провайдеров и реализует логику Fallback.
    """
    def __init__(self):
        self.providers: List[AIProvider] = []
        self._init_providers()
        
    def _init_providers(self):
        # 1. Gemini (Primary)
        if GEMINI_API_KEY:
            self.providers.append(GeminiProvider(GEMINI_API_KEY))
            
        # 2. DeepSeek (Secondary / Fallback #1)
        if DEEPSEEK_API_KEY:
            self.providers.append(DeepSeekProvider(DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL))
            
        # 3. OpenAI (Fallback #2)
        if OPENAI_API_KEY:
            self.providers.append(OpenAIProvider(OPENAI_API_KEY))

        # 4. HuggingFace (Fallback #3)
        if HUGGINGFACE_API_KEY:
            self.providers.append(HuggingFaceProvider(HUGGINGFACE_API_KEY))

        # 5. Ollama (Fallback #4 / Local)
        # Проверяем доступность при инициализации не будем, просто добавим
        if OLLAMA_BASE_URL:
            self.providers.append(OllamaProvider(OLLAMA_BASE_URL, OLLAMA_MODEL))
            
        if not self.providers:
            logger.warning("⚠️ Не найдено ни одного настроенного AI провайдера!")
        else:
            logger.info(f"✅ AI Manager init. Active providers: {[p.name for p in self.providers]}")

    async def generate_text(self, prompt: str, system_prompt: str = None, **kwargs) -> Optional[str]:
        """
        Пытается сгенерировать текст, перебирая провайдеры по очереди.
        """
        errors = []
        for provider in self.providers:
            try:
                # logger.debug(f"🔄 Trying {provider.name}...")
                result = await provider.generate_text(prompt, system_prompt, **kwargs)
                if result:
                    # Добавляем метку провайдера скрыто или явно, если нужно (тут не меняем контент)
                    return result
            except Exception as e:
                errors.append(f"{provider.name}: {str(e)}")
                logger.warning(f"⚠️ {provider.name} failed: {e}")
                continue
        
        logger.error(f"❌ All AI providers failed. Errors: {errors}")
        return None

    async def analyze_json(self, prompt: str, system_prompt: str = None, schema: dict = None, **kwargs) -> Optional[Dict]:
        """
        Пытается получить JSON, перебирая провайдеры.
        """
        errors = []
        for provider in self.providers:
            try:
                # logger.debug(f"🔄 Trying {provider.name} (JSON)...")
                result = await provider.analyze_json(prompt, system_prompt, schema, **kwargs)
                if result:
                    # Inject model info used
                    result['model_used'] = provider.name
                    return result
            except Exception as e:
                errors.append(f"{provider.name}: {str(e)}")
                logger.warning(f"⚠️ {provider.name} failed (JSON): {e}")
                continue
                
        logger.error(f"❌ All AI providers failed (JSON). Errors: {errors}")
        return None

    def get_active_provider_names(self) -> List[str]:
        return [p.name for p in self.providers]

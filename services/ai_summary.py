# services/ai_summary.py
import os
import logging
import json
import google.generativeai as genai
import asyncio
from typing import Optional, Dict

from openai import AsyncOpenAI
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class NewsAnalyzer:
    def __init__(self):
        self.model = None
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.model = self._find_best_model()
            except Exception as e:
                logger.error(f"❌ Критическая ошибка инициализации Gemini: {e}")
        else:
            logger.warning("⚠️ GEMINI_API_KEY не установлен. ИИ отключен.")

    def _find_best_model(self):
        """Ищет доступную модель через API, а не угадывает название"""
        try:
            # Приоритетный список желаемых моделей (от новой к старой)
            preferred_models = [
                'gemini-1.5-flash-002',
                'gemini-1.5-flash-001',
                'gemini-1.5-flash',
                'gemini-1.5-pro-002',
                'gemini-1.5-pro',
            ]

            # Получаем список моделей, доступных ВАШЕМУ ключу
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    name = m.name.replace('models/', '')
                    available_models.append(name)

            logger.info(f"📋 Доступные модели API: {available_models}")

            # Ищем совпадение
            selected_name = None
            for pref in preferred_models:
                if any(pref in avail for avail in available_models):
                    # Берем точное совпадение из доступных, если оно содержит предпочтительное
                    matches = [m for m in available_models if pref in m]
                    selected_name = matches[0]
                    break

            # Если ничего из списка не нашли, берем первую попавшуюся 'gemini'
            if not selected_name:
                fallback = [m for m in available_models if 'gemini' in m]
                if fallback:
                    selected_name = fallback[0]

            if selected_name:
                model = genai.GenerativeModel(selected_name)
                logger.info(f"✅ ИИ Аналитик успешно подключен к: {selected_name}")
                return model
            else:
                logger.error("❌ Не найдено ни одной подходящей модели Gemini")
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка при поиске моделей: {e}")
            return None

    async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
        """Универсальный метод анализа"""
        if not self.model:
            logger.warning("⚠️ Попытка анализа без подключенной модели")
            return None

        prompt = f"""Ты - профессиональный редактор крипто-новостей.
ЗАДАЧА: Сделай краткий пересказ новости на русском языке.
ВХОДНОЙ ТЕКСТ: "{text}"
ТРЕБОВАНИЯ:
1. Заголовок: Цепляющий, но правдивый (до 10 слов).
2. Текст: 2-3 предложения. СУТЬ события. Без воды.
3. Важность: High (влияет на рынок) или Low (проходная).
4. Тональность: Bullish 🟢 / Bearish 🔴 / Neutral ⚪.
5. Монета: Тикер (BTC, ETH) или Market.
ОТВЕТ СТРОГО JSON:
{{
    "ru_title": "Заголовок",
    "ru_summary": "Текст выжимки.",
    "importance": "High",
    "coin": "BTC",
    "sentiment": "Bullish"
}}"""

        try:
            # Делаем вызов с таймаутом
            response = await asyncio.wait_for(
                asyncio.to_thread(self.model.generate_content, prompt),
                timeout=25.0
            )

            if not response.parts:
                logger.error("❌ Пустой ответ от Gemini (Blocked?)")
                return None

            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_json)

        except asyncio.TimeoutError:
            logger.error("❌ Gemini Timeout (25s)")
            return None
        except Exception as e:
            logger.error(f"❌ Gemini Error: {e}. Пробую OpenAI...")
        if self.openai_client:
            return await self._analyze_with_openai(prompt)  # Реализовать этот метод
        return None

    async def process_incoming_news(self, raw_text: str) -> Optional[Dict]:
        """Для Telegram Listener"""
        result = await self.analyze_text(raw_text)
        if result and result.get('importance') == 'High':
            return result
        return None

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        """Для RSS"""
        text = f"{title}. {summary}"
        result = await self.analyze_text(text)

        if result:
            return {
                "clean_title": result.get('ru_title', title),
                "clean_summary": result.get('ru_summary', summary),
                "coin": result.get('coin'),
                "sentiment": result.get('sentiment')
            }
        return None
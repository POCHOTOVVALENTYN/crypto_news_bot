# services/ai_summary.py
import os
import logging
import json
import google.generativeai as genai
import asyncio
from typing import Optional, Dict

logger = logging.getLogger(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class NewsAnalyzer:
    def __init__(self):
        self.model = None
        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                # Ищем модель (упрощенная логика выбора)
                try:
                    self.model = genai.GenerativeModel('gemini-1.5-flash')
                except:
                    self.model = genai.GenerativeModel('gemini-1.5-flash')

                logger.info("✅ ИИ Аналитик готов к работе")
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации Gemini: {e}")

    async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
        """Универсальный метод анализа"""
        if not self.model:
            return None

        prompt = f"""
        Ты - профессиональный крипто-трейдер. Проанализируй текст.

        Текст: "{text}"

        Задачи:
        1. Переведи суть на русский язык (коротко, без воды, стиль Bloomberg).
        2. Определи влияние на рынок: High (важно) или Low (шум).
        3. На какую монету влияет? (Например: BTC, ETH, DOGE, или Market).
        4. Настроение: Bullish (рост) 🟢, Bearish (падение) 🔴, Neutral ⚪️.

        Ответ ТОЛЬКО JSON:
        {{
            "ru_title": "Заголовок (до 10 слов)",
            "ru_summary": "Суть новости (до 2 предложений)",
            "importance": "High/Low",
            "coin": "BTC",
            "sentiment": "Bullish"
        }}
        """

        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_json)
        except Exception as e:
            logger.error(f"AI Error: {e}")
            return None

    # Обертки для совместимости
    async def process_incoming_news(self, raw_text: str) -> Optional[Dict]:
        result = await self.analyze_text(raw_text)
        if result and result.get('importance') == 'High':
            return result
        return None

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        text = f"{title}. {summary}"
        result = await self.analyze_text(text)
        if result:
            return {
                "clean_title": result['ru_title'],
                "clean_summary": result['ru_summary'],
                "coin": result.get('coin'),
                "sentiment": result.get('sentiment')
            }
        return None
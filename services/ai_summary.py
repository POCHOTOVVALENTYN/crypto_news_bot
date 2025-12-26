# services/ai_summary.py
import os
import logging
import json
import asyncio
import google.generativeai as genai
from typing import Optional, Dict

logger = logging.getLogger(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class NewsAnalyzer:
    def __init__(self):
        self.model = None
        self.available = False

        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                # Берем самую стандартную модель, она есть у всех
                self.model = genai.GenerativeModel("gemini-1.5-flash")
                self.available = True
                logger.info("✅ ИИ подключен: gemini-1.5-flash")
            except Exception as e:
                logger.error(f"❌ Ошибка настройки Gemini: {e}")
        else:
            logger.warning("⚠️ Нет GEMINI_API_KEY")

    async def analyze_text(self, text: str) -> Optional[Dict]:
        """Анализ текста через Gemini"""
        if not self.model:
            return None

        prompt = f"""
        Ты крипто-аналитик. Проанализируй новость.
        Текст: {text}

        Верни JSON:
        {{
            "ru_title": "Заголовок на русском (макс 10 слов)",
            "ru_summary": "Суть новости (2 предложения)",
            "importance": "High" или "Low",
            "coin": "BTC" (или тикер),
            "sentiment": "Bullish" или "Bearish" или "Neutral"
        }}
        """

        try:
            # Запускаем в треде, чтобы не блокировать бота
            response = await asyncio.to_thread(self.model.generate_content, prompt)

            # Чистим JSON от лишних символов
            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_json)

        except Exception as e:
            logger.error(f"⚠️ Ошибка Gemini: {e}")
            return None

    # Обертки для совместимости
    async def process_incoming_news(self, raw_text: str) -> Optional[Dict]:
        return await self.analyze_text(raw_text)

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        return await self.analyze_text(f"{title}\n{summary}")
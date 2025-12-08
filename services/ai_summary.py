# services/ai_summary.py
import os
import logging
import json
import google.generativeai as genai
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Получите ключ тут: https://aistudio.google.com/
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class NewsAnalyzer:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash') if GEMINI_API_KEY else None

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        if not self.model:
            return None

        try:
            prompt = f"""
            Ты редактор крипто-канала. Твоя задача - очистить и перевести новость.

            Входящие данные:
            Заголовок: {title}
            Текст: {summary}

            Требования:
            1. Если текст на английском - переведи на русский.
            2. УДАЛИ любые технические ошибки, куски кода, фразы типа "We have identified the issue".
            3. УДАЛИ рекламу и "воды".
            4. Оставь только суть (2-3 предложения).

            Верни ответ строго в JSON:
            {{
                "clean_title": "Заголовок на русском",
                "clean_summary": "Чистая выжимка без мусора",
                "sentiment": "Bullish" или "Bearish" или "Neutral"
            }}
            """

            # Gemini синхронный, но быстрый. Для aiogram лучше обернуть в to_thread,
            # но для 1 запроса раз в 15 минут сойдет и так.
            response = self.model.generate_content(prompt)

            # Чистим ответ от markdown ```json ... ```
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)

        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            return None
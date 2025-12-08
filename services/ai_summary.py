# services/ai_summary.py
import os
import logging
import json
import google.generativeai as genai
from typing import Optional, Dict

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class NewsAnalyzer:
    def __init__(self):
        self.model = None
        if GEMINI_API_KEY:
            # Пытаемся найти рабочую модель
            try:
                # Сначала пробуем Flash (она быстрее)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
            except:
                # Если нет, берем Pro
                self.model = genai.GenerativeModel('gemini-pro')

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        if not self.model:
            return None

        try:
            prompt = f"""
            Ты редактор крипто-канала. Твоя задача - сделать короткую выжимку новости на русском языке.

            Входящие данные:
            Заголовок: {title}
            Текст: {summary}

            Инструкция:
            1. Переведи на русский язык.
            2. Убери "воду", рекламу и технический мусор.
            3. Оставь 2-3 самых важных предложения. Текст должен быть связным.
            4. Не используй вводные фразы типа "Эта новость о том...". Сразу к сути.

            Ответ верни строго в JSON:
            {{
                "clean_title": "Заголовок на русском",
                "clean_summary": "Текст новости (максимум 800 символов)"
            }}
            """

            # Генерируем контент
            # Важно: используем синхронный вызов в треде, чтобы не блокировать бота
            import asyncio
            response = await asyncio.to_thread(self.model.generate_content, prompt)

            # Чистим ответ от markdown
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)

        except Exception as e:
            # Если конкретная модель не найдена, выводим ошибку, но мягко
            if "404" in str(e):
                logger.error("❌ Модель Gemini не найдена. Проверьте API Key или версию библиотеки.")
            else:
                logger.error(f"⚠️ Ошибка Gemini: {e}")
            return None
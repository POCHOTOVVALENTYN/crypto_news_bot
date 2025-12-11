# services/ai_summary.py
import json
import os
import logging
from json import loads
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

                # 1. Получаем список всех доступных моделей для этого ключа
                available_models = [m.name for m in genai.list_models() if
                                    'generateContent' in m.supported_generation_methods]
                logger.info(f"📋 Доступные модели Gemini: {available_models}")

                # 2. Ищем лучшую из доступных
                target_model = None
                # Приоритет моделей (от новой к старой)
                priority_list = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-pro']

                for model_name in priority_list:
                    if model_name in available_models:
                        target_model = model_name
                        break

                # Если ничего из списка нет, берем первую попавшуюся
                if not target_model and available_models:
                    target_model = available_models[0]

                if target_model:
                    self.model = genai.GenerativeModel(target_model)
                    logger.info(f"✅ Выбрана модель Gemini: {target_model}")
                else:
                    logger.error("❌ Нет доступных моделей Gemini для этого ключа")

            except Exception as e:
                logger.error(f"❌ Ошибка инициализации Gemini: {e}")

    async def process_incoming_news(self, raw_text: str) -> Optional[Dict]:
        """
        Фильтрует и переводит входящие молнии.
        Возвращает None, если новость неважная.
        """
        if not self.model:
            return None

        try:
            prompt = f"""
            Ты - элитный крипто-трейдер. Твоя задача - отфильтровать шум и выдать только важные новости.

            Входящий текст: "{raw_text}"

            Алгоритм:
            1. Это ВАЖНАЯ новость для рынка (цена, регулирование, взломы, листинги, Илон Маск про крипту)?
            2. Если НЕТ (реклама, спам, приветствия, вода) -> Верни JSON с "is_relevant": false.
            3. Если ДА -> Переведи на русский язык (сухо, факты, без воды).

            Верни ТОЛЬКО JSON:
            {{
                "is_relevant": true/false,
                "ru_title": "Короткий заголовок (до 10 слов)",
                "ru_summary": "Суть новости (1-2 предложения)"
            }}
            """

            # Запускаем в потоке
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            text = response.text.replace('```json', '').replace('```', '').strip()
            result = json.loads(text)

            if result.get("is_relevant") is True:
                return result
            return None

        except Exception as e:
            logger.error(f"⚠️ Ошибка AI фильтрации: {e}")
            return None


    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        if not self.model:
            return None

        try:
            prompt = f"""
            Ты редактор крипто-новостей. Сделай краткую выжимку на русском.

            Заголовок: {title}
            Текст: {summary}

            Задача:
            1. Переведи на русский.
            2. Оставь только факты, убери "воду".
            3. Максимум 3 предложения.

            Ответ ТОЛЬКО JSON:
            {{
                "clean_title": "Заголовок на русском",
                "clean_summary": "Текст выжимки"
            }}
            """

            # Запускаем в отдельном потоке, чтобы не тормозить бота
            response = await asyncio.to_thread(self.model.generate_content, prompt)

            text = response.text.replace('```json', '').replace('```', '').strip()
            return loads(text)

        except Exception as e:
            logger.error(f"⚠️ Ошибка генерации Gemini: {e}")
            return None
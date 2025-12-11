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

                # ✅ ИСПРАВЛЕНО: Только стабильные названия моделей
                model_names = [
                    'gemini-1.5-flash',
                    'gemini-1.5-flash-latest',
                    'gemini-1.5-pro',
                    'gemini-1.0-pro',
                    'gemini-pro',
                    'gemini-1.5-flash-001'
                ]

                for model_name in model_names:
                    try:
                        # Пробуем инициализировать
                        self.model = genai.GenerativeModel(model_name)
                        logger.info(f"✅ ИИ Аналитик готов: {model_name}")
                        break
                    except Exception as e:
                        logger.debug(f"Модель {model_name} недоступна: {e}")
                        continue

                if not self.model:
                    logger.error("❌ Не удалось загрузить ни одну модель Gemini")

            except Exception as e:
                logger.error(f"❌ Ошибка инициализации Gemini: {e}")
        else:
            logger.warning("⚠️ GEMINI_API_KEY не установлен. ИИ отключен.")

    async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
        """Универсальный метод анализа"""
        if not self.model:
            return None

        # Промпт для качественной выжимки
        prompt = f"""Ты - профессиональный редактор крипто-новостей.

ЗАДАЧА: Сделай краткий пересказ новости на русском языке.

ВХОДНОЙ ТЕКСТ: "{text}"

ТРЕБОВАНИЯ:
1. Заголовок: Цепляющий, но правдивый (до 10 слов).
2. Текст: 2-3 предложения. СУТЬ события. Без воды. Без обрывов на полуслове.
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
            response = await asyncio.wait_for(
                asyncio.to_thread(self.model.generate_content, prompt),
                timeout=20.0
            )

            clean_json = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_json)

        except Exception as e:
            logger.error(f"❌ AI Error: {e}")
            return None

    async def process_incoming_news(self, raw_text: str) -> Optional[Dict]:
        """Для Telegram Listener"""
        result = await self.analyze_text(raw_text)
        # Пропускаем через фильтр только если важность высокая
        if result and result.get('importance') == 'High':
            return result
        return None

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        """Для RSS"""
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
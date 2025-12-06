# services/ai_summary.py
from typing import Optional, Dict
import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def format_sentiment_emoji(sentiment: str) -> str:
    """Конвертируйте sentiment в эмодзи"""
    sentiments = {
        "Bullish": "📈",
        "Bearish": "📉",
        "Neutral": "⚪",
    }
    return sentiments.get(sentiment, "⚪")


class NewsAnalyzer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        """
        Переведите на русский и проанализируйте настроение
        """
        if not self.client:
            return None

        try:
            prompt = f"""Вы профессиональный криптоаналитик и переводчик.

Проанализируйте эту криптовалютную новость:

ЗАГОЛОВОК: {title}
ОПИСАНИЕ: {summary}

Выполните следующие задачи:
1. Переведите заголовок на русский язык (кратко, 5-10 слов)
2. Сделайте краткую выжимку описания на русском (1-2 предложения, максимум 150 символов)
3. Определите настроение рынка: "Bullish" (положительное), "Bearish" (отрицательное) или "Neutral" (нейтральное)
4. Выделите ключевые факты (максимум 2-3 пункта)

Ответьте ТОЛЬКО в формате JSON без пояснений:
{{
    "title_ru": "Переведенный заголовок",
    "summary_ru": "Краткое описание на русском",
    "sentiment": "Bullish/Bearish/Neutral",
    "key_points": ["факт 1", "факт 2"]
}}
"""

            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Вы криптоаналитик. Отвечайте только JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500,
            )

            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)

            logger.info(f"🧠 AI обработка: {result.get('sentiment')}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка OpenAI: {e}")
            return None
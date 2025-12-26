# services/ai_summary.py
import os
import logging
import json
import re
from google import genai
import asyncio
from typing import Optional, Dict

from openai import AsyncOpenAI
from config import OPENAI_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)


class NewsAnalyzer:
    def __init__(self):
        self.client = None
        self.model_name = None
        self.openai_client = None

        # 1. Инициализация OpenAI (Fallback)
        if OPENAI_API_KEY:
            self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        # 2. Инициализация Gemini (Основной) - новый API google.genai
        if GEMINI_API_KEY:
            try:
                self.client = genai.Client(api_key=GEMINI_API_KEY)
                self.model_name = self._find_best_model()
                if self.model_name:
                    logger.info(f"✅ ИИ Аналитик подключен к: {self.model_name}")
            except Exception as e:
                logger.error(f"❌ Критическая ошибка инициализации Gemini: {e}")
        else:
            logger.warning("⚠️ GEMINI_API_KEY не установлен.")

    def _find_best_model(self):
        """Выбирает стабильную модель для free tier"""
        # Используем стабильную модель вместо экспериментальной (экспериментальные могут не работать на free tier)
        logger.info("✅ Используем стабильную модель: gemini-1.5-flash (free tier compatible)")
        return 'gemini-1.5-flash'

    def _clean_json_response(self, text: str) -> Optional[Dict]:
        """Очищает ответ от Markdown и ищет JSON объект"""
        try:
            # 1. Удаляем блоки кода ```json ... ```
            text = text.replace('```json', '').replace('```', '')

            # 2. Ищем JSON структуру с помощью regex (от первой { до последней })
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)

            # 3. Если regex не нашел, пробуем распарсить весь текст
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"⚠️ Ошибка парсинга JSON: {e}. Текст: {text[:50]}...")
            return None

    async def _analyze_with_openai(self, prompt: str) -> Optional[Dict]:
        """Резервный анализ через OpenAI"""
        if not self.openai_client:
            logger.error("❌ OpenAI не настроен, но был вызван как fallback")
            return None

        try:
            logger.info("🤖 Переключаюсь на OpenAI (Fallback)...")
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Дешевая и умная модель
                messages=[
                    {"role": "system", "content": "You are a crypto news editor. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},  # Гарантирует JSON
                timeout=15
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error(f"❌ OpenAI Error: {e}")
            return None

    async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
        """Универсальный метод анализа с улучшенным промптом"""

        prompt = f"""Ты эксперт-аналитик криптовалютного рынка с 10+ летним опытом.

ВХОДНАЯ НОВОСТЬ:
"{text}"

ЗАДАЧА:
1. Определить КРИТИЧЕСКУЮ ВАЖНОСТЬ новости (0-10)
2. Создать цепляющий заголовок на русском (до 10 слов)
3. Написать краткое описание (2-3 предложения, только суть)
4. Определить тональность (Extreme Bullish / Bullish / Neutral / Bearish / Extreme Bearish)
5. Указать монету (BTC, ETH, SOL, или Market)
6. Оценить влияние на рынок (High / Medium / Low)

КРИТЕРИИ ВАЖНОСТИ:
- 10 (Critical): Взломы, банкротства, критические регуляторные решения
- 9 (Very High): ETF одобрения, крупные листинги, институциональные инвестиции >$100M
- 8 (High): Регуляторные новости, средние листинги, заявления ключевых персон
- 7 (High): Крупные транзакции >$50M, важные обновления протоколов
- 6 (Medium): Значимые обновления, средние новости
- 4-5 (Medium): Обычные новости
- 0-3 (Low): Низкая важность, рутинные обновления

ВАЖНО:
- Заголовок должен быть информативным и цепляющим
- Описание - только ключевая информация, без воды
- Тональность должна отражать возможное влияние на цену
- Если новость не относится к крипто - верни importance: "Low"

ФОРМАТ ОТВЕТА (только JSON, без Markdown):
{{
    "importance": "Critical|Very High|High|Medium|Low",
    "importance_score": 10,
    "ru_title": "...",
    "ru_summary": "...",
    "sentiment": "Bullish|Bearish|Neutral|Extreme Bullish|Extreme Bearish",
    "coin": "BTC|ETH|SOL|Market",
    "market_impact": "High|Medium|Low"
}}"""

        # 1. Попытка через Gemini (новый API google.genai)
        if self.client and self.model_name:
            try:
                # Используем новый API google.genai
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=prompt
                    ),
                    timeout=20.0
                )

                # Извлекаем текст из ответа (новый API имеет response.text)
                if hasattr(response, 'text') and response.text:
                    result = self._clean_json_response(response.text)
                    if result:
                        return result
                    logger.warning("⚠️ Gemini вернул некорректный JSON")
                else:
                    logger.warning("⚠️ Gemini вернул пустой ответ")

            except Exception as e:
                logger.error(f"❌ Gemini Error: {e}")

        # 2. Попытка через OpenAI (если Gemini упал или не настроен)
        if self.openai_client:
            return await self._analyze_with_openai(prompt)

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
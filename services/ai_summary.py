# services/ai_summary.py
import os
import logging
import json
import re
import google.generativeai as genai
import asyncio
from typing import Optional, Dict

from openai import AsyncOpenAI
from config import OPENAI_API_KEY, GEMINI_API_KEY

logger = logging.getLogger(__name__)


class NewsAnalyzer:
    def __init__(self):
        self.model = None
        self.openai_client = None

        # 1. Инициализация OpenAI (Fallback)
        if OPENAI_API_KEY:
            self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        # 2. Инициализация Gemini (Основной)
        if GEMINI_API_KEY:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                self.model = self._find_best_model()
            except Exception as e:
                logger.error(f"❌ Критическая ошибка инициализации Gemini: {e}")
        else:
            logger.warning("⚠️ GEMINI_API_KEY не установлен.")

    def _find_best_model(self):
        """Ищет доступную модель через API"""
        try:
            # Приоритетный список (свежие и быстрые модели)
            preferred_models = [
                'gemini-2.0-flash',  # Если доступна 2.0
                'gemini-1.5-flash',
                'gemini-1.5-flash-002',
                'gemini-1.5-pro',
            ]

            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    name = m.name.replace('models/', '')
                    available_models.append(name)

            logger.info(f"📋 Доступные модели API: {available_models}")

            # Ищем лучшее совпадение
            selected_name = None
            for pref in preferred_models:
                # Ищем точное или частичное совпадение
                matches = [m for m in available_models if pref in m]
                if matches:
                    # Сортируем, чтобы найти самую короткую (точную) версию, или берем первую
                    selected_name = matches[0]
                    break

            # Fallback: берем любую флеш или про
            if not selected_name:
                fallback = [m for m in available_models if 'flash' in m or 'pro' in m]
                if fallback:
                    selected_name = fallback[0]

            if selected_name:
                model = genai.GenerativeModel(selected_name)
                logger.info(f"✅ ИИ Аналитик подключен к: {selected_name}")
                return model

            logger.error("❌ Подходящая модель Gemini не найдена")
            return None

        except Exception as e:
            logger.error(f"❌ Ошибка поиска моделей: {e}")
            return None

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
        """Универсальный метод анализа с Fallback"""

        prompt = f"""Ты редактор крипто-новостей.
ЗАДАЧА: Сделай краткий пересказ новости на русском.

ВХОДНОЙ ТЕКСТ: "{text}"

ТРЕБОВАНИЯ:
1. Заголовок: Цепляющий, правдивый (до 10 слов).
2. Текст: 2-3 предложения. Только суть.
3. Важность: High или Low.
4. Тональность: Bullish 🟢 / Bearish 🔴 / Neutral ⚪.
5. Монета: Тикер (BTC, ETH) или Market.

ВАЖНО: ОТВЕТ ТОЛЬКО В ФОРМАТЕ JSON. БЕЗ MARKDOWN.
{{
    "ru_title": "...",
    "ru_summary": "...",
    "importance": "High",
    "coin": "BTC",
    "sentiment": "Bullish"
}}"""

        # 1. Попытка через Gemini
        if self.model:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(self.model.generate_content, prompt),
                    timeout=20.0
                )

                if response.parts:
                    result = self._clean_json_response(response.text)
                    if result: return result
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
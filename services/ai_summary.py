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
        self._last_api_call_time = 0  # Для rate limiting
        self._min_delay_seconds = 1.5  # Минимальная задержка между запросами (1.5 секунды)

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
        # Для нового API google-genai пробуем несколько вариантов имен моделей
        # Попробуем последнюю доступную модель
        model_name = 'gemini-2.5-flash'  # Последняя версия Flash модели
        logger.info(f"✅ Используем модель: {model_name} (free tier compatible)")
        # Если эта модель не работает, будет fallback на OpenAI
        return model_name

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

        # Rate limiting для OpenAI тоже
        await self._rate_limit_wait()

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

    async def _rate_limit_wait(self):
        """Ожидание для соблюдения rate limiting"""
        import time
        current_time = time.time()
        time_since_last_call = current_time - self._last_api_call_time
        
        if time_since_last_call < self._min_delay_seconds:
            wait_time = self._min_delay_seconds - time_since_last_call
            await asyncio.sleep(wait_time)
        
        self._last_api_call_time = time.time()

    async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
        """Универсальный метод анализа с улучшенным промптом"""
        
        # Rate limiting: задержка между запросами
        await self._rate_limit_wait()

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
                # Используем правильный формат для нового API google.genai
                # Синхронный вызов через asyncio.to_thread
                def _generate():
                    return self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt
                    )
                
                response = await asyncio.wait_for(
                    asyncio.to_thread(_generate),
                    timeout=20.0
                )

                # Извлекаем текст из ответа (пробуем разные способы)
                response_text = None
                if hasattr(response, 'text'):
                    response_text = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    # Альтернативный способ извлечения текста
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content'):
                        content = candidate.content
                        if hasattr(content, 'parts') and content.parts:
                            first_part = content.parts[0]
                            if hasattr(first_part, 'text'):
                                response_text = first_part.text
                
                if response_text:
                    result = self._clean_json_response(response_text)
                    if result:
                        return result
                    logger.warning("⚠️ Gemini вернул некорректный JSON")
                else:
                    logger.warning(f"⚠️ Gemini вернул пустой ответ. Response type: {type(response)}")

            except Exception as e:
                error_str = str(e)
                # Детальное логирование ошибки
                if '404' in error_str or 'NOT_FOUND' in error_str:
                    logger.error(f"❌ Gemini Error: Модель не найдена. Проверьте имя модели: {self.model_name}")
                    logger.error(f"💡 Попробуйте другую модель или проверьте документацию Google AI")
                elif '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                    logger.error(f"❌ Gemini Error: Превышена квота API. Fallback на OpenAI...")
                else:
                    logger.error(f"❌ Gemini Error: {e}")
                # Fallback на OpenAI произойдет автоматически ниже

        # 2. Попытка через OpenAI (если Gemini упал или не настроен)
        if self.openai_client:
            return await self._analyze_with_openai(prompt)

        return None

    async def process_incoming_news(self, raw_text: str) -> Optional[Dict]:
        """Для Telegram Listener - фильтрует только важные новости"""
        result = await self.analyze_text(raw_text)
        if not result:
            return None
        
        # Проверяем важность новости (Critical, Very High, High)
        importance = result.get('importance', '').lower()
        importance_score = result.get('importance_score', 0)
        
        # Принимаем новости с высокой важностью
        if importance in ['critical', 'very high', 'high']:
            return result
        
        # Или если importance_score >= 7 (высокая важность)
        if isinstance(importance_score, (int, float)) and importance_score >= 7:
            return result
        
        # Все остальные отфильтровываем
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
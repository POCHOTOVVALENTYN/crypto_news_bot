# services/ai_summary.py
import os
import logging
import json
import re
from google import genai
import asyncio
from typing import Optional, Dict

from openai import AsyncOpenAI
from config import OPENAI_API_KEY, GEMINI_API_KEY, MISTRAL_API_KEY

logger = logging.getLogger(__name__)


class NewsAnalyzer:
    def __init__(self):
        self.client = None
        self.model_name = None
        self.openai_client = None
        self.mistral_client = None
        # Rate limiting для разных провайдеров
        self._last_gemini_call_time = 0
        self._last_mistral_call_time = 0
        self._last_openai_call_time = 0
        self._gemini_delay_seconds = 4.5  # Gemini free tier: 15 RPM = минимум 4 секунды
        self._mistral_delay_seconds = 1.1  # Mistral free tier: 1 RPS = минимум 1 секунда
        self._openai_delay_seconds = 1.0  # OpenAI (платный, более либеральные лимиты)
        # ✅ ИСПРАВЛЕНО: Семафор для ограничения одновременных AI запросов (максимум 2)
        self._ai_request_semaphore = asyncio.Semaphore(2)

        # 1. Инициализация OpenAI (Fallback #2)
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
        
        # 3. Инициализация Mistral AI (Fallback #1) - ВРЕМЕННО ОТКЛЮЧЕН
        # ⚠️ Mistral AI отключен из-за конфликтов зависимостей:
        # - mistralai требует pydantic>=2.9.0 (несовместимо с aiogram 3.3.0)
        # - mistralai<1.3.0 требует httpx<0.28.0 (несовместимо с google-genai)
        # Для использования Mistral AI потребуется обновить aiogram до версии, поддерживающей pydantic>=2.9.0
        if False and MISTRAL_API_KEY:  # Временно отключено
            try:
                from mistralai import Mistral
                self.mistral_client = Mistral(api_key=MISTRAL_API_KEY)
                logger.info("✅ Mistral AI подключен (Fallback #1)")
            except ImportError:
                logger.warning("⚠️ mistralai не установлен, Mistral AI недоступен. Установите: pip install mistralai")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка инициализации Mistral AI: {e}")

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

    async def _rate_limit_wait_gemini(self):
        """Ожидание для соблюдения Gemini rate limiting (4.5 сек)"""
        import time
        current_time = time.time()
        time_since_last_call = current_time - self._last_gemini_call_time
        
        if time_since_last_call < self._gemini_delay_seconds:
            wait_time = self._gemini_delay_seconds - time_since_last_call
            await asyncio.sleep(wait_time)
        
        self._last_gemini_call_time = time.time()

    async def _rate_limit_wait_mistral(self):
        """Ожидание для соблюдения Mistral rate limiting (1.1 сек)"""
        import time
        current_time = time.time()
        time_since_last_call = current_time - self._last_mistral_call_time
        
        if time_since_last_call < self._mistral_delay_seconds:
            wait_time = self._mistral_delay_seconds - time_since_last_call
            await asyncio.sleep(wait_time)
        
        self._last_mistral_call_time = time.time()

    async def _rate_limit_wait_openai(self):
        """Ожидание для соблюдения OpenAI rate limiting (1 сек)"""
        import time
        current_time = time.time()
        time_since_last_call = current_time - self._last_openai_call_time
        
        if time_since_last_call < self._openai_delay_seconds:
            wait_time = self._openai_delay_seconds - time_since_last_call
            await asyncio.sleep(wait_time)
        
        self._last_openai_call_time = time.time()

    async def _analyze_with_mistral(self, prompt: str) -> Optional[Dict]:
        """Анализ через Mistral AI (Fallback #1)"""
        if not self.mistral_client:
            return None

        # Rate limiting для Mistral
        await self._rate_limit_wait_mistral()

        try:
            logger.info("🔮 Переключаюсь на Mistral AI (Fallback #1)...")
            # Mistral использует синхронный API, оборачиваем в executor
            def _generate():
                response = self.mistral_client.chat.complete(
                    model="mistral-large-latest",  # Лучшая модель для анализа
                    messages=[
                        {"role": "system", "content": "You are a crypto news editor. Output only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                return response.choices[0].message.content
            
            response_text = await asyncio.wait_for(
                asyncio.to_thread(_generate),
                timeout=20.0
            )
            
            if response_text:
                result = self._clean_json_response(response_text)
                if result:
                    return result
                logger.warning("⚠️ Mistral вернул некорректный JSON")
        except Exception as e:
            error_str = str(e)
            if '429' in error_str or 'rate limit' in error_str.lower():
                logger.error(f"❌ Mistral Error: Превышен rate limit. Fallback на OpenAI...")
            else:
                logger.error(f"❌ Mistral Error: {e}")
            return None

    async def _analyze_with_openai(self, prompt: str) -> Optional[Dict]:
        """Резервный анализ через OpenAI (Fallback #2)"""
        if not self.openai_client:
            return None

        # Rate limiting для OpenAI
        await self._rate_limit_wait_openai()

        try:
            logger.info("🤖 Переключаюсь на OpenAI (Fallback #2)...")
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Дешевая и умная модель
                messages=[
                    {"role": "system", "content": "You are a crypto news editor. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},  # Гарантирует JSON
                timeout=10  # ✅ ИСПРАВЛЕНО: Уменьшен таймаут с 15 до 10 секунд
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.error(f"❌ OpenAI Error: {e}")
            return None

    async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
        """
        Универсальный метод анализа с улучшенным промптом.
        ✅ ИСПРАВЛЕНО: Добавлен общий таймаут 30 секунд для всей операции.
        """
        # ✅ ИСПРАВЛЕНО: Общий таймаут для всей операции анализа (30 секунд)
        try:
            return await asyncio.wait_for(
                self._analyze_text_internal(text, context),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.error("❌ AI анализ превысил общий таймаут (30 секунд)")
            return None
    
    async def _analyze_text_internal(self, text: str, context: str = "news") -> Optional[Dict]:
        """Внутренний метод анализа (без общего таймаута, используется внутри analyze_text)"""
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

        # 1. Попытка через Gemini (новый API google.genai) - ОСНОВНОЙ
        if self.client and self.model_name:
            try:
                # Rate limiting для Gemini (4.5 сек)
                await self._rate_limit_wait_gemini()
                
                # Используем правильный формат для нового API google.genai
                # Синхронный вызов через asyncio.to_thread
                def _generate():
                    return self.client.models.generate_content(
                        model=self.model_name,
                        contents=prompt
                    )
                
                # ✅ ИСПРАВЛЕНО: Уменьшен таймаут с 20 до 15 секунд
                response = await asyncio.wait_for(
                    asyncio.to_thread(_generate),
                    timeout=15.0
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
                    logger.error(f"❌ Gemini Error: {e}. Fallback на OpenAI...")
                # Fallback на Mistral произойдет автоматически ниже

        # 2. Попытка через Mistral AI (Fallback #1) - ВРЕМЕННО ОТКЛЮЧЕН
        # if self.mistral_client:
        #     result = await self._analyze_with_mistral(prompt)
        #     if result:
        #         return result

        # 3. Попытка через OpenAI (Fallback #2) - последний резерв
        if self.openai_client:
            result = await self._analyze_with_openai(prompt)
            if result:
                return result

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
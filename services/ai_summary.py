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

                # ✅ ИСПРАВЛЕНО: Правильные названия моделей
                # Пробуем разные модели по порядку
                model_names = [
                    'gemini-1.5-flash-latest',  # Новая версия
                    'gemini-1.5-flash',
                    'gemini-pro',  # Fallback
                    'gemini-1.0-pro'  # Старая версия
                ]

                for model_name in model_names:
                    try:
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
            logger.debug("ИИ не доступен, пропускаем анализ")
            return None

        # ✅ УЛУЧШЕН ПРОМПТ: Более четкие инструкции
        prompt = f"""Ты - профессиональный крипто-аналитик Bloomberg Terminal.

ЗАДАЧА: Проанализируй новость и верни ТОЛЬКО JSON (без текста до/после).

ТЕКСТ: "{text}"

ИНСТРУКЦИЯ:
1. Переведи на русский (краткий заголовок, 8-12 слов)
2. Выжимка сути (2-3 предложения, без воды)
3. Важность: High (влияет на цену) или Low (шум)
4. Монета: BTC, ETH, SOL, DOGE, XRP, BNB или Market (общее)
5. Настроение: Bullish 🟢, Bearish 🔴, Neutral ⚪

ФОРМАТ ОТВЕТА:
{{
    "ru_title": "Краткий заголовок",
    "ru_summary": "Суть новости в 2-3 предложениях",
    "importance": "High",
    "coin": "BTC",
    "sentiment": "Bullish"
}}

ТОЛЬКО JSON БЕЗ ЛИШНЕГО ТЕКСТА!"""

        try:
            # ✅ УЛУЧШЕНА ОБРАБОТКА: Добавлен retry и timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(self.model.generate_content, prompt),
                timeout=15.0  # 15 секунд максимум
            )

            # Чистим ответ от markdown
            clean_json = response.text.strip()

            # Убираем возможные обертки
            if clean_json.startswith('```'):
                clean_json = clean_json.split('```')[1]
                if clean_json.startswith('json'):
                    clean_json = clean_json[4:]

            clean_json = clean_json.strip()

            result = json.loads(clean_json)

            # Валидация результата
            required_keys = ['ru_title', 'ru_summary', 'importance', 'coin', 'sentiment']
            if all(key in result for key in required_keys):
                return result
            else:
                logger.warning(f"⚠️ ИИ вернул неполный ответ: {result.keys()}")
                return None

        except asyncio.TimeoutError:
            logger.error("⏱️ ИИ не ответил за 15 секунд")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"❌ ИИ вернул невалидный JSON: {e}")
            logger.debug(f"Ответ: {response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"❌ AI Error: {e}")
            return None

    async def process_incoming_news(self, raw_text: str) -> Optional[Dict]:
        """
        Для Telegram Listener: строгая фильтрация
        Возвращает результат ТОЛЬКО если importance=High
        """
        result = await self.analyze_text(raw_text, context="insider")

        if result and result.get('importance') == 'High':
            logger.info(f"✅ ИИ: Важная новость о {result['coin']}")
            return result

        logger.debug("ИИ: Новость не важна (Low)")
        return None

    async def translate_and_analyze(self, title: str, summary: str) -> Optional[Dict]:
        """
        Для RSS: всегда обрабатываем (нет фильтрации по важности)
        """
        text = f"{title}. {summary}"
        result = await self.analyze_text(text, context="rss")

        if result:
            return {
                "clean_title": result['ru_title'],
                "clean_summary": result['ru_summary'],
                "coin": result.get('coin'),
                "sentiment": result.get('sentiment')
            }

        # Если ИИ не сработал - возвращаем оригинал
        return {
            "clean_title": title[:100],
            "clean_summary": summary[:400],
            "coin": "Market",
            "sentiment": "Neutral"
        }
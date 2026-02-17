import logging
import asyncio
from typing import Optional, Dict, List

# Импортируем менеджер провайдеров
from services.ai.manager import AIProviderManager
# Импортируем настройки
from config import config

logger = logging.getLogger(__name__)


class NewsAnalyzer:
    def __init__(self):
        # Инициализируем менеджер, который сам поднимет всех провайдеров
        self.ai_manager = AIProviderManager()
        
    async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
        """
        Анализирует новость и возвращает JSON с важностью и саммари.
        Использует каскад провайдеров через AIProviderManager.
        """
        
        # 1. Формируем промпт
        prompt = f"""Ты эксперт-аналитик криптовалютного рынка с 10+ летним опытом.

ВХОДНАЯ НОВОСТЬ:
"{text}"

ЗАДАЧА:
1. Определить КРИТИЧЕСКУЮ ВАЖНОСТЬ новости (0-10)
2. Создать цепляющий заголовок на русском (до 10 слов)
3. Написать краткое описание (2-3 предложения, только суть)
4. Указать монету (BTC, ETH, SOL, или Market)
5. ОЦЕНИТЬ ВЛИЯНИЕ:
6. category: Bitcoin | Ethereum | DeFi | NFT | Regulation | Market | Altcoins | Security | Other
7. sentiment_score: от -10 (Total Collapse) до +10 (To The Moon). 0 = Neutral.
8. why_it_matters: 1 предложение, объясняющее почему это важно для инвестора.
9. market_impact: High / Medium / Low

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
- Если новость не относится к крипто - верни importance: "Low"
- НЕ ИСПОЛЬЗУЙ MARKDOWN СИНТАКСИС ([text](url), **bold**, _italic_)
- Используй только обычный текст без форматирования
- Не добавляй квадратные скобки [] в заголовок или описание

ФОРМАТ ОТВЕТА (только JSON, без Markdown):
{{
    "importance": "Critical|Very High|High|Medium|Low",
    "importance_score": 10,
    "ru_title": "...",
    "ru_summary": "...",
    "coin": "BTC|ETH|SOL|Market",
    "category": "Bitcoin|Ethereum|DeFi|NFT|Regulation|Market|Altcoins|Security|Other",
    "sentiment_score": 7,
    "why_it_matters": "...",
    "market_impact": "High|Medium|Low"
}}"""

        # 2. Делегируем выполнение менеджеру
        # Менеджер сам попробует Gemini -> DeepSeek -> OpenAI
        result = await self.ai_manager.analyze_json(
            prompt=prompt, 
            system_prompt="You are a crypto news editor. Output only valid JSON. Never use Markdown syntax in text fields."
        )
        
        return result

    async def generate_digest(self, news_list: list[Dict], period_name: str = "сутки") -> Optional[str]:
        """
        Генерирует дайджест новостей.
        Если AI не справился - фоллбэк на Simple Digest.
        """
        if not news_list:
            return None

        # Подготовка списка новостей для промпта
        input_text = ""
        # Получаем channel_id для формирования ссылок
        channel_id = str(config.telegram_channel_id)
        if channel_id.startswith("-100"):
            channel_id = channel_id[4:]

        for i, news in enumerate(news_list[:50]):
            title = news.get("title", "Без заголовка")
            summary = news.get("summary", "")
            
            msg_id = news.get("telegram_message_id")
            if msg_id and channel_id:
                url = f"https://t.me/c/{channel_id}/{msg_id}"
            else:
                url = news.get("url", "#")
            
            input_text += f"{i+1}. {title}\nСсылка: {url}\nСуть: {summary}\n\n"

        prompt = f"""Ты — профессиональный аналитик и редактор крипто-новостного канала.
Твоя задача — составить ИТОГОВЫЙ ДАЙДЖЕСТ ЗА {period_name} ("Mega-Recap").

ВОТ СПИСОК НОВОСТЕЙ ССЫЛКАМИ И СУТЬЮ:
{input_text}

ТРЕБОВАНИЯ К ФОРМАТУ (СТРОГО HTML, без Markdown):

<b>📅 Итоги дня: Главное за 24 часа</b>

<b>📈 Настроение рынка:</b>
[Здесь напиши 2-3 предложения с общим анализом: что происходило на рынке, рос он или падал, какие были главные тренды. Сделай вывод о настроении инвесторов.]

<b>🔥 Топ событий:</b>

1. ЭМОДЗИ <a href="URL_1"><b>Заголовок первой важной новости</b></a>
[Краткое описание сути новости в 1 предложение. Почему это важно?]

2. ЭМОДЗИ <a href="URL_2"><b>Заголовок второй новости</b></a>
[Краткое описание...]

... (Всего 5-7 самых важных новостей)

<b>📊 Вывод:</b> [Короткая финальная фраза-напутствие или прогноз на завтра]

ВАЖНО:
- Используй теги <b>, <i>, <a href="...">. Не используй Markdown (**bold**).
- Ссылки вшивай в заголовки.
- Выбирай только САМОЕ важное. Группируй похожие новости.
- Эмодзи должны соответствовать теме новости.
"""
        
        # 1. Пробуем через AI
        result_text = await self.ai_manager.generate_text(
            prompt=prompt,
            system_prompt="You are a crypto market analyst. Output valid HTML.",
            timeout=180.0 # Дайджест может генерироваться долго
        )
        
        if result_text:
            # Очистка от markdown блоков, если они есть
            clean_text = result_text.replace("```html", "").replace("```", "").strip()
            # Убираем возможные лишние теги html/body если модель их добавила
            clean_text = clean_text.replace("<html>", "").replace("</html>", "").replace("<body>", "").replace("</body>", "")
            return clean_text
            
        # 2. Fallback на Simple Digest
        logger.warning("⚠️ Все AI сервисы недоступны. Генерирую простой дайджест (Simple Mode).")
        return self._generate_simple_digest(news_list, period_name, channel_id)

    def _generate_simple_digest(self, news_list: list, period_name: str, channel_id: Optional[str]) -> str:
        """
        Генерация простого дайджеста без участия AI.
        Исправленная и укрепленная версия.
        """
        digest = f"<b>📅 Итоги дня: Главное за {period_name}</b> (Simple Mode)\n\n"
        
        digest += "<b>📈 Настроение рынка:</b>\n"
        digest += "Данные недоступны (AI сервис временно отключен).\n\n"
        
        digest += "<b>🔥 Топ событий:</b>\n\n"
        
        # Берем 7 новостей
        count = 0
        for news in news_list:
            if count >= 7:
                break
                
            title = news.get("title", "Без заголовка")
            msg_id = news.get("telegram_message_id")
            original_url = news.get("url")
            
            # Логика ссылок:
            # 1. Если есть msg_id и channel_id -> внутренняя ссылка
            # 2. Если нет -> внешняя ссылка (original_url)
            # 3. Если и ее нет -> пропускаем или ставим заглушку (лучше пропустить)
            
            url = None
            if msg_id and channel_id:
                url = f"https://t.me/c/{channel_id}/{msg_id}"
            elif original_url and original_url.startswith("http"):
                url = original_url
            
            if not url:
                logger.warning(f"⚠️ Пропуск новости в Simple Digest (нет ссылки): {title}")
                continue
            
            # Подбираем эмодзи по ключевым словам (примитивно)
            emoji = "📰"
            t_lower = title.lower()
            if "bitcoin" in t_lower or "btc" in t_lower: emoji = "💎"
            elif "ethereum" in t_lower or "eth" in t_lower: emoji = "🔷"
            elif "solana" in t_lower or "sol" in t_lower: emoji = "🟣"
            elif "sec" in t_lower or "суд" in t_lower: emoji = "⚖️"
            elif "рост" in t_lower or "to the moon" in t_lower: emoji = "🚀"
            elif "падение" in t_lower or "обвал" in t_lower: emoji = "📉"
            elif "hack" in t_lower or "взлом" in t_lower: emoji = "🚨"
            
            digest += f"{emoji} <a href=\"{url}\"><b>{title}</b></a>\n\n"
            count += 1
            
        digest += f"<b>📊 Вывод:</b> {len(news_list)} важных новостей за этот период."
        return digest
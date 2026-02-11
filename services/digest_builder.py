"""
Создание периодических дайджестов новостей
Собирает новости за N часов, группирует и публикует сводку
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import bot
from config import config
from database import db
from services.ai_summary import NewsAnalyzer
from services.content_deduplicator import ContentDeduplicator
from services.message_builder import get_multiple_crypto_prices, FearGreedIndexTracker

logger = logging.getLogger(__name__)


class DigestBuilder:
    """Создание периодических дайджестов новостей"""
    
    # Интервал дайджеста (3 часа по требованию пользователя)
    DIGEST_INTERVAL_HOURS = 3
    
    # Минимальное количество новостей для публикации дайджеста
    MIN_NEWS_COUNT = 2
    
    # Категории новостей
    CATEGORIES = {
        'breaking': {'emoji': '🔥', 'title': 'МОЛНИЕНОСНЫЕ НОВОСТИ'},
        'main_events': {'emoji': '📰', 'title': 'ГЛАВНЫЕ СОБЫТИЯ'},
        'market': {'emoji': '💼', 'title': 'РЫНОК И РЕГУЛЯЦИИ'},
        'tech': {'emoji': '🛠️', 'title': 'ТЕХНОЛОГИИ И ПРОТОКОЛЫ'},
        'other': {'emoji': '📌', 'title': 'ДРУГИЕ НОВОСТИ'}
    }
    
    def __init__(self):
        self.ai_analyzer = NewsAnalyzer()
    
    async def build_and_publish_digest(self):
        """
        Главная функция: собрать и опубликовать дайджест
        
        Вызывается планировщиком каждые 3 часа
        """
        try:
            logger.info(f"📰 Начало сборки {self.DIGEST_INTERVAL_HOURS}-часового дайджеста...")
            
            # 1. Получить новости за период
            news_list = await self._get_digest_news()
            
            if len(news_list) < self.MIN_NEWS_COUNT:
                logger.info(f"⏭️ Недостаточно новостей ({len(news_list)} < {self.MIN_NEWS_COUNT}), пропускаем дайджест")
                return
            
            logger.info(f"📊 Собрано {len(news_list)} новостей для дайджеста")
            
            # 2. Категоризация и дедупликация
            categorized_news = await self._categorize_and_deduplicate(news_list)
            
            # 3. Форматирование дайджеста
            digest_html = await self._format_digest(categorized_news)
            
            # 4. Публикация
            message_id = await self._publish_digest(digest_html, len(news_list))
            
            if message_id:
                # 5. Сохранить информацию о дайджесте
                await self._save_digest_info(message_id, news_list)
                logger.info(f"✅ Дайджест успешно опубликован (MsgID: {message_id})")
            
        except Exception as e:
            logger.error(f"❌ Ошибка build_and_publish_digest: {e}", exc_info=True)
    
    async def _get_digest_news(self) -> List[Dict]:
        """
        Получить новости для дайджеста
        
        ВАЖНО: Выбираем ВСЕ непубликованные новости (не только за последние N часов),
        иначе старые новости никогда не будут опубликованы!
        """
        try:
            async with db.conn.execute(
                """
                SELECT * FROM news
                WHERE posted_to_telegram = 0
                AND digest_batch_id IS NULL
                AND priority < 9
                ORDER BY priority DESC, added_at DESC
                LIMIT 20
                """,
                ()
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                rows = await cursor.fetchall()
                
                logger.info(f"📊 Найдено {len(rows)} новостей для дайджеста (не опубликовано)")
                return rows
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения новостей для дайджеста: {e}", exc_info=True)
            return []
    
    async def _categorize_and_deduplicate(self, news_list: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Категоризировать новости и применить дедупликацию
        
        Returns:
            Словарь {категория: [новости]}
        """
        categorized = {cat: [] for cat in self.CATEGORIES.keys()}
        
        for news_item in news_list:
            # 1. Определить категорию
            category = await self._categorize_news(news_item)
            
            # 2. Применить дедупликацию
            dedup_result = await ContentDeduplicator.smart_summarize(
                title=news_item['title'],
                description=news_item.get('summary', ''),
                key_points=None,  # Для дайджеста ключевые моменты не используем
                dedup_threshold=0.6
            )
            
            # Обновляем новость дедуплицированным контентом
            news_item['dedup_title'] = dedup_result['title']
            news_item['dedup_content'] = dedup_result['content']
            
            categorized[category].append(news_item)
        
        # Удаляем пустые категории
        categorized = {k: v for k, v in categorized.items() if v}
        
        return categorized
    
    async def _categorize_news(self, news_item: Dict) -> str:
        """
        Определить категорию новости с помощью AI
        
        Returns:
            Ключ категории из CATEGORIES
        """
        try:
            # Используем priority и ключевые слова для категоризации
            title_lower = news_item['title'].lower()
            summary_lower = news_item.get('summary', '').lower()
            
            # Простая категоризация по ключевым словам
            # (можно заменить на AI, но это быстрее)
            
            if news_item['priority'] >= 8:
                return 'main_events'
            
            # Рынок и регуляции
            market_keywords = ['sec', 'регулятор', 'запрет', 'санкции', 'etf', 'биржа', 'цена', 'курс']
            if any(kw in title_lower or kw in summary_lower for kw in market_keywords):
                return 'market'
            
            # Технологии
            tech_keywords = ['хардфорк', 'обновление', 'протокол', 'сеть', 'майнинг', 'консенсус', 'блокчейн']
            if any(kw in title_lower or kw in summary_lower for kw in tech_keywords):
                return 'tech'
            
            # По умолчанию
            return 'other'
            
        except Exception as e:
            logger.debug(f"Ошибка категоризации: {e}")
            return 'other'
    
    async def _format_digest(self, categorized_news: Dict[str, List[Dict]]) -> str:
        """
        Форматировать дайджест в HTML
        
        Args:
            categorized_news: {категория: [новости]}
            
        Returns:
            HTML-текст дайджеста
        """
        now = datetime.now()
        
        # Заголовок
        lines = [
            f"📰 <b>ДАЙДЖЕСТ КРИПТОНОВОСТЕЙ</b>",
            f"⏰ {now.strftime('%d.%m.%Y %H:%M')}",
            ""
        ]
        
        # Категории
        for category, news_items in categorized_news.items():
            if not news_items:
                continue
            
            cat_info = self.CATEGORIES[category]
            lines.append(f"{cat_info['emoji']} <b>{cat_info['title']}</b>")
            
            for news_item in news_items[:5]:  # Максимум 5 новостей на категорию
                # Укороченный заголовок
                title = news_item['dedup_title'][:100]
                if len(news_item['dedup_title']) > 100:
                    title += "..."
                
                # Встраиваем ссылку нативно в Telegram
                url = news_item['url']
                
                # Проверяем metadata для Telegram источников
                metadata_str = news_item.get('metadata')
                if metadata_str:
                    try:
                        metadata = json.loads(metadata_str)
                        if metadata.get('is_telegram_source') and metadata.get('telegram_link'):
                            url = metadata['telegram_link']
                    except:
                        pass
                
                lines.append(f"• <a href=\"{url}\">{title}</a>")
            
            lines.append("")  # Пустая строка между категориями
        
        # Разделитель
        lines.append("───────────────────────")
        
        # Цены и индекс страха
        try:
            prices = await get_multiple_crypto_prices()
            if prices:
                lines.append("💰 <b>Цены (24h):</b>")
                
                if "bitcoin" in prices:
                    p = prices['bitcoin']
                    emoji = "🚀" if p.get('change', 0) >= 0 else "🩸"
                    lines.append(f"{emoji} BTC: <b>${p['price']:,.0f}</b> ({p['change']:+.2f}%)")
                
                if "ethereum" in prices:
                    p = prices['ethereum']
                    emoji = "🚀" if p.get('change', 0) >= 0 else "🩸"
                    lines.append(f"{emoji} ETH: <b>${p['price']:,.0f}</b> ({p['change']:+.2f}%)")
                
                if "solana" in prices:
                    p = prices['solana']
                    emoji = "🚀" if p.get('change', 0) >= 0 else "🩸"
                    lines.append(f"{emoji} SOL: <b>${p['price']:.2f}</b> ({p['change']:+.2f}%)")
                
                lines.append("")
        except Exception as e:
            logger.debug(f"Ошибка получения цен: {e}")
        
        try:
            fear_greed = await FearGreedIndexTracker.get_fear_greed_index()
            if fear_greed:
                fear_val = fear_greed['value']
                fear_emoji = "😰" if fear_val < 30 else ("🤑" if fear_val > 70 else "⚖️")
                lines.append(f"{fear_emoji} <b>Индекс страха:</b> {fear_val}/100")
                lines.append("")
        except Exception as e:
            logger.debug(f"Ошибка получения индекса страха: {e}")
        
        # Футер
        footer = await db.get_setting("footer_template", "")
        if footer:
            lines.append(footer)
        
        return "\n".join(lines)
    
    async def _publish_digest(self, digest_html: str, news_count: int) -> Optional[int]:
        """
        Опубликовать дайджест в канал
        
        Returns:
            message_id или None
        """
        try:
            # Inline кнопки
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="💬 Открытый общий чат", url="https://t.me/+514GO2tFjAtkMWRi")
            keyboard.button(text="📢 Подписаться", url="https://t.me/blexler_invest")
            keyboard.adjust(1)
            
            sent_message = await bot.send_message(
                chat_id=config.telegram_channel_id,
                text=digest_html,
                parse_mode="HTML",
                disable_web_page_preview=False,  # Показываем превью ссылок
                reply_markup=keyboard.as_markup()
            )
            
            logger.info(f"✅ Дайджест опубликован: {news_count} новостей, MsgID: {sent_message.message_id}")
            return sent_message.message_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка публикации дайджеста: {e}", exc_info=True)
            return None
    
    async def _save_digest_info(self, message_id: int, news_list: List[Dict]):
        """Сохранить информацию о дайджесте в БД"""
        try:
            # 1. Создать запись в news_digests
            async with db.conn.execute(
                """
                INSERT INTO news_digests (type, telegram_message_id, news_count)
                VALUES (?, ?, ?)
                """,
                (f'{self.DIGEST_INTERVAL_HOURS}hour', message_id, len(news_list))
            ) as cursor:
                await db.conn.commit()
                digest_id = cursor.lastrowid
            
            # 2. Обновить все новости в дайджесте
            news_urls = [n['url'] for n in news_list]
            
            for url in news_urls:
                await db.conn.execute(
                    """
                    UPDATE news
                    SET posted_to_telegram = 1, digest_batch_id = ?, telegram_message_id = ?
                    WHERE url = ?
                    """,
                    (digest_id, message_id, url)
                )
            
            await db.conn.commit()
            
            logger.info(f"✅ Сохранена информация о дайджесте #{digest_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения информации о дайджесте: {e}", exc_info=True)


# Глобальный экземпляр
digest_builder = DigestBuilder()

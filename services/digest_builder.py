"""
Создание периодических дайджестов новостей (Digest 2.0)
Собирает новости за N часов, группирует по категориям и публикует аналитическую сводку
"""
import logging
import json
import random
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import bot
from config import config
from database import db
from services.ai_summary import NewsAnalyzer
from services.content_deduplicator import ContentDeduplicator
from services.message_builder import get_multiple_crypto_prices, FearGreedIndexTracker
from services.translator import translator

logger = logging.getLogger(__name__)


class DigestBuilder:
    """Создание периодических дайджестов новостей"""
    
    # Интервал дайджеста (1 час по требованию пользователя)
    DIGEST_INTERVAL_HOURS = 1
    
    # Минимальное количество новостей для публикации дайджеста
    MIN_NEWS_COUNT = 2
    
    # Категории новостей (Digest 2.0)
    # Ключи соответствуют тому, что возвращает AI (или маппинг)
    CATEGORIES = {
        'Bitcoin': {'emoji': '🟠', 'title': 'BITCOIN & MACRO'},
        'Ethereum': {'emoji': '🔵', 'title': 'ETHEREUM & L2'},
        'Altcoins': {'emoji': '🟣', 'title': 'ALTCOINS'},
        'DeFi': {'emoji': '💸', 'title': 'DEFI & STABLECOINS'},
        'NFT': {'emoji': '🖼️', 'title': 'NFT & METAVERSE'},
        'Regulation': {'emoji': '⚖️', 'title': 'REGULATION'},
        'Market': {'emoji': '📊', 'title': 'MARKET SENTIMENT'},
        'Security': {'emoji': '🚨', 'title': 'SECURITY & HACKS'},
        'Other': {'emoji': '📌', 'title': 'OTHER NEWS'}
    }
    
    # Эмодзи для новостей (fallback)
    NEWS_EMOJIS = ['🔹', '🔸', '⚡', '✨', '📌', '📍', '💎', '💡', '🔖', '🚩', '🌀', '💠']
    
    def __init__(self):
        self.ai_analyzer = NewsAnalyzer()
    
    async def build_and_publish_digest(self):
        """
        Главная функция: собрать и опубликовать дайджест
        
        Вызывается планировщиком каждые 3 часа
        """
        try:
            # === СИСТЕМНЫЙ "ТИХИЙ РЕЖИМ" (23:00 - 08:00) ===
            current_hour = datetime.now().hour
            if current_hour >= 23 or current_hour < 8:
                logger.info(f"🌙 Тихий режим (23:00-08:00). Дайджест пропущен. (Сейчас {current_hour}:00)")
                return

            logger.info(f"📰 Начало сборки {self.DIGEST_INTERVAL_HOURS}-часового дайджеста (v2.0)...")
            
            # 1. Получить новости за период
            news_list = await self._get_digest_news()
            
            if len(news_list) < self.MIN_NEWS_COUNT:
                logger.info(f"⏭️ Недостаточно новостей ({len(news_list)} < {self.MIN_NEWS_COUNT}), пропускаем дайджест")
                return
            
            logger.info(f"📊 Собрано {len(news_list)} новостей для дайджеста")
            
            # 2. Категоризация и дедупликация
            categorized_news, sentiment_data = await self._categorize_and_process(news_list)
            
            # 3. Форматирование дайджеста
            digest_html = await self._format_digest(categorized_news, sentiment_data, len(news_list))
            
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
    
    async def _categorize_and_process(self, news_list: List[Dict]) -> tuple[Dict[str, List[Dict]], Dict]:
        """
        Категоризировать новости и подготовить данные для аналитики
        Returns:
            categorized: Словарь {category: [news]}
            sentiment_data: Данные о сентименте
        """
        categorized = {cat: [] for cat in self.CATEGORIES.keys()}
        total_sentiment = 0
        sentiment_count = 0
        
        for news_item in news_list:
            # 1. Проверяем наличие AI данных (Digest 2.0)
            if not news_item.get('category') or news_item.get('sentiment_score') is None:
                logger.info(f"🔄 AI анализ для новости (Digest 2.0): {news_item['title'][:30]}...")
                try:
                    # Анализируем полный текст или summary
                    text_to_analyze = news_item.get('full_content') or news_item.get('summary') or news_item['title']
                    ai_result = await self.ai_analyzer.analyze_text(text_to_analyze)
                    
                    if ai_result:
                        # Обновляем новость в памяти
                        news_item['category'] = ai_result.get('category')
                        news_item['sentiment_score'] = ai_result.get('sentiment_score')
                        news_item['why_it_matters'] = ai_result.get('why_it_matters')
                        
                        # Сохраняем в БД
                        async with db.conn.execute(
                            """UPDATE news 
                               SET category = ?, sentiment_score = ?, why_it_matters = ? 
                               WHERE url = ?""",
                            (news_item['category'], news_item['sentiment_score'], news_item['why_it_matters'], news_item['url'])
                        ) as cursor:
                            await db.conn.commit()
                except Exception as e:
                    logger.error(f"⚠️ Ошибка AI анализа в дайджесте: {e}")

            # 2. Определяем категорию
            category = news_item.get('category')
            
            # Если всё ещё нет категории, пробуем угадать (fallback)
            if not category or category not in self.CATEGORIES:
                category = await self._guess_category(news_item)
            
            # Fallback
            if category not in self.CATEGORIES:
                category = 'Other'
                
            # 3. Считаем сентимент
            score = news_item.get('sentiment_score')
            if score is not None:
                try:
                    total_sentiment += int(score)
                    sentiment_count += 1
                except: pass
                
            # 4. Дедупликация контента
            if not news_item.get('summary'):
                 news_item['summary'] = news_item['title']

            categorized[category].append(news_item)
        
        # Удаляем пустые категории
        categorized = {k: v for k, v in categorized.items() if v}
        
        # Сортировка категорий (Bitcoin первым, остальные как есть)
        sorted_categorized = {}
        priority_order = ['Market', 'Bitcoin', 'Ethereum', 'Altcoins', 'Regulation', 'DeFi', 'NFT', 'Security', 'Other']
        
        for k in priority_order:
            if k in categorized:
                sorted_categorized[k] = categorized[k]
                
        # Расчет среднего сентимента
        avg_sentiment = 0
        if sentiment_count > 0:
            avg_sentiment = total_sentiment / sentiment_count
            
        sentiment_data = {
            'average': avg_sentiment,
            'count': sentiment_count
        }
        
        return sorted_categorized, sentiment_data
    
    async def _guess_category(self, news_item: Dict) -> str:
        """Heuristic categorization if AI failed"""
        title = news_item['title'].lower()
        summary = news_item.get('summary', '').lower()
        full_text = title + " " + summary
        
        if 'bitcoin' in full_text or 'btc' in full_text: return 'Bitcoin'
        if 'ethereum' in full_text or 'eth' in full_text: return 'Ethereum'
        if 'solana' in full_text or 'sol' in full_text or 'altcoin' in full_text: return 'Altcoins'
        if 'nft' in full_text or 'metaverse' in full_text: return 'NFT'
        if 'defi' in full_text or 'stablecoin' in full_text or 'tvl' in full_text: return 'DeFi'
        if 'sec' in full_text or 'ban' in full_text or 'law' in full_text: return 'Regulation'
        if 'hack' in full_text or 'exploit' in full_text: return 'Security'
        if 'price' in full_text or 'market' in full_text or 'inflation' in full_text: return 'Market'
        
        return 'Other'
    
    async def _format_digest(self, categorized_news: Dict[str, List[Dict]], sentiment_data: Dict, news_count: int) -> str:
        """Форматировать дайджест 2.0 в HTML"""
        
        # 1. HEADER & SENTIMENT METER
        date_str = datetime.now().strftime("%d.%m.%Y")
        avg_sent = sentiment_data['average']
        
        # Visual Sentiment Meter [-10...10] -> [0...10] scale approx for squares
        # Mapped to 5 circles: 🔴🔴⚪⚪🟢
        
        # Normalize -10..10 to 0..1
        norm_score = (avg_sent + 10) / 20  # 0.0 to 1.0
        
        if avg_sent >= 5:
            mood_text = "Жадность (Greed)"
            circles = "🟢🟢🟢🟢🟢"
        elif avg_sent >= 2:
            mood_text = "Умеренная жадность"
            circles = "🟢🟢🟢⚪⚪"
        elif avg_sent >= -2:
            mood_text = "Нейтрально"
            circles = "⚪⚪⚪⚪⚪"
        elif avg_sent >= -5:
            mood_text = "Страх (Fear)"
            circles = "🔴🔴🔴⚪⚪"
        else:
            mood_text = "Экстремальный страх"
            circles = "🔴🔴🔴🔴🔴"
            
        lines = [
            f"📰 <b>CRYPTO DIGEST • {date_str}</b>",
            f"[{circles}] <b>Настроение рынка: {mood_text}</b> ({avg_sent:+.1f}/10)",
            "" 
        ]
        
        # Получаем текущий event loop для перевода
        loop = asyncio.get_event_loop()
        
        # 2. CATEGORIES
        for category, news_items in categorized_news.items():
            if not news_items:
                continue
            
            cat_info = self.CATEGORIES.get(category, self.CATEGORIES['Other'])
            lines.append(f"{cat_info['emoji']} <b>{cat_info['title']}</b>")
            lines.append("") 
            
            # Limit items per category to avoid super long posts
            for news_item in news_items[:3]:
                # 1. Перевод на лету (ПРИНУДИТЕЛЬНО)
                original_title = news_item['title']
                translated_title = original_title
                
                try:
                    translation_result = await loop.run_in_executor(
                        None, 
                        translator.translate_text, 
                        original_title, 
                        'auto', 
                        'ru'
                    )
                    if translation_result:
                        translated_title = translation_result
                except Exception as e:
                    logger.warning(f"Ошибка перевода: {e}")

                title = translated_title[:150]
                
                # 2. Ссылка
                url = news_item['url']
                # Check metadata for telegram link (skipped for brevity, assuming URL is fine)
                
                # 3. Эмодзи (случайный, если нет специфики)
                emoji = random.choice(self.NEWS_EMOJIS)
                
                # 4. Форматирование строки
                lines.append(f"{emoji} <a href=\"{url}\">{title}</a>")
                
                # 5. "Why It Matters" / Context
                why_matters = news_item.get('why_it_matters')
                if why_matters and len(why_matters) > 10:
                     # Translate why_it_matters too if needed (usually it's English from AI)
                    try:
                        wm_translated = await loop.run_in_executor(
                            None, translator.translate_text, why_matters, 'auto', 'ru'
                        )
                        if wm_translated:
                            why_matters = wm_translated
                    except: pass
                    
                    lines.append(f"💡 <i>{why_matters}</i>")
                
                lines.append("") # Интервал
            
        # 3. PRICES HEADER (Mini)
        try:
            prices = await get_multiple_crypto_prices()
            if prices and 'bitcoin' in prices:
                p = prices['bitcoin']
                changes = p.get('change', 0)
                arrow = "↗️" if changes >= 0 else "↘️"
                lines.append(f"💰 <b>BTC:</b> ${p['price']:,.0f} ({changes:+.2f}%) {arrow}")
        except: pass
        
        # 4. FOOTER
        lines.append("")
        lines.append(f"📊 <i>Всего новостей: {news_count}</i>")
        footer = await db.get_setting("footer_template", "")
        if footer:
            lines.append(footer)
        
        return "\n".join(lines)
    
    async def _publish_digest(self, digest_html: str, news_count: int) -> Optional[int]:
        """Опубликовать дайджест в канал"""
        try:
            # Inline кнопки
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="💬 Обсудить в чате", url="https://t.me/+514GO2tFjAtkMWRi")
            keyboard.button(text="🔥 Premium Аналитика", url="https://t.me/blexler_support_bot")
            keyboard.adjust(1)
            
            sent_message = await bot.send_message(
                chat_id=config.telegram_channel_id,
                text=digest_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard.as_markup()
            )
            
            logger.info(f"✅ Дайджест 2.0 опубликован: {news_count} новостей, MsgID: {sent_message.message_id}")
            return sent_message.message_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка публикации дайджеста: {e}", exc_info=True)
            return None
    
    async def _save_digest_info(self, message_id: int, news_list: List[Dict]):
        """Сохранить информацию о дайджесте в БД"""
        try:
            async with db.conn.execute(
                """
                INSERT INTO news_digests (type, telegram_message_id, news_count)
                VALUES (?, ?, ?)
                """,
                (f'{self.DIGEST_INTERVAL_HOURS}hour_v2', message_id, len(news_list))
            ) as cursor:
                await db.conn.commit()
                digest_id = cursor.lastrowid
            
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
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения информации о дайджесте: {e}", exc_info=True)


# Глобальный экземпляр
digest_builder = DigestBuilder()

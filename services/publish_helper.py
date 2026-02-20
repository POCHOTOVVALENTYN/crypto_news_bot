"""
Вспомогательная функция для публикации отдельной новости
Используется breaking_news_moderator для публикации одобренных новостей
"""
import logging
import asyncio
from typing import Dict, Optional

from loader import bot
from config import config
from database import db
from services.ai_summary import NewsAnalyzer
from services.message_builder import (
    AdvancedMessageFormatter, RichMediaMessage,
    get_multiple_crypto_prices, FearGreedIndexTracker,
    message_formatter
)
from services.comment_manager import CommentManager # <--- НОВОЕ
from services.content_deduplicator import ContentDeduplicator
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)


async def publish_single_news(news_item: Dict, is_breaking: bool = False):
    """
    Публикует одну новость в канал
    
    Args:
        news_item: Словарь с данными новости из БД
        is_breaking: Флаг breaking news (для логирования)
    """
    try:
        logger.info(f"🚀 Публикация{'🔥 BREAKING' if is_breaking else ''}: {news_item['title'][:50]}")
        
        # ========== КРИТИЧНО: ПЕРЕВОД ВСЕГО КОНТЕНТА НА РУССКИЙ ==========
        from services.translator import translator
        loop = asyncio.get_event_loop()
        
        # 1. Перевести title (если не на русском)
        if news_item.get('title'):
            try:
                detected_lang = await loop.run_in_executor(
                    None, translator.detect_language, news_item['title']
                )
                
                if detected_lang and detected_lang != 'ru':
                    translated_title = await loop.run_in_executor(
                        None, translator.translate_text, 
                        news_item['title'], detected_lang, 'ru'
                    )
                    if translated_title:
                        news_item['title'] = translated_title
                        logger.info(f"✅ Title переведен: {detected_lang} → ru")
            except Exception as e:
                logger.debug(f"⚠️ Ошибка перевода title: {e}")
        
        # 2. Перевести summary (если не на русском)
        summary = news_item.get('summary', '')
        if summary:
            try:
                # Очистка HTML тегов из summary
                summary_clean = AdvancedMessageFormatter.clean_text(summary)
                
                if summary_clean:
                    detected_lang = await loop.run_in_executor(
                        None, translator.detect_language, summary_clean
                    )
                    
                    if detected_lang and detected_lang != 'ru':
                        translated_summary = await loop.run_in_executor(
                            None, translator.translate_text,
                            summary_clean, detected_lang, 'ru'
                        )
                        if translated_summary:
                            news_item['summary'] = translated_summary
                            logger.info(f"✅ Summary переведен: {detected_lang} → ru")
                    else:
                        # Даже если на русском, используем очищенную версию
                        news_item['summary'] = summary_clean
            except Exception as e:
                logger.debug(f"⚠️ Ошибка перевода summary: {e}")
        
        # 3. Перевести full_content (если есть и не на русском)
        full_content = news_item.get('full_content', '')
        if full_content:
            try:
                # Очистка HTML тегов
                full_content_clean = AdvancedMessageFormatter.clean_text(full_content)
                
                if full_content_clean and len(full_content_clean) > 50:
                    # Проверяем язык на первых 500 символах
                    sample_text = full_content_clean[:500]
                    detected_lang = await loop.run_in_executor(
                        None, translator.detect_language, sample_text
                    )
                    
                    if detected_lang and detected_lang != 'ru':
                        # Если текст длинный (>2000), переводим частями
                        if len(full_content_clean) > 2000:
                            content_to_translate = full_content_clean[:2000]
                            translated_content = await loop.run_in_executor(
                                None, translator.translate_text,
                                content_to_translate, detected_lang, 'ru'
                            )
                            if translated_content:
                                news_item['full_content'] = translated_content
                                logger.info(f"✅ Full_content переведен (частично, 2000 симв): {detected_lang} → ru")
                        else:
                            translated_content = await loop.run_in_executor(
                                None, translator.translate_text,
                                full_content_clean, detected_lang, 'ru'
                            )
                            if translated_content:
                                news_item['full_content'] = translated_content
                                logger.info(f"✅ Full_content переведен: {detected_lang} → ru")
                    else:
                        # Даже если на русском, используем очищенную версию
                        news_item['full_content'] = full_content_clean
            except Exception as e:
                logger.debug(f"⚠️ Ошибка перевода full_content: {e}")
        
        # ========== КОНЕЦ БЛОКА ПЕРЕВОДА ==========
        
        # Подготовка данных
        ai_data = None
        technical_analysis = None
        
        # Получаем полный текст (уже переведенный)
        full_content = news_item.get('full_content') or news_item.get('summary', '')
        
        # Извлекаем ключевые моменты (ПРИНУДИТЕЛЬНО, для буллет-поинтов)
        key_points = []
        if full_content and len(full_content) > 300: # Даже для средних текстов
            try:
                # Сначала пробуем извлечь простые пункты без AI (быстро)
                from services.content_summarizer import ContentSummarizer
                key_points_raw = ContentSummarizer.extract_key_points(full_content)
                
                # Если не вышло, или мало, можно было бы AI, но пока stay simple
                if not key_points_raw and news_item.get('summary'):
                     # Если summary длинное, разбиваем его
                     key_points_raw = ContentSummarizer.extract_key_points(news_item['summary'])

                # Переводим ключевые моменты на русский (если они есть)
                if key_points_raw:
                    loop = asyncio.get_event_loop()
                    from services.translator import translator # Local import to avoid cycle
                    
                    for point in key_points_raw:
                        detected_lang = await loop.run_in_executor(None, translator.detect_language, point)
                        
                        if detected_lang and detected_lang != 'ru':
                            translated_point = await loop.run_in_executor(
                                None,
                                translator.translate_text,
                                point,
                                'ru'
                            )
                            key_points.append(translated_point or point)
                        else:
                            key_points.append(point)
                
                logger.info(f"✅ Извлечено {len(key_points)} ключевых моментов на русском")
                
            except Exception as e:
                logger.error(f"❌ Ошибка извлечения ключевых моментов: {e}")
        
        # Применяем дедупликацию
        dedup_result = await ContentDeduplicator.smart_summarize(
            title=news_item['title'],
            description=news_item.get('summary', ''),
            key_points=key_points,
            dedup_threshold=0.6
        )
        
        # Используем дедуплицированные данные
        title = dedup_result['title']
        summary = dedup_result['content'] or news_item.get('summary', '')
        key_points = dedup_result['key_points']
        
        if dedup_result['dedup_applied']:
            logger.info(f"✅ Дедупликация применена: {ContentDeduplicator.get_dedup_stats(len(key_points_raw) if 'key_points_raw' in locals() else 0, len(key_points), dedup_result.get('title_desc_overlap', False))}")
        
        # Получаем цены и индекс страха
        prices = await get_multiple_crypto_prices()
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()
        
        # Получаем шаблон футера
        footer_template = await db.get_setting("footer_template")
        
        # Форматируем сообщение
        msg_data = await message_formatter.format_professional_news(
            title=title,
            summary=summary,
            source=news_item['source'],
            source_url=news_item['url'],
            prices=prices,
            fear_greed=fear_greed,
            image_url=news_item.get('image_url'),
            ai_data=ai_data,
            technical_analysis=technical_analysis,
            key_points=key_points,
            full_content=full_content,
            footer_template=footer_template,
            is_breaking=is_breaking
        )
        
        # Проверяем metadata для встраивания Telegram ссылок
        import json
        metadata_str = news_item.get('metadata')
        if metadata_str:
            try:
                metadata = json.loads(metadata_str)
                if metadata.get('is_telegram_source') and metadata.get('telegram_link'):
                    telegram_link = metadata['telegram_link']
                    
                    # Встраиваем ссылку в случайный key point
                    if key_points:
                        import random
                        random_idx = random.randint(0, len(key_points) - 1)
                        key_points[random_idx] = AdvancedMessageFormatter.insert_random_link(
                            key_points[random_idx],
                            telegram_link
                        )
                        logger.info(f"🔗 Telegram ссылка встроена в key point #{random_idx + 1}")
                        
                        # Обновляем msg_data с новыми key points
                        # (переформатируем сообщение с обновленными key points)
                        msg_data = await message_formatter.format_professional_news(
                            title=title,
                            summary=summary,
                            source=news_item['source'],
                            source_url=news_item['url'],
                            prices=prices,
                            fear_greed=fear_greed,
                            image_url=news_item.get('image_url'),
                            ai_data=ai_data,
                            technical_analysis=technical_analysis,
                            key_points=key_points,
                            full_content=full_content,
                            footer_template=footer_template,
                            is_breaking=is_breaking
                        )
            except Exception as e:
                logger.debug(f"Ошибка обработки metadata: {e}")
        
        # Custom Buttons with Color Styles (Raw JSON)
        # aiogram does not support 'style' in inline keyboard buttons yet
        reply_markup_dict = {
            "inline_keyboard": [
                [
                    {
                        "text": "💬 Открытый общий чат",
                        "url": "https://t.me/+514GO2tFjAtkMWRi",
                        "style": "primary" # Blue button
                    }
                ],
                [
                    {
                        "text": "📢 Подписаться",
                        "url": "https://t.me/blexler_invest",
                        "style": "success" # Green button
                    }
                ]
            ]
        }
        
        # Публикуем
        # Используем reply_markup_dict напрямую
        rich_msg = RichMediaMessage(msg_data['text'], msg_data['image_url'], reply_markup=reply_markup_dict)
        sent_message = await rich_msg.send(bot, config.telegram_channel_id)
        
        if sent_message:
            message_id = sent_message.message_id
            await db.mark_as_posted(news_item['url'], message_id=message_id)
            
            if is_breaking:
                logger.info(f"🔥 Breaking news опубликована (MsgID: {message_id})")
            else:
                logger.info(f"✅ Новость опубликована (MsgID: {message_id})")
            
            # === НОВОЕ: Авто-комментарий с дисклеймером ===
            asyncio.create_task(CommentManager.post_disclaimer_comment(bot, message_id))
            
            return message_id
        else:
            logger.error(f"❌ Ошибка публикации новости")
            return None
            
    except Exception as e:
        logger.error(f"❌ Ошибка publish_single_news: {e}", exc_info=True)
        return None

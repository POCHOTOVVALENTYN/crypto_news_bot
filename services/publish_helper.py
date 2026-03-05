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


async def prepare_news_for_publish(news_item: Dict, is_breaking: bool = False) -> Dict:
    """
    БАГ 1 ИСПРАВЛЕН: Полный pipeline подготовки новости.
    Используется и для превью у администратора, и для реальной публикации
    (WYSIWYG — то, что видит админ = то, что увидит аудитория).
    
    Returns:
        Dict: {'text': html_text, 'image_url': image_url}
    """
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
    
    # 2. Перевести summary
    summary = news_item.get('summary', '')
    if summary:
        try:
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
                else:
                    news_item['summary'] = summary_clean
        except Exception as e:
            logger.debug(f"⚠️ Ошибка перевода summary: {e}")
    
    # 3. Перевести full_content
    full_content = news_item.get('full_content', '')
    if full_content:
        try:
            full_content_clean = AdvancedMessageFormatter.clean_text(full_content)
            if full_content_clean and len(full_content_clean) > 50:
                sample_text = full_content_clean[:500]
                detected_lang = await loop.run_in_executor(
                    None, translator.detect_language, sample_text
                )
                if detected_lang and detected_lang != 'ru':
                    content_to_translate = full_content_clean[:2000] if len(full_content_clean) > 2000 else full_content_clean
                    translated_content = await loop.run_in_executor(
                        None, translator.translate_text,
                        content_to_translate, detected_lang, 'ru'
                    )
                    if translated_content:
                        news_item['full_content'] = translated_content
                else:
                    news_item['full_content'] = full_content_clean
        except Exception as e:
            logger.debug(f"⚠️ Ошибка перевода full_content: {e}")
    
    # Получаем полный текст (уже переведенный)
    full_content = news_item.get('full_content') or news_item.get('summary', '')
    
    # БАГ 4 ИСПРАВЛЕН: key_points для Breaking News убраны полностью — они дублируют тело текста.
    # Для обычных новостей key_points оставяляем (дайджесты и др.)
    key_points = []
    if not is_breaking and full_content and len(full_content) > 300:
        try:
            from services.content_summarizer import ContentSummarizer
            key_points_raw = ContentSummarizer.extract_key_points(full_content)
            if not key_points_raw and news_item.get('summary'):
                key_points_raw = ContentSummarizer.extract_key_points(news_item['summary'])
            if key_points_raw:
                for point in key_points_raw:
                    detected_lang = await loop.run_in_executor(None, translator.detect_language, point)
                    if detected_lang and detected_lang != 'ru':
                        translated_point = await loop.run_in_executor(
                            None, translator.translate_text, point, 'ru'
                        )
                        key_points.append(translated_point or point)
                    else:
                        key_points.append(point)
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения ключевых моментов: {e}")
    
    # Применяем дедупликацию
    dedup_result = await ContentDeduplicator.smart_summarize(
        title=news_item['title'],
        description=news_item.get('summary', ''),
        key_points=key_points,
        dedup_threshold=0.6
    )
    title = dedup_result['title']
    summary = dedup_result['content'] or news_item.get('summary', '')
    key_points = dedup_result['key_points']
    
    # =========================================================
    # AI-РЕРАЙТ: умный копирайтинг под лимиты Telegram
    # =========================================================
    has_image = bool(news_item.get('image_url'))
    
    # БАГ 6 ИСПРАВЛЕН: raw_body = summary (уже переведённый, дедуплицированный)
    # Не full_content — он может быть длиннее и не переведён
    raw_body = summary or ''
    
    # Лимиты для тела с учётом overhead (~300 симв: заголовк+цены+футер).
    # caption (1024 симв Telegram) = 600 body + 300 overhead + 124 запас
    # message (4096 симв Telegram) = 3000 body + 300 overhead + 796 запас
    OVERHEAD = 300
    body_limit = (1024 - OVERHEAD - 124) if has_image else (4096 - OVERHEAD - 796)
    body_limit = max(body_limit, 300)
    
    # БАГ 6 ИСПРАВЛЕН: для Breaking News рерайт ВСЕГДА (не только при длинном тексте)
    # Для обычных новостей — только при превышении лимита
    needs_rewrite = is_breaking or (len(raw_body) > body_limit)
    
    if needs_rewrite and raw_body:
        try:
            # Выбираем тональность:
            # "breaking" — срочно/факты (длинный текст)
            # "enrich"   — дополнить контекстом (короткий текст)
            # "analysis" — аналитически (обычные новости)
            if is_breaking and len(raw_body) < 400:
                tone = "enrich"
            elif is_breaking:
                tone = "breaking"
            else:
                tone = "analysis"
            
            target = body_limit if len(raw_body) > body_limit else min(len(raw_body) + 300, body_limit)
            logger.info(
                f"🤖 AI-рерайт: {len(raw_body)} симв → цель ~{target} "
                f"(тон={tone}, фото={has_image})"
            )
            news_analyzer = NewsAnalyzer()
            ai_rewritten_text = await news_analyzer.rewrite_for_telegram(
                text=raw_body,
                title=title,
                has_image=has_image,
                tone=tone
            )
            if ai_rewritten_text:
                summary = ai_rewritten_text
                key_points = []
                logger.info(f"✅ AI-рерайт применён: {len(summary)} симв.")
            else:
                logger.warning("⚠️ AI-рерайт вернул None — smart_truncate fallback")
                from services.message_builder import AdvancedMessageFormatter as AMF
                if len(raw_body) > body_limit:
                    summary = AMF._smart_truncate(raw_body, body_limit)
                key_points = []
        except Exception as e:
            logger.error(f"❌ Ошибка AI-рерайта: {e}")
            from services.message_builder import AdvancedMessageFormatter as AMF
            if len(raw_body) > body_limit:
                summary = AMF._smart_truncate(raw_body, body_limit)
            key_points = []
    # =========================================================
    
    # Получаем цены и индекс страха
    prices = await get_multiple_crypto_prices()
    fear_greed = await FearGreedIndexTracker.get_fear_greed_index()
    
    # Форматируем сообщение
    msg_data = await message_formatter.format_professional_news(
        title=title,
        summary=summary,
        source=news_item['source'],
        source_url=news_item['url'],
        prices=prices,
        fear_greed=fear_greed,
        image_url=news_item.get('image_url'),
        key_points=key_points,
        full_content=full_content,
        is_breaking=is_breaking
    )
    
    # Встраиваем Telegram-ссылку если есть в metadata
    import json
    metadata_str = news_item.get('metadata')
    if metadata_str:
        try:
            metadata = json.loads(metadata_str)
            if metadata.get('is_telegram_source') and metadata.get('telegram_link') and key_points:
                import random
                random_idx = random.randint(0, len(key_points) - 1)
                key_points[random_idx] = AdvancedMessageFormatter.insert_random_link(
                    key_points[random_idx], metadata['telegram_link']
                )
                msg_data = await message_formatter.format_professional_news(
                    title=title, summary=summary,
                    source=news_item['source'], source_url=news_item['url'],
                    prices=prices, fear_greed=fear_greed,
                    image_url=news_item.get('image_url'),
                    key_points=key_points, full_content=full_content,
                    is_breaking=is_breaking
                )
        except Exception as e:
            logger.debug(f"Ошибка обработки metadata: {e}")
    
    return msg_data


async def prepare_news_for_moderation(news_item: Dict) -> Dict:
    """
    Краткий pipeline для admin preview-карточки модерации.
    
    НЕ используется для публикации — только для превью у администратора.
    Возвращает краткую выжимку (2-3 предложения), однострочные цены.
    
    Returns:
        Dict: {
            'title': str,          # заголовок новости
            'body': str,           # краткая выжимка 150-200 симв
            'prices_line': str,    # "BTC $72K (+1.4%) • ETH $2.1K (+2.5%) • F&G: 22"
        }
    """
    from services.translator import translator
    loop = asyncio.get_event_loop()

    title = news_item.get('title', '')
    summary = news_item.get('summary', '') or news_item.get('full_content', '')

    # 1. Перевод заголовка на русский
    try:
        detected = await loop.run_in_executor(None, translator.detect_language, title)
        if detected and detected != 'ru':
            translated = await loop.run_in_executor(
                None, translator.translate_text, title, detected, 'ru'
            )
            if translated:
                title = translated
    except Exception:
        pass

    # 2. Перевод тела
    if summary:
        try:
            detected = await loop.run_in_executor(None, translator.detect_language, summary[:200])
            if detected and detected != 'ru':
                translated = await loop.run_in_executor(
                    None, translator.translate_text, summary[:1500], detected, 'ru'
                )
                if translated:
                    summary = translated
        except Exception:
            pass

    # 3. AI-выжимка: digest tone → 150-200 симв
    body = summary
    if summary:
        try:
            news_analyzer = NewsAnalyzer()
            digest_text = await news_analyzer.rewrite_for_telegram(
                text=summary,
                title=title,
                has_image=False,
                tone="digest"
            )
            if digest_text:
                body = digest_text
                logger.info(f"✅ Digest-выжимка: {len(body)} симв")
        except Exception as e:
            logger.warning(f"⚠️ Digest AI failed, using raw summary: {e}")
            # Fallback: обрезаем summary до 200 симв по предложению
            from services.message_builder import AdvancedMessageFormatter as AMF
            body = AMF._smart_truncate(summary, 200) if len(summary) > 200 else summary

    # 4. Однострочные цены (не вызываем если не нужно — берём только основные)
    prices_parts = []
    try:
        prices = await get_multiple_crypto_prices()
        if prices:
            btc = prices.get('bitcoin')
            eth = prices.get('ethereum')
            if btc:
                sign = '+' if btc['change'] >= 0 else ''
                prices_parts.append(f"BTC ${btc['price']:,.0f} ({sign}{btc['change']:.1f}%)")
            if eth:
                sign = '+' if eth['change'] >= 0 else ''
                prices_parts.append(f"ETH ${eth['price']:,.0f} ({sign}{eth['change']:.1f}%)")
        fear_greed = await FearGreedIndexTracker.get_fear_greed_index()
        if fear_greed:
            prices_parts.append(f"F&G: {fear_greed.get('value', '?')}/100")
    except Exception:
        pass

    prices_line = " • ".join(prices_parts) if prices_parts else ""

    return {
        'title': title,
        'body': body,
        'prices_line': prices_line,
    }



async def publish_single_news(news_item: Dict, is_breaking: bool = False, pending_id: int = None):
    """
    Публикует одну новость в канал.
    
    Args:
        news_item: Словарь с данными новости из БД
        is_breaking: Флаг breaking news
        pending_id: ID записи в pending_breaking_news (для WYSIWYG)
    """
    try:
        logger.info(f"🚀 Публикация{'🔥 BREAKING' if is_breaking else ''}: {news_item['title'][:50]}")
        
        # ✅ WYSIWYG: для breaking news берём уже подготовленный текст из БД
        msg_data = None
        if is_breaking and pending_id:
            try:
                async with db.conn.execute(
                    "SELECT prepared_text, prepared_image_url FROM pending_breaking_news WHERE id = ?",
                    (pending_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                if row and row[0]:
                    msg_data = {'text': row[0], 'image_url': row[1]}
                    logger.info(f"✅ WYSIWYG: текст из БД ({len(row[0])} симв)")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось прочитать prepared_text: {e}")
        
        # Fallback: если нет prepared_text — готовим заново
        if msg_data is None:
            msg_data = await prepare_news_for_publish(news_item, is_breaking=is_breaking)
        
        
        
        # БАГ 3 ИСПРАВЛЕН: InlineKeyboardMarkup вместо dict (Telegram не принимает dict)
        channel_builder = InlineKeyboardBuilder()
        channel_builder.button(text="💬 Открытый общий чат", url="https://t.me/+514GO2tFjAtkMWRi")
        channel_builder.button(text="📢 Подписаться на канал", url="https://t.me/blexler_invest")
        channel_builder.adjust(1)
        channel_markup = channel_builder.as_markup()
        
        # Публикуем
        rich_msg = RichMediaMessage(msg_data['text'], msg_data['image_url'], reply_markup=channel_markup)
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

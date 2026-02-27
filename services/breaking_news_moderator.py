"""
Модерация молниеносных (breaking) новостей
Отправляет критические новости админам для подтверждения перед публикацией
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import bot
from config import config, ADMIN_IDS
from database import db
from services.message_builder import (
    message_formatter, get_multiple_crypto_prices, FearGreedIndexTracker
)

logger = logging.getLogger(__name__)

# SQLite CURRENT_TIMESTAMP формат: '2026-02-26 14:31:00' (без T, без микросекунд)
# isoformat() даёт '2026-02-26T14:31:00.123456' — при строковом сравнении
# буква T (ASCII 84) > пробел (ASCII 32), поэтому любая запись CURRENT_TIMESTAMP
# сразу считалась 'просроченной' — это и была причина бага!
_SQLITE_FMT = "%Y-%m-%d %H:%M:%S"

def _sqlite_now() -> str:
    """Текущее UTC время в формате, совместимом с SQLite CURRENT_TIMESTAMP"""
    return datetime.utcnow().strftime(_SQLITE_FMT)

def _sqlite_dt(dt: datetime) -> str:
    """datetime → SQLite-совместимая строка"""
    return dt.strftime(_SQLITE_FMT)


class BreakingNewsModerator:
    """Система модерации молниеносных новостей"""
    
    # Приоритет для breaking news
    BREAKING_PRIORITY_THRESHOLD = 9
    
    # БАГ 5: таймаут увеличен до 30 минут
    AUTO_PUBLISH_TIMEOUT_MINUTES = 30
    
    # Напоминание админам по истечении половины таймаута
    REMINDER_AT_MINUTES = 15
    
    def __init__(self):
        self.processing_lock = asyncio.Lock()
    
    async def detect_and_notify_admins(self):
        """
        Обнаружить breaking news и отправить админам на модерацию
        
        Вызывается планировщиком каждые 30 секунд
        """
        try:
            # Получаем новости с priority >= 9 без модерации
            breaking_news_list = await self._get_unmoderated_breaking_news()
            
            if not breaking_news_list:
                return
            
            logger.info(f"🔥 Обнаружено {len(breaking_news_list)} breaking news для модерации")
            
            for news_item in breaking_news_list:
                await self._create_moderation_request(news_item)
                
        except Exception as e:
            logger.error(f"❌ Ошибка detect_and_notify_admins: {e}", exc_info=True)
    
    async def _get_unmoderated_breaking_news(self) -> List[Dict]:
        """Получить breaking news без модерации"""
        try:
            async with db.conn.execute(
                """
                SELECT n.* FROM news n
                LEFT JOIN pending_breaking_news pbn ON n.url = pbn.news_url
                WHERE n.priority >= ?
                AND n.posted_to_telegram = 0
                AND n.digest_batch_id IS NULL
                AND pbn.id IS NULL
                ORDER BY n.added_at ASC
                LIMIT 5
                """,
                (self.BREAKING_PRIORITY_THRESHOLD,)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                rows = await cursor.fetchall()
                return rows
        except Exception as e:
            logger.error(f"❌ Ошибка получения breaking news: {e}", exc_info=True)
            return []
    
    async def _create_moderation_request(self, news_item: Dict):
        """Создать запрос на модерацию и отправить админам"""
        news_url = news_item['url']
        
        try:
            from services.translator import translator
            
            # Переводим на русский перед модерацией
            translation = await translator.translate_news(news_item['title'], news_item.get('summary', ''))
            
            if translation:
                news_item['title'] = translation['ru_title']
                if translation.get('ru_summary'):
                    news_item['summary'] = translation['ru_summary']

            # Добавляем в pending_breaking_news
            async with db.conn.execute(
                """
                INSERT INTO pending_breaking_news (news_url)
                VALUES (?)
                """,
                (news_url,)
            ) as cursor:
                await db.conn.commit()
                pending_id = cursor.lastrowid
            
            logger.info(f"📋 Создан запрос на модерацию #{pending_id} для: {news_item['title'][:50]}")
            
            # Отправляем всем админам
            for admin_id in ADMIN_IDS:
                await self._send_admin_notification(admin_id, news_item, pending_id)
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания запроса на модерацию: {e}", exc_info=True)
    
    async def _send_admin_notification(self, admin_id: int, news_item: Dict, pending_id: int):
        """БАГ 1 ИСПРАВЛЕН: WYSIWYG-превью = полный pipeline публикации"""
        try:
            # Импортируем функцию подготовки из publish_helper — тот же pipeline, что и при публикации
            from services.publish_helper import prepare_news_for_publish
            
            # Полная подготовка: перевод, key_points, дедупликация, цены
            news_copy = dict(news_item)  # не меняем оригинал
            preview_data = await prepare_news_for_publish(news_copy, is_breaking=True)
            
            # Таймаут из базы (если есть) или по умолчанию
            timeout_min = await db.get_setting("moderation_timeout", str(self.AUTO_PUBLISH_TIMEOUT_MINUTES))
            try:
                timeout_min = int(timeout_min)
            except (ValueError, TypeError):
                timeout_min = self.AUTO_PUBLISH_TIMEOUT_MINUTES
            
            message_text = (
                f"🚨 <b>BREAKING NEWS МОДЕРАЦИЯ</b>\n"
                f"➖➖➖➖➖➖➖➖➖➖\n"
                f"{preview_data['text']}\n"
                f"➖➖➖➖➖➖➖➖➖➖\n"
                f"⚡️ <b>Приоритет:</b> {news_item['priority']}/10\n"
                f"⏳ <b>Время:</b> {news_item['added_at']}\n"
                f"❌ <i>Авто-отмена через {timeout_min} мин.</i>"
            )
            
            reply_markup_dict = {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Опубликовать",
                            "callback_data": f"breaking_approve:{pending_id}",
                            "style": "success"
                        },
                        {
                            "text": "❌ Отклонить",
                            "callback_data": f"breaking_reject:{pending_id}",
                            "style": "danger"
                        }
                    ]
                ]
            }
            
            image_url = news_item.get('image_url')
            
            try:
                if image_url and isinstance(image_url, str) and image_url.startswith('http'):
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=image_url,
                        caption=message_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup_dict
                    )
                else:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=message_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup_dict
                    )
            except Exception as send_error:
                logger.warning(f"⚠️ Не удалось отправить фото админу {admin_id}: {send_error}")
                await bot.send_message(
                    chat_id=admin_id,
                    text=message_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup_dict
                )
            
            logger.info(f"📨 Уведомление отправлено админу {admin_id} (pending #{pending_id})")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления админу {admin_id}: {e}", exc_info=True)
    
    async def handle_admin_approval(self, callback_query: CallbackQuery, pending_id: int, decision: str):
        """
        Обработка решения админа
        
        Args:
            callback_query: Callback от inline кнопки
            pending_id: ID запроса в pending_breaking_news
            decision: 'approved' или 'rejected'
        """
        admin_id = callback_query.from_user.id
        
        try:
            # Получаем данные запроса
            async with db.conn.execute(
                "SELECT * FROM pending_breaking_news WHERE id = ?",
                (pending_id,)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                pending = await cursor.fetchone()
            
            if not pending:
                await callback_query.answer("⚠️ Запрос не найден", show_alert=True)
                return
            
            if pending['admin_decision'] != 'pending':
                await callback_query.answer(
                    f"⚠️ Уже обработано: {pending['admin_decision']}",
                    show_alert=True
                )
                return
            
            # БАГ 5 ИСПРАВЛЕН: формат дат совместим с SQLite (strftime вместо isoformat)
            async with db.conn.execute(
                """
                UPDATE pending_breaking_news
                SET admin_decision = ?, admin_approved_by = ?, published_at = ?
                WHERE id = ?
                """,
                (decision, admin_id, _sqlite_now(), pending_id)
            ) as cursor:
                await db.conn.commit()
            
            logger.info(f"✅ Админ {admin_id} принял решение: {decision} (pending #{pending_id})")
            
            # Уведомляем админа
            if decision == 'approved':
                await callback_query.answer("✅ Новость одобрена! Публикую...", show_alert=True)
                
                # Публикуем немедленно
                await self._publish_breaking_news(pending['news_url'])
                
                # Обновляем сообщения других админов
                await self._notify_other_admins(admin_id, pending_id, "одобрил")
                
            else:  # rejected
                await callback_query.answer("❌ Новость отклонена", show_alert=True)
                await self._notify_other_admins(admin_id, pending_id, "отклонил")
            
            # Редактируем сообщение с кнопками
            if callback_query.message.photo:
                await callback_query.message.edit_caption(
                    caption=callback_query.message.caption + f"\n\n{'✅ ОДОБРЕНО' if decision == 'approved' else '❌ ОТКЛОНЕНО'} админом",
                    parse_mode="HTML"
                )
            else:
                 await callback_query.message.edit_text(
                    text=callback_query.message.text + f"\n\n{'✅ ОДОБРЕНО' if decision == 'approved' else '❌ ОТКЛОНЕНО'} админом",
                    parse_mode="HTML"
                )
            
        except Exception as e:
            logger.error(f"❌ Ошибка handle_admin_approval: {e}", exc_info=True)
            await callback_query.answer("⚠️ Ошибка обработки", show_alert=True)
    
    async def _publish_breaking_news(self, news_url: str):
        """Немедленная публикация breaking news"""
        try:
            # Импортируем функцию публикации
            from services.publish_helper import publish_single_news
            
            # Получаем новость
            async with db.conn.execute(
                "SELECT * FROM news WHERE url = ?",
                (news_url,)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                news_item = await cursor.fetchone()
            
            if not news_item:
                logger.error(f"❌ Новость не найдена: {news_url}")
                return
            
            # Публикуем
            await publish_single_news(news_item, is_breaking=True)
            
            logger.info(f"🔥 Breaking news опубликована: {news_item['title'][:50]}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка публикации breaking news: {e}", exc_info=True)
    
    async def _notify_other_admins(self, approving_admin_id: int, pending_id: int, action: str):
        """Уведомить других админов о принятом решении"""
        try:
            from config import ADMIN_NAMES
            admin_name = ADMIN_NAMES.get(approving_admin_id, f"Админ #{approving_admin_id}")
            
            notification_text = f"ℹ️ {admin_name} {action} breaking news (ID: {pending_id})"
            
            for admin_id in ADMIN_IDS:
                if admin_id != approving_admin_id:
                    try:
                        await bot.send_message(
                            chat_id=admin_id,
                            text=notification_text
                        )
                    except Exception as e:
                        logger.debug(f"Не удалось уведомить админа {admin_id}: {e}")
                        
        except Exception as e:
            logger.debug(f"Ошибка уведомления других админов: {e}")
    
    async def handle_expired_requests(self):
        """
        Обработка истекших запросов на модерацию.
        Вызывается планировщиком каждые 1 минуту.
        
        БАГ 2+3 ИСПРАВЛЕН: reminder-блок выполняется ВСЕГДА, независимо
        от того, есть ли истёкшие новости. Разделено на два независимых блока.
        """
        try:
            now_utc = datetime.utcnow()
            
            # Таймаут из БД (настраиваемый админом)
            timeout_min_raw = await db.get_setting("moderation_timeout", str(self.AUTO_PUBLISH_TIMEOUT_MINUTES))
            try:
                timeout_min = int(timeout_min_raw)
            except (ValueError, TypeError):
                timeout_min = self.AUTO_PUBLISH_TIMEOUT_MINUTES
            
            cutoff_str    = _sqlite_dt(now_utc - timedelta(minutes=timeout_min))
            reminder_str  = _sqlite_dt(now_utc - timedelta(minutes=self.REMINDER_AT_MINUTES))
            
            # ── БЛОК 1: отмена истёкших (detected_at < now-30мин) ─────────────
            await self._expire_old_requests(cutoff_str)
            
            # ── БЛОК 2: напоминание (detected_at между now-30мин и now-15мин) ─
            # Выполняется ВСЕГДА, не зависит от Блока 1
            if self.REMINDER_AT_MINUTES < timeout_min:
                await self._send_reminders(reminder_str, cutoff_str)

        except Exception as e:
            logger.error(f"❌ Ошибка handle_expired_requests: {e}", exc_info=True)

    async def _expire_old_requests(self, cutoff_str: str):
        """Отменяем pending новости старше таймаута."""
        try:
            async with db.conn.execute(
                """
                SELECT * FROM pending_breaking_news
                WHERE admin_decision = 'pending'
                AND detected_at < ?
                """,
                (cutoff_str,)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                expired_requests = await cursor.fetchall()

            if not expired_requests:
                return

            logger.info(f"⏱ Истекло {len(expired_requests)} breaking news — отменяю.")
            for request in expired_requests:
                await self._expire_request(request)
        except Exception as e:
            logger.error(f"❌ _expire_old_requests: {e}", exc_info=True)

    async def _send_reminders(self, reminder_str: str, cutoff_str: str):
        """
        Отправляем напоминание если новость ждёт больше REMINDER_AT_MINUTES,
        но ещё не истекла (между reminder_str и cutoff_str по detected_at).
        
        Условие: reminder_str > cutoff_str хронологически
        (reminder_str = now-15мин, cutoff_str = now-30мин)
        → ищем записи в окне [now-30мин, now-15мин]
        """
        try:
            async with db.conn.execute(
                """
                SELECT id, news_url FROM pending_breaking_news
                WHERE admin_decision = 'pending'
                AND detected_at >= ?
                AND detected_at < ?
                AND reminded_at IS NULL
                """,
                (cutoff_str, reminder_str)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                to_remind = await cursor.fetchall()

            if not to_remind:
                return

            logger.info(f"⏰ Отправляю {len(to_remind)} напоминание(ий) о Breaking News")
            timeout_min = int(await db.get_setting("moderation_timeout", str(self.AUTO_PUBLISH_TIMEOUT_MINUTES)))
            remaining = timeout_min - self.REMINDER_AT_MINUTES

            for req in to_remind:
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(
                            chat_id=admin_id,
                            text=(
                                f"⏰ <b>Напоминание!</b> Breaking News ID: {req['id']}\n"
                                f"❗ Осталось <b>{remaining} мин.</b> для одобрения или отклонения.\n"
                                f"📄 URL: <code>{req['news_url'][:60]}</code>"
                            ),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.debug(f"Не удалось уведомить админа {admin_id}: {e}")
                # Помечаем что напомнили
                try:
                    await db.conn.execute(
                        "UPDATE pending_breaking_news SET reminded_at = ? WHERE id = ?",
                        (_sqlite_now(), req['id'])
                    )
                    await db.conn.commit()
                except Exception as e:
                    logger.warning(f"Не удалось обновить reminded_at для #{req['id']}: {e}")

        except Exception as e:
            logger.error(f"❌ _send_reminders: {e}", exc_info=True)


    async def _expire_request(self, request: Dict):
        """Пометить запрос как истекший и уведомить админов"""
        try:
            pending_id = request['id']
            news_url = request['news_url']
            
            # Обновляем статус на expired
            async with db.conn.execute(
                """
                UPDATE pending_breaking_news
                SET admin_decision = 'expired', last_error = 'Timeout reached'
                WHERE id = ?
                """,
                (pending_id,)
            ) as cursor:
                await db.conn.commit()

            # ✅ НОВОЕ: Помечаем новость как пропущенную в основной таблице (2 = skipped)
            async with db.conn.execute(
                "UPDATE news SET posted_to_telegram = 2 WHERE url = ?",
                (news_url,)
            ) as cursor:
                await db.conn.commit()
            
            logger.info(f"⏳ Breaking news истекла (таймаут {self.AUTO_PUBLISH_TIMEOUT_MINUTES} мин): {news_url}")
            
            # Уведомляем админов
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"⏳ <b>Время истекло</b>\nBreaking news ID: {pending_id} <b>ОТМЕНЕНА</b> (нет реакции админов).",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.debug(f"Не удалось уведомить админа {admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка _expire_request: {e}", exc_info=True)


# Глобальный экземпляр
breaking_moderator = BreakingNewsModerator()

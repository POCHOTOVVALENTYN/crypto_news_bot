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

logger = logging.getLogger(__name__)


class BreakingNewsModerator:
    """Система модерации молниеносных новостей"""
    
    # Приоритет для breaking news (пользователь установил 9)
    BREAKING_PRIORITY_THRESHOLD = 9
    
    # Таймаут автопубликации (5 минут по требованию пользователя)
    AUTO_PUBLISH_TIMEOUT_MINUTES = 5
    
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
        """Отправить уведомление админу"""
        try:
            # Форматируем сообщение
            message_text = (
                f"🔥 <b>BREAKING NEWS - ТРЕБУЕТСЯ МОДЕРАЦИЯ</b>\n\n"
                f"<b>Заголовок:</b> {news_item['title']}\n\n"
                f"<b>Источник:</b> {news_item['source']}\n"
                f"<b>Приоритет:</b> {news_item['priority']}/10\n"
                f"<b>Время:</b> {news_item['added_at']}\n\n"
                f"<b>Описание:</b>\n{news_item.get('summary', 'Нет описания')[:300]}\n\n"
                f"⏱️ Автопубликация через {self.AUTO_PUBLISH_TIMEOUT_MINUTES} минут"
            )
            
            # Создаем inline кнопки
            keyboard = InlineKeyboardBuilder()
            keyboard.button(
                text="✅ Опубликовать",
                callback_data=f"breaking_approve:{pending_id}"
            )
            keyboard.button(
                text="❌ Отклонить",
                callback_data=f"breaking_reject:{pending_id}"
            )
            keyboard.adjust(2)  # 2 кнопки в ряд
            
            await bot.send_message(
                chat_id=admin_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=keyboard.as_markup()
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
            
            # Обновляем решение
            async with db.conn.execute(
                """
                UPDATE pending_breaking_news
                SET admin_decision = ?, admin_approved_by = ?, published_at = ?
                WHERE id = ?
                """,
                (decision, admin_id, datetime.now().isoformat(), pending_id)
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
            await callback_query.message.edit_text(
                callback_query.message.text + f"\n\n{'✅ ОДОБРЕНО' if decision == 'approved' else '❌ ОТКЛОНЕНО'} админом",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка handle_admin_approval: {e}", exc_info=True)
            await callback_query.answer("⚠️ Ошибка обработки", show_alert=True)
    
    async def _publish_breaking_news(self, news_url: str):
        """Немедленная публикация breaking news"""
        try:
            # Импортируем функцию публикации
            from services.scheduler_tasks import publish_single_news
            
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
    
    async def auto_publish_expired(self):
        """
        Автопубликация breaking news при истечении таймаута
        
        Вызывается планировщиком каждые 1 минуту
        """
        try:
            cutoff_time = datetime.now() - timedelta(minutes=self.AUTO_PUBLISH_TIMEOUT_MINUTES)
            
            # Получаем pending запросы старше таймаута
            async with db.conn.execute(
                """
                SELECT * FROM pending_breaking_news
                WHERE admin_decision = 'pending'
                AND detected_at < ?
                """,
                (cutoff_time.isoformat(),)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                expired_requests = await cursor.fetchall()
            
            if not expired_requests:
                return
            
            logger.info(f"⏱️ Обнаружено {len(expired_requests)} истекших breaking news для автопубликации")
            
            for request in expired_requests:
                await self._auto_publish_single(request)
                
        except Exception as e:
            logger.error(f"❌ Ошибка auto_publish_expired: {e}", exc_info=True)
    
    async def _auto_publish_single(self, request: Dict):
        """Автопубликация одной breaking news"""
        try:
            pending_id = request['id']
            news_url = request['news_url']
            
            # Обновляем статус
            async with db.conn.execute(
                """
                UPDATE pending_breaking_news
                SET admin_decision = 'approved', auto_published = 1, published_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), pending_id)
            ) as cursor:
                await db.conn.commit()
            
            # Публикуем
            await self._publish_breaking_news(news_url)
            
            logger.warning(f"⚠️ Breaking news автоопубликована (таймаут {self.AUTO_PUBLISH_TIMEOUT_MINUTES} мин): {news_url}")
            
            # Уведомляем админов
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=f"⚠️ Breaking news автоматически опубликована (ID: {pending_id}) из-за истечения таймаута"
                    )
                except Exception as e:
                    logger.debug(f"Не удалось уведомить админа {admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка автопубликации: {e}", exc_info=True)


# Глобальный экземпляр
breaking_moderator = BreakingNewsModerator()

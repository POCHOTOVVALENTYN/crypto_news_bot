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

from zoneinfo import ZoneInfo

def _sqlite_dt(dt: datetime) -> str:
    """datetime → SQLite-совместимая строка"""
    return dt.strftime(_SQLITE_FMT)

def is_quiet_hours() -> bool:
    """
    Проверяет, включен ли сейчас "Тихий час" для Breaking News.
    Время: 23:00 - 06:59 по часовому поясу из config (обычно Europe/Kyiv).
    """
    try:
        tz = ZoneInfo(config.timezone)
        now_local = datetime.now(tz)
        
        # 23:00 до 23:59 ИЛИ 00:00 до 06:59
        if now_local.hour >= 23 or now_local.hour < 7:
            return True
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки тихого часа: {e}")
        return False


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
    
    async def detect_emergency_news(self):
        """
        🔥 Black Swans: Запуск каждые 45 минут (по запросу юзера).
        Выводит только priority = 10 (ЧС). Пропускает ИИ-куратора.
        """
        try:
            if is_quiet_hours():
                return
                
            emergency_list = await self._get_unmoderated_breaking_news(min_priority=10, max_priority=10)
            
            if not emergency_list:
                return
            
            logger.info(f"🚨 ЧРЕЗВЫЧАЙНАЯ НОВОСТЬ: Обнаружено {len(emergency_list)} Black Swan(s)")
            
            for news_item in emergency_list:
                await self._create_moderation_request(news_item)
                
        except Exception as e:
            logger.error(f"❌ Ошибка detect_emergency_news: {e}", exc_info=True)

    async def curate_hourly_news(self):
        """
        🧐 ИИ-Куратор: Запуск каждый час. 
        Собирает новости priority 6-9 за последние 2 часа и выбирает ТОП-1-2.
        Отсеянные получают статус 'discarded_by_ai'.
        """
        try:
            if is_quiet_hours():
                return
                
            curatable_list = await self._get_unmoderated_breaking_news(min_priority=6, max_priority=9)
            
            if not curatable_list:
                return
            
            logger.info(f"🧐 ИИ-КУРАТОР: Накопилось {len(curatable_list)} новостей для оценки.")
            
            if len(curatable_list) == 1:
                # Если всего одна новость, отправляем без ИИ
                logger.info("🧐 ИИ-КУРАТОР: У нас только 1 новость за час, пускаем сразу.")
                await self._create_moderation_request(curatable_list[0])
                return

            from services.ai_summary import NewsAnalyzer
            ai_analyzer = NewsAnalyzer()
            
            # ИИ выбирает победителей
            winner_ids = await ai_analyzer.curate_news_batch(curatable_list, max_winners=2)
            
            if not winner_ids:
                logger.info("🧐 ИИ-КУРАТОР: Все новости забракованы (инфошум).")
            
            for news_item in curatable_list:
                news_id = news_item.get('id')
                if news_id in winner_ids:
                    logger.info(f"🏆 КУРАТОР РЕКОМЕНДУЕТ (ID {news_id}): {news_item.get('title')}")
                    await self._create_moderation_request(news_item)
                else:
                    logger.debug(f"🗑 КУРАТОР ОТСЕЯЛ (ID {news_id}): {news_item.get('title')}")
                    # Помечаем как отброшенную
                    await self._discard_news_silently(news_item['url'])
                    
        except Exception as e:
            logger.error(f"❌ Ошибка curate_hourly_news: {e}", exc_info=True)
    
    async def _get_unmoderated_breaking_news(self, min_priority: int, max_priority: int = 10) -> List[Dict]:
        """Получить свежие breaking news без модерации"""
        try:
            async with db.conn.execute(
                """
                SELECT n.* FROM news n
                LEFT JOIN pending_breaking_news pbn ON n.url = pbn.news_url
                WHERE n.priority >= ? AND n.priority <= ?
                AND n.posted_to_telegram = 0
                AND n.digest_batch_id IS NULL
                AND pbn.id IS NULL
                AND n.added_at >= datetime('now', '-2 hours')
                ORDER BY n.priority DESC, n.added_at ASC
                LIMIT 10
                """,
                (min_priority, max_priority)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                rows = await cursor.fetchall()
                return rows
        except Exception as e:
            logger.error(f"❌ Ошибка получения breaking news: {e}", exc_info=True)
            return []
            
    async def _discard_news_silently(self, news_url: str):
        """Отсеять новость (добавить в pending_breaking_news, но как отклоненную)"""
        try:
            async with db.conn.execute(
                "INSERT INTO pending_breaking_news (news_url, admin_decision, decision_at) VALUES (?, 'discarded_by_ai', CURRENT_TIMESTAMP)",
                (news_url,)
            ):
                await db.conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка при отсеивании куратором: {e}")
    
    async def _create_moderation_request(self, news_item: Dict):
        """Создать запрос на модерацию: два pipeline — публикация (WYSIWYG) и превью (краткая карточка)"""
        news_url = news_item['url']
        
        try:
            from services.translator import translator
            
            # Переводим на русский перед модерацией (ОДИН РАЗ)
            # БАГ 1 ИСПРАВЛЕН: выставляем флаг _ru_translated = True чтобы
            # последующие pipeline (prepare_for_publish, prepare_for_moderation)
            # не переводили уже переведённый текст повторно
            translation = await translator.translate_news(news_item['title'], news_item.get('summary', ''))
            if translation:
                news_item['title'] = translation['ru_title']
                if translation.get('ru_summary'):
                    news_item['summary'] = translation['ru_summary']
                news_item['_ru_translated'] = True  # пропускаем перевод в downstream

            # Добавляем в pending_breaking_news
            async with db.conn.execute(
                "INSERT INTO pending_breaking_news (news_url) VALUES (?)",
                (news_url,)
            ) as cursor:
                await db.conn.commit()
                pending_id = cursor.lastrowid
            
            logger.info(f"📋 Создан запрос #{pending_id}: {news_item['title'][:50]}")
            
            # ── Pipeline 1: Полная публикация для канала (WYSIWYG) ──────────────────
            from services.publish_helper import prepare_news_for_publish, prepare_news_for_moderation
            news_copy = dict(news_item)
            channel_data = await prepare_news_for_publish(news_copy, is_breaking=True)
            logger.info(f"✅ Channel pipeline: {len(channel_data.get('text',''))} симв")
            
            # ── Pipeline 2: Краткое превью для администратора ───────────────────────
            moderation_card = await prepare_news_for_moderation(dict(news_item))
            logger.info(f"✅ Moderation preview: {len(moderation_card.get('body',''))} симв")
            
            # Отправляем всем админам (краткую карточку + кнопки)
            admin_msg_ids: Dict[int, int] = {}
            for admin_id in ADMIN_IDS:
                msg_id = await self._send_admin_notification(
                    admin_id, news_item, pending_id,
                    moderation_card=moderation_card
                )
                if msg_id:
                    admin_msg_ids[admin_id] = msg_id
            
            # Сохраняем в БД: канальный текст (WYSIWYG) + msg_ids
            import json
            update_data = {
                'admin_messages':     json.dumps(admin_msg_ids) if admin_msg_ids else None,
                'prepared_text':      channel_data.get('text'),
                'prepared_image_url': channel_data.get('image_url'),
            }
            update_data = {k: v for k, v in update_data.items() if v is not None}
            if update_data:
                set_clause = ", ".join(f"{k} = ?" for k in update_data)
                await db.conn.execute(
                    f"UPDATE pending_breaking_news SET {set_clause} WHERE id = ?",
                    (*update_data.values(), pending_id)
                )
                await db.conn.commit()
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания запроса на модерацию: {e}", exc_info=True)
    
    async def _send_admin_notification(
        self,
        admin_id: int,
        news_item: Dict,
        pending_id: int,
        moderation_card: Optional[Dict] = None,
        # legacy param — ignored now
        preview_data: Optional[Dict] = None
    ) -> Optional[int]:
        """
        Отправляет краткую admin-карточку модерации.
        
        Формат (итого: ~350-400 симв):
          🚨 BREAKING | Приоритет 10/10 | ⏳ 30 мин.
          
          📰 ЗАГОЛОВОК НОВОСТИ
          
          Краткая выжимка 2-3 предложения с фактами.
          
          📊 BTC $72K (+1.4%) • ETH $2.1K (+2.5%) • F&G: 22
        """
        try:
            timeout_min = await db.get_setting("moderation_timeout", str(self.AUTO_PUBLISH_TIMEOUT_MINUTES))
            try:
                timeout_min = int(timeout_min)
            except (ValueError, TypeError):
                timeout_min = self.AUTO_PUBLISH_TIMEOUT_MINUTES

            priority = news_item.get('priority', 0)
            
            # Если moderation_card не передан — формируем через старый путь (обратная совместимость)
            if moderation_card is None:
                title = news_item.get('title', 'Breaking News')
                body = news_item.get('summary', '')
                if len(body) > 200:
                    from services.message_builder import AdvancedMessageFormatter as AMF
                    body = AMF._smart_truncate(body, 200)
                source = news_item.get('source', 'Неизвестно')
                image_url = news_item.get('image_url')
            else:
                title = moderation_card.get('title') or news_item.get('title', 'Breaking News')
                body = moderation_card.get('body', '')
                source = moderation_card.get('source') or news_item.get('source', 'Неизвестно')
                image_url = moderation_card.get('image_url') or news_item.get('image_url')
            
            # Используем безопасную очистку, оставляя скобки, кавычки и важные символы
            from services.message_builder import AdvancedMessageFormatter as AMF
            clean_title = AMF.clean_text(title)
            
            # ВАЖНО v12: Увеличиваем лимит заголовка до 160 и используем smart_truncate
            if clean_title:
                display_title = AMF._smart_truncate(clean_title, 160).upper()
            else:
                display_title = AMF._smart_truncate(title, 160).upper()
            
            # Визуальное разделение (ЧС vs Куратор)
            if priority >= 10:
                header_line = f"🚨 <b>ЭКСТРЕННО (Black Swan)</b>  |  Приоритет <b>{priority}/10</b>  |  ⏳ <i>{timeout_min} мин.</i>"
            else:
                header_line = f"🧐 <b>ВЫБОР ИИ-КУРАТОРА</b>  |  Приоритет <b>{priority}/10</b>  |  ⏳ <i>{timeout_min} мин.</i>"

            # Сборка источника и фото
            source_parts = [f"<i>Источник: {source}</i>"]
            if image_url:
                source_parts.append(f"<a href='{image_url}'>[🖼 Фото]</a>")
            footer_line = " • ".join(source_parts)

            # Сборка карточки — чистый формат, без разделителей
            lines = [
                header_line,
                "",
            ]
            
            if not body:
                # Режим "Только заголовок" — делаем его максимально заметным
                lines.append(f"🔥 <b>{display_title}</b>")
                lines.append("")
                lines.append("<i>⚡️ Короткая новость без доп. контекста.</i>")
            else:
                lines.append(f"📰 <b>{display_title}</b>")
                lines.append("")
                lines.append(body.strip())
            
            lines.append("")
            lines.append(footer_line)
            
            # v12: Цены удалены из превью для админов (по запросу пользователя), 
            # они будут только в финальной публикации.
            
            message_text = "\n".join(lines)
            
            # Кнопки
            builder = InlineKeyboardBuilder()
            builder.button(text="✅ Опубликовать", callback_data=f"breaking_approve:{pending_id}")
            builder.button(text="❌ Отклонить", callback_data=f"breaking_reject:{pending_id}")
            builder.adjust(2)
            reply_markup = builder.as_markup()
            
            # Отправляем как текстовое сообщение (без фото, чтобы не связываться с caption-лимитом)
            sent = await bot.send_message(
                chat_id=admin_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
            return sent.message_id if sent else None
            
        except Exception as e:
            logger.error(f"❌ Ошибка _send_admin_notification для {admin_id}: {e}", exc_info=True)
            return None

    
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
            
            # Уведомляем и публикуем
            if decision == 'approved':
                await callback_query.answer("✅ Новость одобрена! Публикую...", show_alert=True)
                await self._publish_breaking_news(pending['news_url'], pending_id=pending_id)
                await self._notify_other_admins_of_decision(admin_id, pending_id, pending, decision="approved")
            else:  # rejected
                await callback_query.answer("❌ Новость отклонена", show_alert=True)
                await self._notify_other_admins_of_decision(admin_id, pending_id, pending, decision="rejected")
            
            # Удаляем reminder-сообщения у всех сразу (они уже неактуальны)
            asyncio.create_task(self._delete_reminder_messages(pending, delay=1))
            
            # БАГ 7 ИСПРАВЛЕН: обновляем карточку у одобрившего admin (чистый статус, убираем кнопки)
            if decision == 'approved':
                try:
                    emoji_self = "✅"
                    if callback_query.message.photo:
                        await callback_query.message.edit_caption(
                            caption=f"{emoji_self} <b>Вы одобрили</b> breaking news\n<i>ID: {pending_id} — публикую в канал...</i>",
                            parse_mode="HTML",
                            reply_markup=None
                        )
                    else:
                        await callback_query.message.edit_text(
                            text=f"{emoji_self} <b>Вы одобрили</b> breaking news\n<i>ID: {pending_id} — публикую в канал...</i>",
                            parse_mode="HTML",
                            reply_markup=None
                        )
                except Exception:
                    pass
            else:
                # При отклонении — удаляем карточку у одобрившего через 5 сек
                asyncio.create_task(
                    self._delayed_delete_message(callback_query.message, delay=5)
                )


        except Exception as e:
            logger.error(f"❌ Ошибка handle_admin_approval: {e}", exc_info=True)
            await callback_query.answer("⚠️ Ошибка обработки", show_alert=True)
    
    async def _publish_breaking_news(self, news_url: str, pending_id: int = None):
        """Немедленная публикация breaking news"""
        try:
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
            
            # Публикуем с pending_id для WYSIWYG
            await publish_single_news(news_item, is_breaking=True, pending_id=pending_id)
            
            logger.info(f"🔥 Breaking news опубликована: {news_item['title'][:50]}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка публикации breaking news: {e}", exc_info=True)
    
    async def _delayed_delete_message(self, message, delay: int = 5):
        """Удалить сообщение через delay секунд"""
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except Exception:
            pass

    async def _delayed_delete_by_id(self, chat_id: int, message_id: int, delay: int = 3):
        """Удалить сообщение по chat_id + message_id через delay секунд"""
        await asyncio.sleep(delay)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    async def _delete_reminder_messages(self, pending: Dict, delay: int = 0):
        """Удалить reminder-сообщения у всех админов.
        Вызывается после любого решения (approved/rejected/expired)."""
        import json
        if delay:
            await asyncio.sleep(delay)
        raw = pending.get('reminder_messages')
        if not raw:
            return
        try:
            reminder_messages = {int(k): int(v) for k, v in json.loads(raw).items()}
        except Exception:
            return
        for chat_id, msg_id in reminder_messages.items():
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass

    async def _notify_other_admins_of_decision(
        self,
        approving_admin_id: int,
        pending_id: int,
        pending: Dict,
        decision: str
    ):
        """
        Уведомить других админов о решении.
        Если решение approved — помечаем их сообщения. 
        Если rejected — удаляем сообщения у всех других.
        """
        import json
        try:
            from config import ADMIN_NAMES
            admin_name = ADMIN_NAMES.get(approving_admin_id, f"Админ #{approving_admin_id}")
            verb = "одобрил" if decision == "approved" else "отклонил"
            emoji = "✅" if decision == "approved" else "❌"

            # Извлекаем сохранённые msg_id
            admin_messages: Dict[int, int] = {}
            raw = pending.get('admin_messages')
            if raw:
                try:
                    admin_messages = {int(k): int(v) for k, v in json.loads(raw).items()}
                except Exception:
                    pass

            for admin_id in ADMIN_IDS:
                if admin_id == approving_admin_id:
                    continue
                try:
                    msg_id = admin_messages.get(admin_id)
                    if msg_id:
                        if decision == "rejected":
                            # Удаляем оригинальное сообщение модерации через 3 сек
                            asyncio.create_task(
                                self._delayed_delete_by_id(admin_id, msg_id, delay=3)
                            )
                        else:  # approved
                            # БАГ 2 ИСПРАВЛЕН: admin-карточка — текстовое сообщение (send_message, без фото).
                            # edit_message_caption вызвал бы BadRequest → сразу edit_message_text
                            try:
                                await bot.edit_message_text(
                                    chat_id=admin_id, message_id=msg_id,
                                    text=f"{emoji} <b>{admin_name} {verb}</b> breaking news\n<i>ID: {pending_id}</i>",
                                    parse_mode="HTML"
                                )
                            except Exception:
                                pass
                    else:
                        # Для старых записей без admin_messages — просто текст
                        notif = await bot.send_message(
                            chat_id=admin_id,
                            text=f"{emoji} {admin_name} {verb} breaking news (ID: {pending_id})"
                        )
                        if decision == "rejected":
                            asyncio.create_task(
                                self._delayed_delete_message(notif, delay=10)
                            )
                except Exception as e:
                    logger.debug(f"Не удалось уведомить админа {admin_id}: {e}")

        except Exception as e:
            logger.debug(f"Ошибка _notify_other_admins_of_decision: {e}")

    async def handle_expired_requests(self):
        """
        Обработка истекших запросов на модерацию.
        Вызывается планировщиком каждые 1 минуту.
        
        БАГ 2+3 ИСПРАВЛЕН: reminder-блок выполняется ВСЕГДА, независимо
        от того, есть ли истёкшие новости. Разделено на два независимых блока.
        """
        try:
            # БЛОКИРОВКА В ТИХИЙ ЧАС (Ночью)
            if is_quiet_hours():
                return
                
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
        Rich reminder: заголовок новости + кнопку «К сообщению» + кнопки approve/reject.
        Сохраняет reminder_messages в БД для последующего удаления при решении.
        """
        try:
            # Загружаем pending + admin_messages + заголовок новости за один запрос
            async with db.conn.execute(
                """
                SELECT pbn.id, pbn.news_url, pbn.admin_messages,
                       n.title
                FROM pending_breaking_news pbn
                LEFT JOIN news n ON n.url = pbn.news_url
                WHERE pbn.admin_decision = 'pending'
                AND pbn.detected_at >= ?
                AND pbn.detected_at < ?
                AND pbn.reminded_at IS NULL
                """,
                (cutoff_str, reminder_str)
            ) as cursor:
                cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
                to_remind = await cursor.fetchall()

            if not to_remind:
                return

            logger.info(f"⏰ Отправляю {len(to_remind)} напоминание(й) о Breaking News")
            timeout_min = int(await db.get_setting("moderation_timeout", str(self.AUTO_PUBLISH_TIMEOUT_MINUTES)))
            remaining = timeout_min - self.REMINDER_AT_MINUTES

            import json
            for req in to_remind:
                # Формат заголовка: из news.title или fallback на URL
                news_title = req.get('title') or ''
                if news_title:
                    # Берём первую строку, max 80 символов
                    display_title = news_title.split('\n')[0][:80].upper()
                else:
                    display_title = req['news_url'][:60]

                # Парсим admin_messages для deep link
                admin_messages: Dict[int, int] = {}
                raw = req.get('admin_messages')
                if raw:
                    try:
                        admin_messages = {int(k): int(v) for k, v in json.loads(raw).items()}
                    except Exception:
                        pass

                reminder_msg_ids: Dict[int, int] = {}

                # БАГ 9 ИСПРАВЛЕН: перепроверяем что запись ещё pending
                # (другой admin мог одобрить пока мы готовили напоминание)
                async with db.conn.execute(
                    "SELECT admin_decision FROM pending_breaking_news WHERE id = ?",
                    (req['id'],)
                ) as _chk:
                    _row = await _chk.fetchone()
                    if not _row or _row[0] != 'pending':
                        logger.info(f"⏭ Reminder #{req['id']} пропущен — уже обработан ({_row[0] if _row else 'not found'})")
                        continue

                for admin_id in ADMIN_IDS:
                    try:
                        # Кнопки: approve / reject / ссылка на оригинальное сообщение
                        reminder_builder = InlineKeyboardBuilder()
                        reminder_builder.button(
                            text="✅ Опубликовать", callback_data=f"breaking_approve:{req['id']}"
                        )
                        reminder_builder.button(
                            text="❌ Отклонить", callback_data=f"breaking_reject:{req['id']}"
                        )
                        reminder_builder.adjust(2)

                        # Deep link на оригинальное сообщение (работает для personal бота)
                        orig_msg_id = admin_messages.get(admin_id)
                        if orig_msg_id:
                            # tg://openmessage?user_id=XXX&message_id=YYY — универсальный deep link
                            deep_link = f"tg://openmessage?user_id={admin_id}&message_id={orig_msg_id}"
                            reminder_builder.row()
                            reminder_builder.button(text="↗️ К сообщению модерации", url=deep_link)

                        reminder_markup = reminder_builder.as_markup()

                        sent = await bot.send_message(
                            chat_id=admin_id,
                            text=(
                                f"⏰ <b>Напоминание о Breaking News!</b>\n\n"
                                f"📰 <b>{display_title}</b>\n\n"
                                f"⏳ Осталось: <b>{remaining} мин.</b> для принятия решения.\n"
                                f"После этого новость будет автоматически отменена."
                            ),
                            parse_mode="HTML",
                            reply_markup=reminder_markup
                        )
                        if sent:
                            reminder_msg_ids[admin_id] = sent.message_id
                    except Exception as e:
                        logger.debug(f"Не удалось отправить reminder админу {admin_id}: {e}")

                # Сохраняем reminder_messages и reminded_at
                try:
                    await db.conn.execute(
                        """UPDATE pending_breaking_news
                           SET reminded_at = ?, reminder_messages = ?
                           WHERE id = ?""",
                        (_sqlite_now(), json.dumps(reminder_msg_ids) if reminder_msg_ids else None, req['id'])
                    )
                    await db.conn.commit()
                except Exception as e:
                    logger.warning(f"Не удалось обновить reminded_at/reminder_messages для #{req['id']}: {e}")

        except Exception as e:
            logger.error(f"❌ _send_reminders: {e}", exc_info=True)


    async def _expire_request(self, request: Dict):
        """Пометить запрос как истекший, удалить все сообщения админов"""
        import json
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

            # Помечаем новость как пропущенную (2 = skipped)
            async with db.conn.execute(
                "UPDATE news SET posted_to_telegram = 2 WHERE url = ?",
                (news_url,)
            ) as cursor:
                await db.conn.commit()
            
            logger.info(f"⏳ Breaking news истекла (таймаут {self.AUTO_PUBLISH_TIMEOUT_MINUTES} мин): {news_url}")
            
            # Удаляем ремайндеры сразу
            asyncio.create_task(self._delete_reminder_messages(request, delay=0))
            
            # Удаляем оригинальные сообщения модерации через 10 секунд
            raw_admin = request.get('admin_messages')
            if raw_admin:
                try:
                    admin_msgs = {int(k): int(v) for k, v in json.loads(raw_admin).items()}
                    for chat_id, msg_id in admin_msgs.items():
                        asyncio.create_task(self._delayed_delete_by_id(chat_id, msg_id, delay=10))
                except Exception:
                    pass
            
            # Отправляем уведомление админам → авто-удаление через 60 сек
            for admin_id in ADMIN_IDS:
                try:
                    sent = await bot.send_message(
                        chat_id=admin_id,
                        text=(
                            f"⏳ <b>Время истекло</b>\n"
                            f"Breaking news <b>ID: {pending_id}</b> отменена — никто не отреагировал.\n"
                            f"<i>Сообщение удалится через 1 мин.</i>"
                        ),
                        parse_mode="HTML"
                    )
                    # Авто-удаление expired-уведомления через 60 сек
                    asyncio.create_task(self._delayed_delete_message(sent, delay=60))
                except Exception as e:
                    logger.debug(f"Не удалось уведомить админа {admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка _expire_request: {e}", exc_info=True)


# Глобальный экземпляр
breaking_moderator = BreakingNewsModerator()

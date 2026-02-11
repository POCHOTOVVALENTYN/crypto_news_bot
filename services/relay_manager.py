"""
RelayManager - Управление пересылкой сообщений между пользователями и админами
Relay Mode: Бот выступает посредником в общении
"""
import logging
from datetime import datetime
from typing import Optional, Dict
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from loader import bot
from config import ADMIN_NAMES, SUPPORT_CASCADE

logger = logging.getLogger(__name__)


def _extract_content_info(message: Message) -> dict:
    """Извлекает информацию о контенте сообщения для логов"""
    try:
        content_type = message.content_type
        # Безопасно получаем текст или подпись
        text = message.text or message.caption or ""
        
        if content_type == 'text':
            return {'type': 'text', 'text': text}
        elif content_type == 'photo':
            return {'type': 'photo', 'text': f"[Photo] {text}".strip()}
        elif content_type == 'voice':
            return {'type': 'voice', 'text': "[Voice Message]"}
        elif content_type == 'video':
            return {'type': 'video', 'text': f"[Video] {text}".strip()}
        elif content_type == 'document':
            return {'type': 'document', 'text': f"[Document] {text}".strip()}
        elif content_type == 'audio':
            return {'type': 'audio', 'text': f"[Audio] {text}".strip()}
        elif content_type == 'sticker':
            return {'type': 'sticker', 'text': "[Sticker]"}
        else:
            return {'type': 'other', 'text': f"[{content_type}]"}
    except Exception as e:
        logger.error(f"Ошибка извлечения контента: {e}")
        return {'type': 'unknown', 'text': "[Unknown Content]"}

class RelayManager:
    """Управление Relay Mode - пересылка сообщений между пользователем и админом"""
    
    @staticmethod
    async def create_session(user_id: int, session_type: str, 
                            initial_admin_id: int = 304050247) -> int:
        """
        Создать новую сессию поддержки
        
        Args:
            user_id: ID пользователя
            session_type: Тип сессии ('premium_support', 'consultation_planning', 'price_negotiation')
            initial_admin_id: ID первого админа (по умолчанию основатель)
            
        Returns:
            session_id: ID созданной сессии
        """
        cursor = await db.conn.execute(
            """
            INSERT INTO support_sessions 
            (user_id, type, current_admin_id, admin_cascade_level, status, created_at, last_activity)
            VALUES (?, ?, ?, 1, 'active', ?, ?)
            """,
            (user_id, session_type, initial_admin_id, datetime.now().isoformat(), datetime.now().isoformat())
        )
        session_id = cursor.lastrowid
        await db.conn.commit()
        
        # Уведомить ВСЕХ админов
        await RelayManager.notify_all_admins(session_id)
        
        logger.info(f"✅ Создана Relay сессия {session_id}: {session_type} для user {user_id}")
        return session_id
    
    @staticmethod
    async def claim_session(session_id: int, admin_id: int):
        """
        Админ забирает сессию себе
        """
        await db.conn.execute(
            """
            UPDATE support_sessions 
            SET current_admin_id = ?, last_activity = ?
            WHERE id = ?
            """,
            (admin_id, datetime.now().isoformat(), session_id)
        )
        await db.conn.commit()
        logger.info(f"✅ Админ {admin_id} забрал сессию {session_id}")

    @staticmethod
    async def notify_all_admins(session_id: int):
        """Уведомить ВСЕХ админов о новой сессии"""
        # Используем список ID из конфига
        from config import ADMIN_IDS
        
        for admin_id in ADMIN_IDS:
            await RelayManager.notify_admin_target(session_id, admin_id)
            
    @staticmethod
    async def notify_admin(session_id: int):
        """Deprecated: Use notify_all_admins or notify_admin_target"""
        await RelayManager.notify_all_admins(session_id)

    @staticmethod
    async def notify_admin_target(session_id: int, admin_id: int):
        """Отправить уведомление КОНКРЕТНОМУ админу"""
        session = await RelayManager.get_session(session_id)
        if not session:
            return
        
        user_id = session['user_id']
        session_type = session['type']
        
        # Получить инфо о пользователе
        user = await db.get_user(user_id)
        
        # Безопасная обработка если пользователь не найден
        if user:
            username = f"@{user.get('username', '')}" if user.get('username') else f"ID:{user_id}"
            full_name = user.get('full_name', 'Пользователь')
            is_premium = user.get('status') == 'premium'
        else:
            username = f"ID:{user_id}"
            full_name = "Новый пользователь"
            is_premium = False
        
        # Формируем сообщение в зависимости от типа
        if session_type == 'premium_support':
            icon = "🆘"
            title = "НОВЫЙ ЗАПРОС ПОДДЕРЖКИ"
            description = "Пользователь ожидает ответа."
        elif session_type == 'consultation_planning':
            icon = "💰"
            title = "НОВАЯ КОНСУЛЬТАЦИЯ"
            description = "Договоритесь о дате и времени встречи."
        elif session_type == 'price_negotiation':
            icon = "💬"
            title = "ПЕРЕГОВОРЫ О ЦЕНЕ PREMIUM"
            description = "Пользователь просит индивидуальную цену."
        else:
            icon = "📨"
            title = "НОВОЕ СООБЩЕНИЕ"
            description = ""
        
        text = (
            f"{icon} <b>{title}</b>\n\n"
            f"👤 Пользователь: {full_name} {username}\n"
            f"🆔 ID: {user_id}\n"
        )
        
        if is_premium:
            text += "📱 Premium: ✅\n"
        
        text += f"\n{description}"
        
        # Inline кнопки для админа
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подключиться", callback_data=f"relay_connect_{session_id}")],
            [
                InlineKeyboardButton(text="➡️ Переадресовать", callback_data=f"relay_forward_{session_id}"),
                InlineKeyboardButton(text="❌ Закрыть", callback_data=f"relay_close_{session_id}")
            ]
        ])
        
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=keyboard)
            logger.info(f"📨 Уведомление отправлено админу {admin_id} о сессии {session_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления админу {admin_id}: {e}")
    
    @staticmethod
    async def relay_to_admin(session_id: int, message: Message):
        """Переслать сообщение пользователя админу (Text + Media)"""
        session = await RelayManager.get_session(session_id)
        if not session or session['status'] != 'active':
            return
        
        admin_id = session['current_admin_id']
        user_id = session['user_id']
        
        # 1. Извлекаем инфо для БД
        content_info = _extract_content_info(message)
        
        # 2. Сохраняем в БД
        await RelayManager.save_message(
            session_id=session_id,
            from_user_id=user_id,
            to_user_id=admin_id,
            message_text=content_info['text'],
            message_type=content_info['type'],
            telegram_message_id=message.message_id
        )
        
        # 3. Инфо о пользователе для заголовка
        user = await db.get_user(user_id)
        if user:
            username = f"@{user.get('username', '')}" if user.get('username') else f"ID:{user_id}"
            full_name = user.get('full_name', 'Пользователь')
        else:
            username = f"ID:{user_id}"
            full_name = "Пользователь"
            
        header_text = f"👤 <b>{full_name}</b> {username}:"
        
        try:
            # 4. Отправляем в чат админу
            # Сначала заголовок, чтобы понятно от кого
            await bot.send_message(admin_id, header_text, parse_mode="HTML")
            
            
            # Затем копируем само сообщение (медиа, текст, все что угодно)
            # Добавляем кнопку "Выставить счёт" для price_negotiation сессий
            buttons = [[InlineKeyboardButton(text="❌ Завершить чат", callback_data=f"relay_close_{session_id}")]]
            
            if session['type'] == 'price_negotiation':
                buttons.insert(0, [InlineKeyboardButton(
                    text="💰 Выставить счёт",
                    callback_data=f"set_custom_price_{session_id}"
                )])
            
            await bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
            logger.info(f"📨 Сообщение ({content_info['type']}) от user {user_id} переслано админу {admin_id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка пересылки сообщения админу {admin_id}: {e}")

        # Обновить активность
        await RelayManager.update_activity(session_id)
    
    @staticmethod
    async def relay_to_user(session_id: int, admin_message: Message):
        """Переслать ответ админа пользователю (Text + Media)"""
        session = await RelayManager.get_session(session_id)
        if not session or session['status'] != 'active':
            return
        
        user_id = session['user_id']
        admin_id = session['current_admin_id']
        
        # 1. Извлекаем инфо для БД
        content_info = _extract_content_info(admin_message)
        
        # 2. Сохранить в БД
        await RelayManager.save_message(
            session_id=session_id,
            from_user_id=admin_id,
            to_user_id=user_id,
            message_text=content_info['text'],
            message_type=content_info['type'],
            telegram_message_id=admin_message.message_id
        )
        
        # Получить имя админа
        admin_name = ADMIN_NAMES.get(admin_id, "Поддержка")
        
        try:
            # 3. Отправляем пользователю Action "typing"
            await bot.send_chat_action(user_id, action="typing")
            
            # 4. Копируем сообщение
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=admin_message.chat.id,
                message_id=admin_message.message_id,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Завершить чат", callback_data=f"user_close_{session_id}")]
                ])
            )
            logger.info(f"📨 Ответ ({content_info['type']}) от админа {admin_id} отправлен user {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ответа user {user_id}: {e}")
        
        # Обновить активность
        await RelayManager.update_activity(session_id)


    
    @staticmethod
    async def escalate_session(session_id: int):
        """Эскалировать сессию на следующий уровень админов"""
        session = await RelayManager.get_session(session_id)
        if not session:
            return
        
        current_level = session['admin_cascade_level']
        
        # Проверяем, есть ли следующий уровень
        if current_level >= len(SUPPORT_CASCADE):
            # Некуда эскалировать - финальное уведомление
            await RelayManager.notify_user_timeout(session_id)
            await RelayManager.close_session(session_id, status='timeout')
            logger.warning(f"⏱️ Сессия {session_id} timeout - все админы недоступны")
            return
        
        # Получить следующего админа
        next_admin_id = SUPPORT_CASCADE[current_level]  # current_level уже 0-indexed
        new_level = current_level + 1
        
        # Обновить сессию
        await db.conn.execute(
            """
            UPDATE support_sessions 
            SET current_admin_id = ?, admin_cascade_level = ?, escalation_attempts = escalation_attempts + 1
            WHERE id = ?
            """,
            (next_admin_id, new_level, session_id)
        )
        await db.conn.commit()
        
        logger.info(f"⬆️ Сессия {session_id} эскалирована на уровень {new_level} -> админ {next_admin_id}")
        
        # Уведомить нового админа
        await RelayManager.notify_admin(session_id)
    
    @staticmethod
    async def notify_user_timeout(session_id: int):
        """Уведомить пользователя о таймауте"""
        session = await RelayManager.get_session(session_id)
        if not session:
            return
        
        user_id = session['user_id']
        
        text = (
            "⏱️ <b>Все админы сейчас заняты</b>\n\n"
            "К сожалению, мы не смогли ответить на ваш запрос сразу.\n"
            "Мы обязательно свяжемся с вами в ближайшее время!\n\n"
            "Спасибо за понимание! 🙏"
        )
        
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления о таймауте user {user_id}: {e}")
    
    @staticmethod
    async def close_session(session_id: int, status: str = 'resolved'):
        """Закрыть сессию"""
        await db.conn.execute(
            """
            UPDATE support_sessions 
            SET status = ?, resolved_at = ?
            WHERE id = ?
            """,
            (status, datetime.now().isoformat(), session_id)
        )
        await db.conn.commit()
        
        logger.info(f"✅ Сессия {session_id} закрыта со статусом '{status}'")
    
    @staticmethod
    async def get_session(session_id: int) -> Optional[Dict]:
        """Получить информацию о сессии"""
        cursor = await db.conn.execute(
            "SELECT * FROM support_sessions WHERE id = ?",
            (session_id,)
        )
        row = await cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    @staticmethod
    async def get_active_session(user_id: int) -> Optional[Dict]:
        """Получить активную сессию пользователя"""
        cursor = await db.conn.execute(
            "SELECT * FROM support_sessions WHERE user_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None

    @staticmethod
    async def get_admin_active_session(admin_id: int) -> Optional[Dict]:
        """Получить активную сессию, которую ведет админ"""
        cursor = await db.conn.execute(
            "SELECT * FROM support_sessions WHERE current_admin_id = ? AND status = 'active' ORDER BY last_activity DESC LIMIT 1",
            (admin_id,)
        )
        row = await cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None
    
    @staticmethod
    async def save_message(session_id: int, from_user_id: int, to_user_id: int,
                          message_text: str, message_type: str = 'text',
                          telegram_message_id: int = None):
        """Сохранить сообщение в историю"""
        await db.conn.execute(
            """
            INSERT INTO support_messages 
            (session_id, from_user_id, to_user_id, message_text, message_type, telegram_message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, from_user_id, to_user_id, message_text, message_type, 
             telegram_message_id, datetime.now().isoformat())
        )
        await db.conn.commit()
    
    @staticmethod
    async def update_activity(session_id: int):
        """Обновить время последней активности"""
        await db.conn.execute(
            "UPDATE support_sessions SET last_activity = ? WHERE id = ?",
            (datetime.now().isoformat(), session_id)
        )
        await db.conn.commit()


# Экземпляр для импорта
relay_manager = RelayManager()

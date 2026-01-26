"""
Дополнение к Admin Dashboard - управление сессиями и консультациями
"""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from config import ADMIN_NAMES, CONSULTATION_PRICES

router = Router()
logger = logging.getLogger(__name__)


# Проверка прав админа
def admin_filter(user_id: int) -> bool:
    """Проверка прав админа"""
    from config import ADMIN_IDS
    return user_id in ADMIN_IDS


# === ПРОСМОТР СЕССИЙ ПОДДЕРЖКИ ===

@router.message(F.text == "📊 Сессии Поддержки")
async def show_support_sessions(message: Message):
    """Показать активные сессии поддержки"""
    user_id = message.from_user.id
    
    if not admin_filter(user_id):
        return
    
    # Получить активные сессии
    async with db.get_connection() as conn:
        cursor = await conn.execute("""
            SELECT s.id, s.user_id, s.type, s.current_admin_id, s.admin_cascade_level,
                   s.created_at, s.last_activity, u.full_name, u.username
            FROM support_sessions s
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.status = 'active'
            ORDER BY s.created_at DESC
        """)
        sessions = await cursor.fetchall()
    
    if not sessions:
        await message.answer("✅ Нет активных сессий поддержки")
        return
    
    text = f"📊 <b>Активные Сессии ({len(sessions)})</b>\n\n"
    
    for session in sessions:
        session_id, user_id, stype, admin_id, level, created, activity, name, username = session
        
        admin_name = ADMIN_NAMES.get(admin_id, f"ID:{admin_id}")
        user_display = name or username or f"ID:{user_id}"
        
        age_minutes = (datetime.now() - datetime.fromisoformat(created)).total_seconds() / 60
        
        type_emoji = {
            'premium_support': '🆘',
            'consultation_planning': '💰',
            'price_negotiation': '💬'
        }.get(stype, '📨')
        
        text += (
            f"{type_emoji} <b>Сессия #{session_id}</b>\n"
            f"👤 {user_display}\n"
            f"👨‍💼 Админ: {admin_name} (L{level})\n"
            f"⏱️ Возраст: {int(age_minutes)} мин\n"
            f"━━━━━━━━━━━━━━━\n"
        )
    
    # Inline кнопки для управления
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh_sessions")]
    ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "admin_refresh_sessions")
async def refresh_sessions(callback: CallbackQuery):
    """Обновить список сессий"""
    user_id = callback.from_user.id
    
    if not admin_filter(user_id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    
    # Получить активные сессии (копия кода выше)
    async with db.get_connection() as conn:
        cursor = await conn.execute("""
            SELECT s.id, s.user_id, s.type, s.current_admin_id, s.admin_cascade_level,
                   s.created_at, s.last_activity, u.full_name, u.username
            FROM support_sessions s
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.status = 'active'
            ORDER BY s.created_at DESC
        """)
        sessions = await cursor.fetchall()
    
    if not sessions:
        await callback.message.edit_text("✅ Нет активных сессий поддержки")
        await callback.answer()
        return
    
    text = f"📊 <b>Активные Сессии ({len(sessions)})</b>\n\n"
    
    for session in sessions:
        session_id, user_id, stype, admin_id, level, created, activity, name, username = session
        
        admin_name = ADMIN_NAMES.get(admin_id, f"ID:{admin_id}")
        user_display = name or username or f"ID:{user_id}"
        
        age_minutes = (datetime.now() - datetime.fromisoformat(created)).total_seconds() / 60
        
        type_emoji = {
            'premium_support': '🆘',
            'consultation_planning': '💰',
            'price_negotiation': '💬'
        }.get(stype, '📨')
        
        text += (
            f"{type_emoji} <b>Сессия #{session_id}</b>\n"
            f"👤 {user_display}\n"
            f"👨‍💼 Админ: {admin_name} (L{level})\n"
            f"⏱️ Возраст: {int(age_minutes)} мин\n"
            f"━━━━━━━━━━━━━━━\n"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh_sessions")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer("Обновлено!")


# === ПРОСМОТР КОНСУЛЬТАЦИЙ ===

@router.message(F.text == "📅 Консультации")
async def show_consultations(message: Message):
    """Показать запланированные консультации"""
    user_id = message.from_user.id
    
    if not admin_filter(user_id):
        return
    
    async with db.get_connection() as conn:
        cursor = await conn.execute("""
            SELECT c.id, c.user_id, c.type, c.amount_usd, c.scheduled_datetime,
                   c.status, u.full_name, u.username
            FROM consultations c
            LEFT JOIN users u ON c.user_id = u.user_id
            WHERE c.status IN ('paid', 'scheduled')
            ORDER BY c.scheduled_datetime ASC
        """)
        consultations = await cursor.fetchall()
    
    if not consultations:
        await message.answer("✅ Нет запланированных консультаций")
        return
    
    text = f"📅 <b>Консультации ({len(consultations)})</b>\n\n"
    
    for cons in consultations:
        c_id, cons_user_id, ctype, amount, scheduled, status, name, username = cons
        
        user_display = name or username or f"ID:{cons_user_id}"
        type_name = CONSULTATION_PRICES.get(ctype, {}).get('name', ctype)
        
        status_emoji = {'paid': '💰', 'scheduled': '📅'}.get(status, '❓')
        
        text += (
            f"{status_emoji} <b>{type_name}</b>\n"
            f"👤 {user_display}\n"
            f"💰 {amount}$\n"
        )
        
        if scheduled:
            dt = datetime.fromisoformat(scheduled)
            date_display = dt.strftime("%d.%m.%Y %H:%M")
            text += f"📅 {date_display}\n"
        
        text += f"━━━━━━━━━━━━━━━\n"
    
    await message.answer(text, parse_mode="HTML")


logger.info("✅ Admin Sessions/Consultations handlers зарегистрированы")

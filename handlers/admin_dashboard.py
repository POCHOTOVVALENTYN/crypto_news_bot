"""
Админ Dashboard - статистика и аналитика
"""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
import logging
from datetime import datetime, timedelta

from database import db
from config import config

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь админом"""
    return user_id == config.admin_id


@router.message(Command("dashboard"))
async def show_dashboard(message: Message):
    """Админ dashboard с общей статистикой"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    # Получаем статистику
    stats = await _collect_dashboard_stats()
    
    text = "📊 <b>Admin Dashboard</b>\n\n"
    
    # Пользователи
    text += "👥 <b>Пользователи:</b>\n"
    text += f"Всего: {stats['total_users']}\n"
    text += f"Premium: {stats['premium_users']}\n"
    text += f"Конверсия: {stats['premium_conversion']:.1f}%\n\n"
    
    # Геймификация
    text += "🎮 <b>Геймификация:</b>\n"
    text += f"Ср. Level: {stats['avg_level']:.1f}\n"
    text += f"Ср. XP: {stats['avg_xp']:.0f}\n"
    text += f"Топ игрок: Lv{stats['top_level']}\n\n"
    
    # Реферралы
    text += "🌳 <b>Реферралы:</b>\n"
    text += f"Всего связей: {stats['total_referrals']}\n"
    text += f"Топ реферрер: {stats['top_referrer_count']} друзей\n"
    text += f"Premium бонусы: {stats['referral_bonuses']}\n\n"
    
    # Revenue
    text += "💰 <b>Доход:</b>\n"
    text += f"Всего: {stats['total_revenue']:,}⭐\n"
    text += f"Этот месяц: {stats['month_revenue']:,}⭐\n"
    text += f"Ср. чек: {stats['avg_check']:.0f}⭐\n\n"
    
    # Stories
    text += "📸 <b>Stories:</b>\n"
    text += f"Всего проверок: {stats['total_story_checks']}\n"
    text += f"Успешных: {stats['successful_stories']}\n"
    text += f"Success rate: {stats['story_success_rate']:.1f}%\n"
    
    await message.answer(text, parse_mode="HTML")
    logger.info(f"📊 Dashboard показан админу")


@router.message(Command("topref"))
async def show_top_referrers(message: Message):
    """Топ рефереров"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return
    
    # Получаем топ-10 рефереров
    top = await db.get_top_referrers(limit=10)
    
    text = "🌟 <b>Топ-10 Рефереров</b>\n\n"
    
    for idx, user in enumerate(top, 1):
        name = user.get('full_name') or user.get('username') or f"User{user['user_id']}"
        count = user['referral_count']
        text += f"{idx}. {name}: {count} рефералов\n"
    
    await message.answer(text, parse_mode="HTML")


async def _collect_dashboard_stats() -> dict:
    """Собрать статистику для dashboard"""
    stats = {}
    
    try:
        # Пользователи
        async with db.get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM users")
            row = await cursor.fetchone()
            stats['total_users'] = row[0] if row else 0
            
            cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE status='premium'")
            row = await cursor.fetchone()
            stats['premium_users'] = row[0] if row else 0
            
            if stats['total_users'] > 0:
                stats['premium_conversion'] = (stats['premium_users'] / stats['total_users']) * 100
            else:
                stats['premium_conversion'] = 0.0
            
            # Геймификация
            cursor = await conn.execute("SELECT AVG(level), AVG(xp), MAX(level) FROM users")
            row = await cursor.fetchone()
            if row:
                stats['avg_level'] = row[0] or 1.0
                stats['avg_xp'] = row[1] or 0.0
                stats['top_level'] = row[2] or 1
            else:
                stats['avg_level'] = 1.0
                stats['avg_xp'] = 0.0
                stats['top_level'] = 1
            
            # Реферралы
            cursor = await conn.execute("SELECT COUNT(*) FROM referrals")
            row = await cursor.fetchone()
            stats['total_referrals'] = row[0] if row else 0
            
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM referrals GROUP BY referrer_id ORDER BY cnt DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            stats['top_referrer_count'] = row[0] if row else 0
            
            # Бонусы
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM user_activities WHERE activity_type='referral_bonus_premium'"
            )
            row = await cursor.fetchone()
            stats['referral_bonuses'] = row[0] if row else 0
            
            # Revenue
            cursor = await conn.execute(
                "SELECT SUM(amount_stars), AVG(amount_stars) FROM payments WHERE status='completed'"
            )
            row = await cursor.fetchone()
            if row:
                stats['total_revenue'] = row[0] or 0
                stats['avg_check'] = row[1] or 0
            else:
                stats['total_revenue'] = 0
                stats['avg_check'] = 0
            
            # Month revenue
            month_ago = (datetime.now() - timedelta(days=30)).isoformat()
            cursor = await conn.execute(
                "SELECT SUM(amount_stars) FROM payments WHERE status='completed' AND created_at > ?",
                (month_ago,)
            )
            row = await cursor.fetchone()
            stats['month_revenue'] = row[0] if row and row[0] else 0
            
            # Stories
            cursor = await conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN xp_earned > 0 THEN 1 ELSE 0 END) FROM user_activities WHERE activity_type='story_check'"
            )
            row = await cursor.fetchone()
            if row:
                stats['total_story_checks'] = row[0] or 0
                stats['successful_stories'] = row[1] or 0
            else:
                stats['total_story_checks'] = 0
                stats['successful_stories'] = 0
            
            if stats['total_story_checks'] > 0:
                stats['story_success_rate'] = (stats['successful_stories'] / stats['total_story_checks']) * 100
            else:
                stats['story_success_rate'] = 0.0
        
        return stats
        
    except Exception as e:
        logger.error(f"Ошибка сбора статистики dashboard: {e}", exc_info=True)
        # Возвращаем пустые данные в случае ошибки
        return {
            'total_users': 0,
            'premium_users': 0,
            'premium_conversion': 0.0,
            'avg_level': 1.0,
            'avg_xp': 0.0,
            'top_level': 1,
            'total_referrals': 0,
            'top_referrer_count': 0,
            'referral_bonuses': 0,
            'total_revenue': 0,
            'avg_check': 0,
            'month_revenue': 0,
            'total_story_checks': 0,
            'successful_stories': 0,
            'story_success_rate': 0.0
        }


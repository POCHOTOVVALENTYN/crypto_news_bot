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
    
    # Пользователи
    total_users = await db.execute("SELECT COUNT(*) FROM users")
    stats['total_users'] = (await total_users.fetchone())[0] if total_users else 0
    
    premium_users = await db.execute("SELECT COUNT(*) FROM users WHERE status='premium'")
    stats['premium_users'] = (await premium_users.fetchone())[0] if premium_users else 0
    
    if stats['total_users'] > 0:
        stats['premium_conversion'] = (stats['premium_users'] / stats['total_users']) * 100
    else:
        stats['premium_conversion'] = 0.0
    
    # Геймификация
    avg_stats = await db.execute("SELECT AVG(level), AVG(xp), MAX(level) FROM users")
    row = await avg_stats.fetchone() if avg_stats else (1, 0, 1)
    stats['avg_level'] = row[0] or 1.0
    stats['avg_xp'] = row[1] or 0.0
    stats['top_level'] = row[2] or 1
    
    # Реферралы
    ref_stats = await db.execute("SELECT COUNT(*) FROM referrals")
    stats['total_referrals'] = (await ref_stats.fetchone())[0] if ref_stats else 0
    
    top_ref = await db.execute(
        "SELECT COUNT(*) as cnt FROM referrals GROUP BY referrer_id ORDER BY cnt DESC LIMIT 1"
    )
    top_row = await top_ref.fetchone() if top_ref else None
    stats['top_referrer_count'] = top_row[0] if top_row else 0
    
    # Бонусы
    bonuses = await db.execute(
        "SELECT COUNT(*) FROM user_activities WHERE activity_type='referral_bonus_premium'"
    )
    stats['referral_bonuses'] = (await bonuses.fetchone())[0] if bonuses else 0
    
    # Revenue
    revenue = await db.execute("SELECT SUM(amount_stars), AVG(amount_stars) FROM payments WHERE status='completed'")
    rev_row = await revenue.fetchone() if revenue else (0, 0)
    stats['total_revenue'] = rev_row[0] or 0
    stats['avg_check'] = rev_row[1] or 0
    
    # Month revenue
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    month_rev = await db.execute(
        "SELECT SUM(amount_stars) FROM payments WHERE status='completed' AND created_at > ?",
        (month_ago,)
    )
    stats['month_revenue'] = (await month_rev.fetchone())[0] if month_rev else 0
    
    # Stories
    story_stats = await db.execute(
        "SELECT COUNT(*), SUM(CASE WHEN xp_earned > 0 THEN 1 ELSE 0 END) FROM user_activities WHERE activity_type='story_check'"
    )
    story_row = await story_stats.fetchone() if story_stats else (0, 0)
    stats['total_story_checks'] = story_row[0] or 0
    stats['successful_stories'] = story_row[1] or 0
    
    if stats['total_story_checks'] > 0:
        stats['story_success_rate'] = (stats['successful_stories'] / stats['total_story_checks']) * 100
    else:
        stats['story_success_rate'] = 0.0
    
    return stats

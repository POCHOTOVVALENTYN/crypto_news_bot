"""
Обработчики геймификации: лидерборд, начисление XP, проверка Stories
"""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
import logging

from database import db
from utils.states import UserState
from services.story_verificator import story_verificator

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "🏆 Топ Участников", StateFilter("*"))
@router.message(F.text == "🏆 Лидерборд", StateFilter("*"))  # Обратная совместимость
async def show_leaderboard(message: Message, state: FSMContext):
    """Показать топ-10 участников розыгрыша"""
    await state.clear()
    user_id = message.from_user.id
    
    # Получаем топ-10
    leaderboard = await db.get_leaderboard(limit=10)
    
    if not leaderboard:
        await message.answer("📊 Лидерборд пока пуст. Будьте первым!")
        return
    
    # Получаем позицию текущего пользователя
    user_rank = await db.get_user_rank(user_id)
    user = await db.get_user(user_id)
    
    # Формируем сообщение
    text = "🏆 <b>Топ Участников Розыгрыша</b>\n\n"
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    
    for idx, player in enumerate(leaderboard, 1):
        medal = medals.get(idx, f"{idx}.")
        name = player.get('full_name') or player.get('username') or f"User{player['user_id']}"
        xp = player['xp']
        level = player['level']
        
        # Выделяем текущего пользователя
        highlight = "👉 " if player['user_id'] == user_id else "   "
        
        text += f"{highlight}{medal} {name}\n"
        text += f"      Level {level} • {xp:,} XP\n\n"
    
    # Добавляем позицию пользователя если не в топ-10
    if user_rank and user_rank > 10:
        text += f"📍 <b>Ваша позиция:</b> #{user_rank}\n"
        text += f"Level {user['level']} • {user['xp']:,} XP\n"
    
    await message.answer(text, parse_mode="HTML")
    logger.info(f"📊 Лидерборд показан: {user_id}")


# === ПРОВЕРКА INSTAGRAM STORIES ===

@router.message(F.text == "📸 Проверить Stories", StateFilter("*"))
async def request_story_proof(message: Message, state: FSMContext):
    """Запрос скриншота Stories для проверки"""
    await state.clear()
    user_id = message.from_user.id
    
    # 🔒 RATE LIMITING: макс 5 проверок в день
    from datetime import datetime
    today = datetime.now().date().isoformat()
    daily_checks = await db.count_user_story_checks(user_id, today)
    
    if daily_checks >= 5:
        await message.answer(
            "⏳ <b>Лимит проверок исчерпан</b>\n\n"
            f"Вы уже проверили {daily_checks} Stories сегодня.\n"
            "Максимум: 5 проверок в день.\n\n"
            "Попробуйте завтра!",
            parse_mode="HTML"
        )
        logger.warning(f"⚠️ Stories rate limit: {user_id} ({daily_checks}/5)")
        return
    
    # Устанавливаем состояние ожидания загрузки
    await state.set_state(UserState.uploading_story)
    
    await message.answer(
        "📸 <b>Проверка Instagram Stories</b>\n\n"
        "Загрузите скриншот вашей Stories с отметкой <b>@blexler_invest</b>\n\n"
        "✅ Требования:\n"
        "• Отчётливо видна отметка аккаунта\n"
        "• Скриншот полный (не обрезан)\n"
        "• Хорошее качество изображения\n\n"
        "💎 Награда: +100 XP\n"
        f"📊 Осталось проверок сегодня: {5 - daily_checks - 1}\n\n"
        "Отправьте фото:",
        parse_mode="HTML"
    )
    logger.info(f"📸 Запрос Stories от {user_id} ({daily_checks + 1}/5)")


@router.message(UserState.uploading_story, F.photo)
async def verify_story_photo(message: Message, state: FSMContext):
    """Проверка загруженного скриншота Stories"""
    user_id = message.from_user.id
    
    # Показываем что обрабатываем
    processing_msg = await message.answer("🔍 Проверяю скриншот...")
    
    try:
        # Берём фото лучшего качества
        photo = message.photo[-1]
        
        # Проверяем через Vision API
        result = await story_verificator.verify_story_screenshot(photo.file_id, user_id)
        
        # Очищаем состояние
        await state.clear()
        
        if result['verified']:
            # ✅ Проверка пройдена!
            xp_result = await db.log_activity(
                user_id,
                'story_check',
                xp_amount=result['xp_earned']
            )
            
            response_text = (
                "✅ <b>Проверка пройдена!</b>\n\n"
                f"Отметка @blexler_invest найдена!\n"
                f"Уровень уверенности: {result['confidence']*100:.0f}%\n\n"
                f"✨ +{result['xp_earned']} XP начислено\n"
            )
            
            # Добавляем info о level up
            if xp_result.get('level_up'):
                response_text += (
                    f"\n🎊 <b>Level UP!</b> Вы достигли {xp_result['new_level']} уровня!"
                )
            
            await processing_msg.edit_text(response_text, parse_mode="HTML")
            logger.info(f"✅ Stories проверка успешна: {user_id} (+{result['xp_earned']} XP)")
            
        else:
            # ❌ Проверка не пройдена
            await processing_msg.edit_text(
                "❌ <b>Отметка не найдена</b>\n\n"
                f"Причина: {result['reason']}\n\n"
                "Пожалуйста, убедитесь что:\n"
                "• Отметка @blexler_invest чётко видна\n"
                "• Скриншот полный и качественный\n"
                "• Это действительно Instagram Stories\n\n"
                "Попробуйте ещё раз: /start",
                parse_mode="HTML"
            )
            logger.warning(f"❌ Stories проверка не пройдена: {user_id} - {result['reason']}")
            
    except Exception as e:
        logger.error(f"Ошибка проверки Stories {user_id}: {e}", exc_info=True)
        await processing_msg.edit_text(
            "⚠️ Произошла ошибка при проверке.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        await state.clear()


@router.message(UserState.uploading_story)
async def invalid_story_upload(message: Message):
    """Обработка неправильного формата (не фото)"""
    await message.answer(
        "⚠️ Пожалуйста, отправьте <b>фото</b> (скриншот Stories).\n\n"
        "Отмена: /start",
        parse_mode="HTML"
    )


# === РЕФЕРАЛЬНАЯ СИСТЕМА ===

@router.message(F.text == "🌳 Мои Рефералы", StateFilter("*"))
async def show_my_referrals(message: Message, state: FSMContext):
    """Показать статистику рефералов пользователя"""
    await state.clear()
    user_id = message.from_user.id
    
    # Получаем дерево рефералов
    tree = await db.get_referral_tree(user_id, max_depth=3)
    
    # Разделяем по уровням
    level1 = [r for r in tree if r['depth'] == 1]
    level2 = [r for r in tree if r['depth'] == 2]
    level3 = [r for r in tree if r['depth'] == 3]
    
    # Считаем активных (Premium)
    active_count = sum(1 for r in level1 if r['status'] == 'premium')
    
    # Проверяем право на бонус
    eligibility = await db.check_premium_bonus_eligibility(user_id)
    
    # Формируем сообщение
    text = "🌳 <b>Мои Рефералы</b>\n\n"
    
    # Общая статистика
    text += f"📊 <b>Статистика:</b>\n"
    text += f"Всего приглашено: {len(level1)}\n"
    text += f"Активных (Premium): {active_count}\n\n"
    
    # Прогресс к бонусу
    if not eligibility['bonus_given']:
        progress = min(active_count, 10)
        bar = "🟩" * progress + "⬜" * (10 - progress)
        text += f"💎 <b>Прогресс к бонусу:</b>\n"
        text += f"{bar} {progress}/10\n"
        
        if progress >= 10:
            text += "🎉 Бонус готов к получению!\n\n"
        else:
            text += f"Осталось: {10 - progress} активных\n"
            text += "Награда: Premium 12 дней + 500 XP\n\n"
    else:
        text += "✅ <b>Бонус уже получен!</b>\n\n"
    
    # Список рефералов
    if level1:
        text += "👥 <b>Мои приглашения (Level 1):</b>\n"
        for idx, ref in enumerate(level1[:5], 1):  # Топ-5
            name = ref.get('full_name') or ref.get('username') or f"User{ref['referred_id']}"
            status_icon = "💎" if ref['status'] == 'premium' else "🆓"
            text += f"{idx}. {status_icon} {name}\n"
        
        if len(level1) > 5:
            text += f"\n... и ещё {len(level1) - 5}\n"
    else:
        text += "👥 Вы ещё не пригласили друзей\n"
    
    # MLM статистика
    if level2 or level3:
        text += f"\n🌐 <b>Сеть MLM:</b>\n"
        text += f"Level 2: {len(level2)} чел.\n"
        text += f"Level 3: {len(level3)} чел.\n"
    
    text += "\n📎 Используйте кнопку 'Пригласить друга' для получения ссылки!"
    
    await message.answer(text, parse_mode="HTML")
    logger.info(f"🌳 Рефералы показаны: {user_id} (L1:{len(level1)}, active:{active_count})")


@router.message(F.text == "📎 Пригласить друга", StateFilter("*"))
async def share_referral_link(message: Message, state: FSMContext):
    """Генерация и отправка реферальной ссылки"""
    await state.clear()
    user_id = message.from_user.id
    
    # Получаем username бота
    bot_info = await message.bot.get_me()
    bot_username = bot_info.username
    
    # Генерируем ссылку
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    # Статистика
    ref_count = await db.get_referral_count(user_id)
    
    await message.answer(
        "📎 <b>Ваша реферальная ссылка</b>\n\n"
        f"<code>{referral_link}</code>\n\n"
        "🎁 <b>Что получите:</b>\n"
        "• +50 XP за каждого друга\n"
        "• +200 XP если друг купит Premium\n"
        "• +25 XP за рефералов 2-го уровня\n"
        "• +10 XP за рефералов 3-го уровня\n\n"
        "💎 <b>Бонус:</b> Premium 12 дней за 10 активных!\n\n"
        f"📊 Уже пригласили: {ref_count} друзей",
        parse_mode="HTML"
    )
    logger.info(f"📎 Реферальная ссылка: {user_id}")


# === ИСТОРИЯ STORIES ===

@router.message(F.text == "📜 История Проверок", StateFilter("*"))
@router.message(F.text == "📜 История Stories", StateFilter("*"))  # Обратная совместимость
async def show_story_history(message: Message, state: FSMContext):
    """История проверок Stories"""
    await state.clear()
    user_id = message.from_user.id
    
    history = await db.get_user_story_history(user_id, limit=10)
    
    if not history:
        await message.answer(
            "📜 <b>История проверок Stories</b>\n\n"
            "У вас пока нет проверок.\n\n"
            "Используйте '📸 Проверить Stories' чтобы начать!",
            parse_mode="HTML"
        )
        return
    
    text = "📜 <b>История проверок Stories</b>\n\n"
    
    for idx, entry in enumerate(history, 1):
        from datetime import datetime
        date = datetime.fromisoformat(entry['created_at']).strftime('%d.%m %H:%M')
        xp = entry['xp_earned']
        status = "✅" if xp > 0 else "❌"
        
        text += f"{idx}. {status} {date} - "
        if xp > 0:
            text += f"+{xp} XP\n"
        else:
            text += "Не пройдено\n"
    
    # Статистика
    total_checks = len(history)
    successful = sum(1 for e in history if e['xp_earned'] > 0)
    
    text += f"\n📊 <b>Статистика:</b>\n"
    text += f"Всего проверок: {total_checks}\n"
    text += f"Успешных: {successful}\n"
    text += f"Получено XP: {sum(e['xp_earned'] for e in history)}"
    
    await message.answer(text, parse_mode="HTML")
    logger.info(f"📜 История Stories показана: {user_id}")


# === БЕЙДЖИ ДОСТИЖЕНИЙ ===

BADGE_NAMES = {
    'level_5': '⭐ Опытный (Level 5)',
    'level_10_champion': '👑 Чемпион (Level 10)',
    'referrer_10': '🌟 Рекрутер (10 рефералов)',
    'referrer_50': '💫 Амбассадор (50 рефералов)',
    'premium_member': '💎 Premium Member',
    'story_hunter': '📸 Охотник за Stories (10+)',
    'early_adopter': '🚀 Ранний пользователь',
    'trader_pro': '📈 Профи Трейдер'
}

@router.message(F.text == "🏅 Мои Достижения", StateFilter("*"))
@router.message(F.text == "🏅 Мои Бейджи", StateFilter("*"))  # Обратная совместимость
async def show_badges(message: Message, state: FSMContext):
    """Показать достижения пользователя"""
    await state.clear()
    user_id = message.from_user.id
    
    # Проверяем и выдаём новые бейджи
    await db.check_and_award_badges(user_id)
    
    badges = await db.get_user_badges(user_id)
    
    if not badges:
        await message.answer(
            "🏅 <b>Мои Бейджи</b>\n\n"
            "У вас пока нет бейджей.\n\n"
            "Зарабатывайте XP, приглашайте друзей и повышайте уровень!",
            parse_mode="HTML"
        )
        return
    
    text = "🏅 <b>Мои Бейджи</b>\n\n"
    
    for badge_type in badges:
        badge_name = BADGE_NAMES.get(badge_type, badge_type)
        text += f"• {badge_name}\n"
    
    text += f"\n📍 Всего бейджей: {len(badges)}/{len(BADGE_NAMES)}"
    
    await message.answer(text, parse_mode="HTML")
    logger.info(f"🏅 Бейджи показаны: {user_id} ({len(badges)})")

from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime
import logging

from database import db
from loader import bot
from config import config

router = Router()
logger = logging.getLogger(__name__)


# === ОБРАБОТЧИКИ БЕСПЛАТНОГО МЕНЮ ===

@router.message(F.text == "🎁 Что внутри Premium?")
async def show_premium_features(message: Message):
    """Показать функции Premium"""
    await message.answer(
        "💎 <b>Premium-подписка включает:</b>\n\n"
        "🤖 <b>AI-клон аналитика Евгения</b>\n"
        "Общайтесь с личным AI-помощником, который поможет разобраться в рынке\n\n"
        "🚀 <b>Эксклюзивные сигналы (Futures)</b>\n"
        "Получайте торговые сигналы по фьючерсам с анализом и точками входа\n\n"
        "📊 <b>Премиум-аналитика</b>\n"
        "Глубокий технический и фундаментальный анализ рынка\n\n"
        "💡 <b>Авторские рекомендации</b>\n"
        "Личные инсайты и стратегии от Евгения\n\n"
        "🎓 <b>Обучающий курс</b>\n"
        "Материалы для развития навыков трейдинга\n\n"
        "💰 <b>Стоимость:</b> 500 ⭐️ (30 дней)\n\n"
        "Нажмите <b>\"🌟 Получить Premium-доступ\"</b> для подключения",
        parse_mode="HTML"
    )


@router.message(F.text == "📚 Наши ресурсы")
async def show_resources(message: Message):
    """Показать бесплатные ресурсы"""
    await message.answer(
        "📚 <b>Бесплатные ресурсы:</b>\n\n"
        "📰 Основной канал с новостями\n"
        "🔗 https://t.me/blexler_invest\n\n"
        "💬 Чат сообщества\n"
        "🔗 https://t.me/+514GO2tFjAtkMWRi",
        parse_mode="HTML"
    )


@router.message(F.text == "👨‍💻 Об Авторе")
async def show_author_info(message: Message):
    """Информация об авторе"""
    await message.answer(
        "👨‍💻 <b>Об Авторе</b>\n\n"
        "Евгений - профессиональный криптотрейдер и аналитик\n\n"
        "📈 Опыт торговли: 10+ лет\n"
        "💼 Специализация: Futures, Spot, DeFi\n"
        "🎯 Фокус: Технический анализ и риск-менеджмент\n\n"
        "Помогаю людям разобраться в криптовалютах и построить прибыльные стратегии",
        parse_mode="HTML"
    )


@router.message(F.text == "📞 Поддержка")
async def show_support_info(message: Message):
    """Контакты поддержки"""
    await message.answer(
        "📞 <b>Поддержка</b>\n\n"
        "По всем вопросам пишите:\n"
        "👤 @admin_username\n\n"
        "📧 Email: support@example.com\n\n"
        "Обычно отвечаем в течение 24 часов",
        parse_mode="HTML"
    )


# === ОБРАБОТЧИКИ PREMIUM МЕНЮ ===

@router.message(F.text == "🚀 Сигналы (Futures)")
async def premium_signals(message: Message):
    """Доступ к каналу сигналов (Premium)"""
    user_id = message.from_user.id
    
    # Проверка Premium
    is_premium = await db.check_subscription(user_id)
    if not is_premium:
        await message.answer(
            "⛔️ <b>Доступ закрыт</b>\n\n"
            "Эта функция доступна только для Premium подписчиков.\n"
            "Нажмите <b>\"🌟 Получить Premium-доступ\"</b> для подключения",
            parse_mode="HTML"
        )
        return
    
    try:
        # Генерируем временную ссылку-приглашение
        invite_link = await bot.create_chat_invite_link(
            chat_id=config.channel_premium_id,
            member_limit=1,
            name=f"User {user_id}"
        )
        
        await message.answer(
            f"🚀 <b>Канал с сигналами по фьючерсам</b>\n\n"
            f"Ваша персональная ссылка-приглашение:\n"
            f"🔗 {invite_link.invite_link}\n\n"
            f"⚠️ Ссылка одноразовая, только для вас",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка генерации invite link: {e}")
        await message.answer(
            "⚠️ Произошла ошибка при генерации ссылки.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )


@router.message(F.text == "📊 Премиум-Аналитика")
async def premium_analytics(message: Message):
    """Доступ к премиум-аналитике"""
    user_id = message.from_user.id
    
    is_premium = await db.check_subscription(user_id)
    if not is_premium:
        await message.answer("⛔️ Доступно только для Premium подписчиков")
        return
    
    await message.answer(
        "📊 <b>Премиум-Аналитика</b>\n\n"
        "Здесь будут публиковаться:\n"
        "• Глубокий технический анализ\n"
        "• Фундаментальные обзоры\n"
        "• Макроэкономические прогнозы\n\n"
        "Материалы скоро появятся!",
        parse_mode="HTML"
    )


@router.message(F.text == "💡 Авторские Рекомендации")
async def premium_recommendations(message: Message):
    """Авторские рекомендации из топовых новостей"""
    user_id = message.from_user.id
    
    is_premium = await db.check_subscription(user_id)
    if not is_premium:
        await message.answer("⛔️ Доступно только для Premium подписчиков")
        return
    
    # Получаем топ-новости из БД (приоритет >= 8)
    try:
        news_list = await db.get_news_for_period(hours=24, min_priority=8)
        
        if not news_list:
            await message.answer(
                "📰 За последние 24 часа нет топовых новостей.\n"
                "Проверьте позже!"
            )
            return
        
        # Формируем сообщение
        text = "💡 <b>Топовые новости за 24 часа:</b>\n\n"
        for idx, news in enumerate(news_list[:5], 1):  # Макс 5 новостей
            text += f"{idx}. <b>{news['title']}</b>\n"
            if news.get('summary'):
                text += f"{news['summary'][:200]}...\n"
            text += f"🔗 <a href='{news['url']}'>Читать</a>\n\n"
        
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Ошибка получения рекомендаций: {e}")
        await message.answer("⚠️ Ошибка загрузки рекомендаций")


@router.message(F.text == "🎓 Обучающий Курс")
async def premium_education(message: Message):
    """Обучающие материалы"""
    user_id = message.from_user.id
    
    is_premium = await db.check_subscription(user_id)
    if not is_premium:
        await message.answer("⛔️ Доступно только для Premium подписчиков")
        return
    
    await message.answer(
        "🎓 <b>Обучающий курс</b>\n\n"
        "Доступ к учебным материалам:\n"
        "• Основы технического анализа\n"
        "• Риск-менеджмент\n"
        "• Психология трейдинга\n"
        "• Стратегии торговли\n\n"
        "Материалы скоро будут добавлены!",
        parse_mode="HTML"
    )


@router.message(F.text == "⚙️ Мой Аккаунт")
async def show_account_info(message: Message):
    """Информация об аккаунте"""
    user_id = message.from_user.id
    
    user = await db.get_user(user_id)
    if not user:
        await message.answer("⚠️ Ошибка получения данных аккаунта")
        return
    
    is_premium = await db.check_subscription(user_id)
    
    text = f"⚙️ <b>Ваш аккаунт</b>\n\n"
    text += f"👤 ID: {user_id}\n"
    text += f"📛 Имя: {user['full_name']}\n"
    
    if is_premium and user.get('subscription_end'):
        end_date = datetime.fromisoformat(user['subscription_end'])
        text += f"\n👑 <b>Статус:</b> Premium\n"
        text += f"📅 <b>Активна до:</b> {end_date.strftime('%d.%m.%Y %H:%M')}\n"
    else:
        text += f"\n📱 <b>Статус:</b> Бесплатный\n"
    
    if user.get('total_purchases', 0) > 0:
        text += f"\n💰 Всего покупок: {user['total_purchases']}\n"
        text += f"⭐️ Потрачено звёзд: {user['lifetime_spent']}\n"
    
    text += f"\n📆 Регистрация: {user.get('joined_at', 'Н/Д')}"
    
    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "👑 Поддержка")
async def premium_support(message: Message):
    """Поддержка для Premium"""
    await message.answer(
        "👑 <b>Premium поддержка</b>\n\n"
        "Как Premium подписчик, вы получаете приоритетную поддержку:\n\n"
        "💬 Напишите @admin_username\n"
        "📧 Email: premium@example.com\n\n"
        "⚡️ Обычно отвечаем в течение 2-4 часов",
        parse_mode="HTML"
    )

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from database import db
from loader import bot
from keyboards.reply import get_free_menu, get_premium_menu, get_giveaway_menu

router = Router()
logger = logging.getLogger(__name__)


# === ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ ===

@router.message(F.text == "🎁 Что внутри Premium?")
async def show_premium_features(message: Message):
    """Показать функции Premium"""
    await message.answer(
        "💎 <b>PREMIUM-ПОДПИСКА</b>\n\n"
        "🎯 <b>Эксклюзивный доступ:</b>\n\n"
        "📊 <b>Premium-сигналы</b>\n"
        "• Закрытый канал с торговыми сигналами\n"
        "• Futures и Spot сделки\n"
        "• Детальные точки входа/выхода\n"
        "• Реальная статистика профита\n\n"
        "🤖 <b>AI-клон Аналитик</b>\n"
        "• Персональный помощник 24/7\n"
        "• Анализ рынка в реальном времени\n"
        "• Прогнозы и рекомендации\n"
        "• Ответы на ваши вопросы\n\n"
        "📈 <b>Мой Аккаунт</b>\n"
        "• Детальная статистика\n"
        "• История сделок и результатов\n"
        "• Персональные настройки\n"
        "• Доступ ко всем фичам\n\n"
        "🆘 <b>Premium-поддержка</b>\n"
        "• Приоритетные ответы от команды\n"
        "• Среднее время ответа: меньше 30 мин\n"
        "• Прямая связь с основателем\n\n"
        "💎 <b>VIP-услуги:</b>\n"
        "• 💰 Разбор кошелька (300$)\n"
        "• 💎 VIP-консультация (350$)\n\n"
        "💰 <b>Стоимость:</b> от 700$ / месяц\n"
        "🎁 <b>Скидка 100$</b> при подписке на канал!\n\n"
        "Трансформируйте свой трейдинг!",
        parse_mode="HTML"
    )


@router.message(F.text == "📚 Наши ресурсы")
async def show_resources(message: Message):
    """Показать бесплатные ресурсы"""
    await message.answer(
        "📚 <b>БЕСПЛАТНЫЕ РЕСУРСЫ</b>\n\n"
        "📰 <b>Основной канал</b>\n"
        "Мои мысли, аналитика и сигналы.\n"
        "➡️ <a href=\"https://t.me/blexler_invest\">BLEXLER-канал</a>\n\n"
        "💬 <b>Чат сообщества</b>\n"
        "Общайтесь с единомышленниками!\n"
        "➡️ <a href=\"https://t.me/+514GO2tFjAtkMWRi\">ОТКРЫТЫЙ ЧАТ BLEXLER</a>\n\n"
        "Присоединяйтесь к нашему сообществу! 🚀",
        parse_mode="HTML",
        disable_web_page_preview=True
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
async def show_support(message: Message):
    """Показать контакты поддержки"""
    await message.answer(
        "📞 <b>Поддержка</b>\n\n"
        "По всем вопросам обращайтесь:\n"
        "👤 @blexler\n\n"
        "Ответим в течение 24 часов! 😊",
        parse_mode="HTML"
    )


# === ПОДМЕНЮ РОЗЫГРЫША ===

@router.message(F.text == "🎁 Розыгрыш BLEXLER")
async def show_giveaway_menu(message: Message):
    """Показать подменю розыгрыша"""
    user_id = message.from_user.id
    
    # Получаем данные пользователя
    user = await db.get_user(user_id)
    level = user.get('level', 1) if user else 1
    xp = user.get('xp', 0) if user else 0
    
    await message.answer(
        "🎁 <b>РОЗЫГРЫШ BLEXLER</b>\n\n"
        "🏆 <b>ГЛАВНЫЙ ПРИЗ:</b>\n"
        "Персональное обучение торговле от BLEXLER!\n\n"
        "✨ <b>Что вы получите:</b>\n"
        "• Индивидуальная программа обучения\n"
        "• Личные сессии с экспертом\n"
        "• Проверка и корректировка стратегии\n"
        "• Психология успешного трейдера\n"
        "• Доступ к приватным инсайтам\n"
        "• Сопровождение на 3 месяца\n\n"
        "💰 <b>Стоимость обучения: >1500$</b>\n"
        "🎯 <b>Победитель:</b> Определяется по рейтингу XP\n\n"
        f"📊 <b>Ваш прогресс:</b>\n"
        f"• Уровень: {level}\n"
        f"• XP: {xp}\n\n"
        "⚡ <b>Зарабатывайте XP за активность:</b>\n"
        "• Реферальная программа\n"
        "• Проверка Instagram Stories\n"
        "• Ежедневная активность\n\n"
        "Чем больше XP - тем выше в рейтинге!\n\n"
        "Нажмите \"❓ Как участвовать?\" для подробностей.",
        reply_markup=get_giveaway_menu(),
        parse_mode="HTML"
    )


@router.message(F.text == "❓ Как участвовать?")
async def show_giveaway_rules(message: Message):
    """Показать правила розыгрыша"""
    user_id = message.from_user.id
    
    # Получаем данные пользователя
    user = await db.get_user(user_id)
    level = user.get('level', 1) if user else 1
    xp = user.get('xp', 0) if user else 0
    
    await message.answer(
        "❓ <b>КАК УЧАСТВОВАТЬ В РОЗЫГРЫШЕ?</b>\n\n"
        "📋 <b>Шаг 1: Регистрация</b>\n"
        "• Вы уже зарегистрированы! ✅\n"
        f"• Ваш уровень: {level} (XP: {xp})\n\n"
        "⚡ <b>Шаг 2: Зарабатывайте XP</b>\n\n"
        "📎 <b>Реферальная программа:</b>\n"
        "• Приглашайте друзей по своей ссылке\n"
        "• +50 XP за каждого реферала\n"
        "• Дополнительно +25 XP и +10 XP за рефералов 2-го и 3-го уровня\n\n"
        "📸 <b>Instagram Stories:</b>\n"
        "• Выложите Stories с упоминанием @blexler_invest\n"
        "• Сделайте скриншот Stories\n"
        "• Отправьте боту для проверки\n"
        "• +100 XP за успешную проверку\n"
        "• Лимит: 5 проверок в день\n\n"
        "💎 <b>Premium подписка:</b>\n"
        "• Активируйте Premium\n"
        "• +100 XP сразу\n\n"
        "🏆 <b>Шаг 3: Следите за Рейтингом</b>\n"
        "• Проверяйте \"🏆 Топ Участников\"\n"
        "• Занимайте топовые позиции\n"
        "• Зарабатывайте достижения\n\n"
        "🎁 <b>Шаг 4: Призы</b>\n"
        "• Розыгрыш проводится <b>каждый месяц</b>\n"
        "• Победители определяются по рейтингу XP\n"
        "• Следите за объявлениями в канале!\n\n"
        "💡 <b>Совет:</b> Комбинируйте все способы заработка XP для максимального результата!",
        parse_mode="HTML"
    )


@router.message(F.text == "🔙 Главное Меню")
async def back_to_main_menu(message: Message):
    """Возврат в главное меню"""
    user_id = message.from_user.id
    
    # Проверяем статус пользователя
    user = await db.get_user(user_id)
    is_premium = user.get('status') == 'premium' if user else False
    
    if is_premium:
        menu = get_premium_menu(user_id)
        text = "👑 <b>Premium Меню</b>"
    else:
        menu = get_free_menu(user_id)
        text = "🏠 <b>Главное Меню</b>"
    
    await message.answer(text, reply_markup=menu, parse_mode="HTML")


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


# === КОНСУЛЬТАЦИИ ===

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, CallbackQuery

@router.message(F.text == "💼 Консультация")
async def handle_consultation_request(message: Message):
    """Запрос платной консультации"""
    await message.answer(
        "💼 <b>Личная консультация</b>\n\n"
        "📋 <b>Что входит:</b>\n"
        "• Детальный разбор портфеля\n"
        "• Персональные рекомендации\n"
        "• Стратегия на месяц\n"
        "• Ответы на все вопросы\n\n"
        "⏱ <b>Длительность:</b> 60 минут\n"
        "💰 <b>Стоимость:</b> 27,000 ⭐️ (~$300)\n\n"
        "Готовы заказать?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", callback_data="buy_consultation")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])
    )


@router.callback_query(F.data == "buy_consultation")
async def process_consultation_payment(callback: CallbackQuery):
    """Обработка покупки консультации"""
    user_id = callback.from_user.id
    
    try:
        await callback.message.answer_invoice(
            title="💼 Личная консультация",
            description="60-минутная консультация: разбор портфеля, стратегия, рекомендации",
            payload=f"consultation_{user_id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Консультация (60 мин)", amount=27000)]
        )
        await callback.answer("💳 Счёт отправлен")
        logger.info(f"💼 Запрос консультации: {user_id}")
    except Exception as e:
        logger.error(f"Ошибка invoice консультации: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)

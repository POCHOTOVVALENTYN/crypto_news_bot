import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_ID, config
from database import db
from loader import bot

logger = logging.getLogger(__name__)

router = Router()

# === СОСТОЯНИЯ ===
class AdminStates(StatesGroup):
    main_menu = State()
    waiting_for_post_content = State()
    waiting_for_post_photo = State()  # Если с фото
    editing_footer = State()

# === КЛАВИАТУРЫ ===
def get_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Создать публикацию"), KeyboardButton(text="📅 Дайджесты")],
            [KeyboardButton(text="⚙️ Настройки футера"), KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главная"), KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

def get_publication_type_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 С фото", callback_data="pub_type_photo"),
             InlineKeyboardButton(text="📝 Без фото", callback_data="pub_type_text")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ]
    )

# === ОБРАБОТЧИКИ ===

@router.message(Command("start"), F.from_user.id == int(ADMIN_ID))
@router.message(Command("menu"), F.from_user.id == int(ADMIN_ID))
async def cmd_admin_menu(message: Message, state: FSMContext):
    """Главное меню админа"""
    await state.clear()
    await message.answer(
        "👋 Привет, Админ! Что будем делать?",
        reply_markup=get_main_menu_keyboard()
    )

@router.message(F.text == "🏠 Главная", F.from_user.id == int(ADMIN_ID))
async def nav_main_menu(message: Message, state: FSMContext):
    await cmd_admin_menu(message, state)

@router.message(F.text == "🔙 Назад", F.from_user.id == int(ADMIN_ID))
async def nav_back(message: Message, state: FSMContext):
    # Логика "Назад" зависит от контекста, но пока просто в главное меню
    await cmd_admin_menu(message, state)


# --- СТАТИСТИКА ---
@router.message(F.text == "📊 Статистика", F.from_user.id == int(ADMIN_ID))
async def show_statistics(message: Message):
    stats = await db.get_statistics()
    text = (
        "📊 <b>Статистика бота:</b>\n\n"
        f"📂 Всего новостей: {stats.get('total_news', 0)}\n"
        f"✅ Опубликовано: {stats.get('posted_count', 0)}\n"
        f"⏳ В очереди: {stats.get('queue_count', 0)}\n"
        f"📅 За сегодня: {stats.get('today_count', 0)}\n"
    )
    await message.answer(text, parse_mode="HTML")


# --- АНАЛИТИКА ПРОДАЖ ---
@router.message(Command("sales"), F.from_user.id == int(ADMIN_ID))
async def cmd_sales_analytics(message: Message):
    """Подробная аналитика продаж и воронки"""
    try:
        sales_stats = await db.get_sales_analytics()
        user_stats = await db.get_user_statistics()
        
        text = (
            "💰 <b>Аналитика продаж:</b>\n\n"
            
            f"👥 <b>Пользователи:</b>\n"
            f"• Всего: {user_stats.get('total_users', 0)}\n"
            f"• Бесплатные: {user_stats.get('free_users', 0)}\n"
            f"• Premium: {user_stats.get('premium_users', 0)}\n\n"
            
            f"📊 <b>Воронка продаж:</b>\n"
            f"• Показов оффера: {sales_stats.get('total_offers_shown', 0)}\n"
            f"• Возражений по цене: {sales_stats.get('price_objections', 0)}\n"
            f"• Конверсия в возражение: {round(sales_stats.get('price_objections', 0) / max(sales_stats.get('total_offers_shown', 1), 1) * 100, 1)}%\n\n"
            
            f"💵 <b>Продажи:</b>\n"
            f"• По полной цене (500⭐️): {sales_stats.get('full_price_sales', 0)}\n"
            f"• Со скидкой (400⭐️): {sales_stats.get('discount_sales', 0)}\n"
            f"• Всего продаж: {sales_stats.get('full_price_sales', 0) + sales_stats.get('discount_sales', 0)}\n\n"
            
            f"📈 <b>Метрики:</b>\n"
            f"• Общий доход: {sales_stats.get('total_revenue', 0)} ⭐️\n"
            f"• Средний чек: {sales_stats.get('average_check', 0)} ⭐️\n"
            f"• Конверсия воронки: {sales_stats.get('conversion_rate', 0)}%\n"
            f"• Процент скидок: {sales_stats.get('discount_usage_rate', 0)}%\n"
        )
        
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка получения аналитики продаж: {e}")
        await message.answer(f"⚠️ Ошибка получения аналитики: {e}")


# --- РУЧНАЯ ПУБЛИКАЦИЯ ---
@router.message(F.text == "📝 Создать публикацию", F.from_user.id == int(ADMIN_ID))
async def start_publication(message: Message, state: FSMContext):
    await message.answer(
        "Какую публикацию создаем?",
        reply_markup=get_publication_type_keyboard()
    )

@router.callback_query(F.data == "cancel_action")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer("Отменено.", reply_markup=get_main_menu_keyboard())
    await state.clear()

@router.callback_query(F.data == "pub_type_text")
async def pub_type_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_post_content)
    await state.update_data(has_photo=False)
    await callback.message.edit_text("✍️ Пришлите текст публикации (HTML поддерживается):")

@router.callback_query(F.data == "pub_type_photo")
async def pub_type_photo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_post_content)
    await state.update_data(has_photo=True)
    await callback.message.edit_text("📸 Пришлите фото с описанием (caption) или просто фото, а потом текст:")

@router.message(AdminStates.waiting_for_post_content, F.from_user.id == int(ADMIN_ID))
async def process_post_content(message: Message, state: FSMContext):
    data = await state.get_data()
    has_photo = data.get('has_photo')

    text = message.html_text if message.text else (message.caption if message.caption else "")
    photo_id = message.photo[-1].file_id if message.photo else None

    if has_photo and not photo_id:
        if not text:
             await message.answer("⚠️ Нужно прислать фото!")
             return
        # Если прислали текст, но мы ждем фото - может они хотят сначала фото? 
        # Но для простоты: если выбрали фото, ждем сообщение с фото.
        await message.answer("⚠️ Вы выбрали режим 'С фото'. Пришлите изображение.")
        return

    # Подтверждение
    await state.update_data(final_text=text, final_photo=photo_id)
    
    # Показываем превью
    preview_text = "<b>👀 Предпросмотр:</b>\n\n" + text
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="confirm_post")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])

    if photo_id:
        await message.answer_photo(photo_id, caption=preview_text, parse_mode="HTML", reply_markup=confirm_kb)
    else:
        await message.answer(preview_text, parse_mode="HTML", reply_markup=confirm_kb)

@router.callback_query(F.data == "confirm_post")
async def confirm_post(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('final_text')
    photo_id = data.get('final_photo')
    
    try:
        if photo_id:
            await bot.send_photo(chat_id=config.telegram_channel_id, photo=photo_id, caption=text, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=config.telegram_channel_id, text=text, parse_mode="HTML")
        
        await callback.message.answer("✅ Успешно опубликовано!", reply_markup=get_main_menu_keyboard())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка публикации: {e}", reply_markup=get_main_menu_keyboard())
    
    await state.clear()


# --- НАСТРОЙКИ ФУТЕРА ---
@router.message(F.text == "⚙️ Настройки футера", F.from_user.id == int(ADMIN_ID))
async def edit_footer_start(message: Message, state: FSMContext):
    current_footer = await db.get_setting("footer_template", "По умолчанию")
    await state.set_state(AdminStates.editing_footer)
    
    await message.answer(
        f"📝 <b>Текущий шаблон футера:</b>\n<pre>{current_footer}</pre>\n\n"
        "Пришлите новый шаблон html-текста. Используйте {prices}, {fear}, {sentiment} для подстановки (пока не реализовано динамически, просто текст):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminStates.editing_footer, F.from_user.id == int(ADMIN_ID))
async def save_footer(message: Message, state: FSMContext):
    if message.text in ["🏠 Главная", "🔙 Назад"]:
        await cmd_admin_menu(message, state)
        return

    new_footer = message.html_text
    await db.set_setting("footer_template", new_footer)
    await message.answer("✅ Шаблон футера сохранен!", reply_markup=get_main_menu_keyboard())
    await state.clear()
    await db.set_setting("footer_template", new_footer)
    await message.answer("✅ Шаблон футера сохранен!", reply_markup=get_main_menu_keyboard())
    await state.clear()


# --- ДАЙДЖЕСТЫ ---

def get_digest_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌞 Суточный (24ч)", callback_data="digest_daily"),
             InlineKeyboardButton(text="🗓 Недельный (7д)", callback_data="digest_weekly")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
        ]
    )

@router.message(F.text == "📅 Дайджесты", F.from_user.id == int(ADMIN_ID))
async def digest_menu(message: Message):
    await message.answer(
        "Какой дайджест сгенерировать?",
        reply_markup=get_digest_keyboard()
    )

@router.callback_query(F.data == "digest_daily")
async def manual_daily_digest(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Генерирую суточный дайджест... Это может занять минуту.")
    from services.scheduler_tasks import daily_digest_task
    # Запускаем задачу
    # Важно: daily_digest_task отправляет сообщение в канал.
    # Мы можем захотеть увидеть его в личке, но пока пусть шлет в канал как положено,
    # а админу пришем отчет.
    try:
        await daily_digest_task()
        await callback.message.answer("✅ Суточный дайджест отправлен в канал!")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == "digest_weekly")
async def manual_weekly_digest(callback: CallbackQuery):
    await callback.message.edit_text("⏳ Генерирую недельный дайджест... Ждите.")
    from services.scheduler_tasks import weekly_digest_task
    try:
        await weekly_digest_task()
        await callback.message.answer("✅ Недельный дайджест отправлен в канал!")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

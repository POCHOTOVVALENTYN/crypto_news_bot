"""
Meeting Scheduler - Планирование встреч для консультаций
Простой календарь выбора даты и времени
"""
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database import db
from loader import bot
from config import CONSULTATION_PRICES, ADMIN_NAMES
from utils.states import ConsultationState
from services.meeting_reminders import create_meeting_reminders

router = Router()
logger = logging.getLogger(__name__)


# === ПРОСТОЙ КАЛЕНДАРЬ ===

def generate_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    """Генерация простого календаря на месяц"""
    
    import calendar
    
    # Получаем календарь месяца
    cal = calendar.monthcalendar(year, month)
    
    # Название месяца
    month_names = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    
    buttons = []
    
    # Заголовок с месяцем и годом
    buttons.append([
        InlineKeyboardButton(
            text=f"📅 {month_names[month-1]} {year}",
            callback_data="calendar_ignore"
        )
    ])
    
    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons.append([
        InlineKeyboardButton(text=day, callback_data="calendar_ignore")
        for day in week_days
    ])
    
    # Дни месяца
    today = datetime.now().date()
    
    for week in cal:
        week_buttons = []
        for day in week:
            if day == 0:
                # Пустая ячейка
                week_buttons.append(
                    InlineKeyboardButton(text=" ", callback_data="calendar_ignore")
                )
            else:
                date = datetime(year, month, day).date()
                
                # Пропускаем прошедшие дни
                if date < today:
                    week_buttons.append(
                        InlineKeyboardButton(text="✖️", callback_data="calendar_ignore")
                    )
                else:
                    # Доступная дата
                    callback_data = f"date_{year}_{month}_{day}"
                    week_buttons.append(
                        InlineKeyboardButton(text=str(day), callback_data=callback_data)
                    )
        
        buttons.append(week_buttons)
    
    # Навигация по месяцам
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    buttons.append([
        InlineKeyboardButton(text="◀️", callback_data=f"calendar_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text="Отмена", callback_data="calendar_cancel"),
        InlineKeyboardButton(text="▶️", callback_data=f"calendar_{next_year}_{next_month}")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def generate_time_slots(selected_date: str) -> InlineKeyboardMarkup:
    """Генерация временных слотов на день"""
    
    # Рабочие часы: 9:00 - 18:00
    hours = list(range(9, 19))
    
    buttons = []
    
    # Заголовок
    buttons.append([
        InlineKeyboardButton(
            text=f"🕐 Выберите время на {selected_date}",
            callback_data="time_ignore"
        )
    ])
    
    # Слоты по 2 в строке
    row = []
    for hour in hours:
        time_str = f"{hour:02d}:00"
        row.append(
            InlineKeyboardButton(
                text=time_str,
                callback_data=f"time_{time_str}"
            )
        )
        
        if len(row) == 2:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    # Кнопка назад
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад к календарю", callback_data="time_back")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# === НАЧАЛО ПЛАНИРОВАНИЯ ===

@router.callback_query(F.data == "schedule_meeting")
async def start_meeting_scheduling(callback: CallbackQuery, state: FSMContext):
    """Начать планирование встречи после оплаты консультации"""
    
    await callback.answer()
    
    # Получаем данные из FSM
    data = await state.get_data()
    consultation_id = data.get('consultation_id')
    
    if not consultation_id:
        await callback.message.answer("❌ Ошибка: консультация не найдена")
        await state.clear()
        return
    
    # Показываем календарь
    now = datetime.now()
    calendar_kb = generate_calendar(now.year, now.month)
    
    await callback.message.edit_text(
        "📅 <b>Планирование встречи</b>\n\n"
        "Выберите удобную дату:",
        parse_mode="HTML",
        reply_markup=calendar_kb
    )
    
    await state.set_state(ConsultationState.selecting_date)


# === НАВИГАЦИЯ ПО КАЛЕНДАРЮ ===

@router.callback_query(F.data.startswith("calendar_"))
async def handle_calendar_navigation(callback: CallbackQuery, state: FSMContext):
    """Навигация по месяцам календаря"""
    
    action = callback.data.split("_", 1)[1]
    
    if action == "ignore":
        await callback.answer()
        return
    
    if action == "cancel":
        await callback.message.edit_text(
            "❌ Планирование отменено.\n\n"
            "Вы можете запланировать встречу позже через поддержку."
        )
        await state.clear()
        await callback.answer()
        return
    
    # Парсим год и месяц
    try:
        year, month = map(int, action.split("_"))
        calendar_kb = generate_calendar(year, month)
        
        await callback.message.edit_reply_markup(reply_markup=calendar_kb)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка навигации календаря: {e}")
        await callback.answer("Ошибка календаря")


# === ВЫБОР ДАТЫ ===

@router.callback_query(F.data.startswith("date_"), ConsultationState.selecting_date)
async def handle_date_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора даты"""
    
    # Парсим дату
    try:
        _, year, month, day = callback.data.split("_")
        selected_date = datetime(int(year), int(month), int(day))
        
        # Проверяем что дата в будущем
        if selected_date.date() < datetime.now().date():
            await callback.answer("❌ Выберите будущую дату", show_alert=True)
            return
        
        # Сохраняем дату
        await state.update_data(selected_date=selected_date.strftime("%Y-%m-%d"))
        
        # Показываем выбор времени
        date_display = selected_date.strftime("%d.%m.%Y")
        time_kb = generate_time_slots(date_display)
        
        await callback.message.edit_text(
            f"📅 Дата: <b>{date_display}</b>\n\n"
            f"🕐 Теперь выберите время:",
            parse_mode="HTML",
            reply_markup=time_kb
        )
        
        await state.set_state(ConsultationState.selecting_time)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка выбора даты: {e}")
        await callback.answer("Ошибка выбора даты")


# === ВЫБОР ВРЕМЕНИ ===

@router.callback_query(F.data == "time_back", ConsultationState.selecting_time)
async def time_back_to_calendar(callback: CallbackQuery, state: FSMContext):
    """Вернуться к выбору даты"""
    
    now = datetime.now()
    calendar_kb = generate_calendar(now.year, now.month)
    
    await callback.message.edit_text(
        "📅 <b>Планирование встречи</b>\n\n"
        "Выберите удобную дату:",
        parse_mode="HTML",
        reply_markup=calendar_kb
    )
    
    await state.set_state(ConsultationState.selecting_date)
    await callback.answer()


@router.callback_query(F.data == "time_ignore")
async def time_ignore(callback: CallbackQuery):
    """Игнорируем нажатия на заголовок"""
    await callback.answer()


@router.callback_query(F.data.startswith("time_"), ConsultationState.selecting_time)
async def handle_time_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора времени"""
    
    # Парсим время
    try:
        time_str = callback.data.split("_", 1)[1]
        
        # Получаем сохранённую дату
        data = await state.get_data()
        selected_date = data.get('selected_date')
        consultation_id = data.get('consultation_id')
        
        if not selected_date or not consultation_id:
            await callback.answer("❌ Ошибка данных", show_alert=True)
            return
        
        # Формируем полную дату-время
        scheduled_datetime = f"{selected_date} {time_str}:00"
        
        # Сохраняем в БД
        await db.update_consultation_datetime(consultation_id, scheduled_datetime)
        
        # Создаём напоминания
        await create_meeting_reminders(consultation_id, scheduled_datetime)
        
        # Получаем консультацию
        consultation = await db.get_consultation(consultation_id)
        type_name = CONSULTATION_PRICES.get(consultation['type'], {}).get('name', consultation['type'])
        
        # Форматируем для отображения
        dt = datetime.fromisoformat(scheduled_datetime)
        date_display = dt.strftime("%d.%m.%Y")
        time_display = dt.strftime("%H:%M")
        
        # Подтверждение пользователю
        await callback.message.edit_text(
            "✅ <b>Встреча запланирована!</b>\n\n"
            f"📋 {type_name}\n"
            f"📅 Дата: {date_display}\n"
            f"🕐 Время: {time_display}\n\n"
            "🔔 Вы получите напоминания:\n"
            "• За 24 часа\n"
            "• За 1 час\n\n"
            "До встречи!",
            parse_mode="HTML"
        )
        
        # Уведомляем основателя
        user_id = consultation['user_id']
        user = await db.get_user(user_id)
        username = f"@{user['username']}" if user.get('username') else f"ID:{user_id}"
        
        await bot.send_message(
            304050247,
            f"📅 <b>Новая консультация запланирована</b>\n\n"
            f"👤 {user.get('full_name', 'Пользователь')} {username}\n"
            f"📋 {type_name}\n"
            f"📅 {date_display} в {time_display}\n\n"
            f"Консультация ID: {consultation_id}",
            parse_mode="HTML"
        )
        
        logger.info(f"✅ Встреча запланирована: консультация {consultation_id} на {scheduled_datetime}")
        
        await state.clear()
        await callback.answer("✅ Встреча запланирована!")
        
    except Exception as e:
        logger.error(f"Ошибка выбора времени: {e}", exc_info=True)
        await callback.answer("❌ Ошибка планирования", show_alert=True)


logger.info("✅ Meeting Scheduler handlers зарегистрированы")

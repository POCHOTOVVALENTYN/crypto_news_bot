import logging
from typing import Optional, Union
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import config, USDT_TRC20_ADDRESS
from database import db
from loader import bot

logger = logging.getLogger(__name__)

class PaymentManager:
    """Manager for Manual USDT Payments & Premium Activation"""
    
    PRICE_USDT = 800  # Fixed price for now
    CURRENCY = "USDT (TRC-20)"
    
    @staticmethod
    async def send_invoice(chat_id: int):
        """Sends manual payment invoice"""
        text = (
            f"💎 <b>Premium Подписка (1 месяц)</b>\n\n"
            f"💵 Стоимость: <b>{PaymentManager.PRICE_USDT} USDT</b>\n"
            f"🌐 Сеть: <b>TRC-20 (Tron)</b>\n\n"
            f"📍 <b>Ваш адрес для пополнения:</b>\n"
            f"<code>{USDT_TRC20_ADDRESS}</code>\n"
            f"(Нажмите на адрес, чтобы скопировать)\n\n"
            f"⚠️ <b>Инструкция:</b>\n"
            f"1. Переведите ровно {PaymentManager.PRICE_USDT} USDT на указанный адрес.\n"
            f"2. Сохраните Hash транзакции (TxID) или скриншот.\n"
            f"3. Нажмите кнопку <b>«✅ Я оплатил»</b> ниже."
        )
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data="pay_manual_paid")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="pay_back")]
        ])
        
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

    @staticmethod
    async def process_proof(user_id: int, proof_content: Union[str, Message], is_photo: bool = False):
        """Processes user proof (text hash or photo)"""
        try:
            proof_text = None
            proof_file_id = None
            
            if is_photo:
                # proof_content is Message object here
                photo = proof_content.photo[-1]
                proof_file_id = photo.file_id
                caption = proof_content.caption
                if caption:
                    proof_text = caption
            else:
                proof_text = proof_content # it's a string

            # 1. Create Order in DB
            order_id = await db.create_payment_order(
                user_id=user_id,
                amount=PaymentManager.PRICE_USDT,
                currency=PaymentManager.CURRENCY,
                proof_file_id=proof_file_id,
                proof_text=proof_text
            )
            
            if not order_id:
                await bot.send_message(user_id, "❌ Ошибка создания заявки. Попробуйте позже.")
                return

            # 2. Notify Admin
            admin_text = (
                f"💰 <b>Новая заявка на оплату!</b>\n"
                f"👤 Пользователь: {user_id}\n"
                f"💵 Сумма: {PaymentManager.PRICE_USDT} USDT\n"
                f"🆔 Order ID: {order_id}\n\n"
                f"Действие:"
            )
            
            admin_markup = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_pay_approve:{order_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_pay_reject:{order_id}")
                ]
            ])
            
            # Send to Admin Channel or Super Admin
            target_admin_id = config.admin_ids[0] if config.admin_ids else 830196453 # Fallback to hardcoded ID if empty
            
            if is_photo:
                await bot.send_photo(target_admin_id, proof_file_id, caption=admin_text, parse_mode="HTML", reply_markup=admin_markup)
            else:
                final_text = f"{admin_text}\n\n📝 Hash: <code>{proof_text}</code>"
                await bot.send_message(target_admin_id, final_text, parse_mode="HTML", reply_markup=admin_markup)
                
            # 3. Notify User
            await bot.send_message(user_id, "✅ <b>Ваша заявка принята!</b>\nМы проверим оплату и активируем подписку в ближайшее время.", parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Error handling payment proof: {e}", exc_info=True)
            await bot.send_message(user_id, "❌ Произошла ошибка при обработке заявки.")

    @staticmethod
    async def approve_order(order_id: int, admin_id: int):
        """Admin approves order -> Activate Premium"""
        order = await db.get_payment_order(order_id)
        if not order:
            return False, "Заявка не найдена"
            
        if order['status'] != 'pending':
            return False, f"Статус уже {order['status']}"
            
        # 1. Update DB
        if await db.update_payment_order_status(order_id, 'approved', admin_id):
            user_id = order['user_id']
            # 2. Activate Premium (30 days)
            await db.set_subscription(user_id, days=config.premium_duration_days)
            
            # 3. Notify User
            try:
                await bot.send_message(
                    user_id, 
                    "🎉 <b>Оплата подтверждена!</b>\n\n"
                    "Premium доступ активирован на 30 дней.\n"
                    "Спасибо за поддержку! 🚀", 
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not notify user {user_id}: {e}")
                
            return True, "Успешно одобрено"
        return False, "Ошибка БД"

    @staticmethod
    async def reject_order(order_id: int, admin_id: int):
        """Admin rejects order"""
        order = await db.get_payment_order(order_id)
        if not order:
            return False, "Заявка не найдена"
            
        if await db.update_payment_order_status(order_id, 'rejected', admin_id):
            user_id = order['user_id']
            try:
                await bot.send_message(user_id, "❌ <b>Ваша оплата не подтверждена.</b>\nЕсли произошла ошибка, свяжитесь с поддержкой.", parse_mode="HTML")
            except: pass
            return True, "Заявка отклонена"
        return False, "Ошибка БД"

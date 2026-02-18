import logging
from typing import Optional, Union
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import config, USDT_TRC20_ADDRESS
from database import db
from loader import bot
from keyboards.reply import get_premium_menu

logger = logging.getLogger(__name__)

class PaymentManager:
    """Manager for Manual USDT Payments & Premium Activation"""
    
    PRICE_USDT = 800  # Fixed price for now
    CURRENCY = "USDT (TRC-20)"
    
    @staticmethod
    async def send_invoice(chat_id: int, custom_price: float = None, service_type: str = 'premium', 
                           title: str = None, description: str = None):
        """Sends manual payment invoice (standard or custom price)"""
        
        price = custom_price if custom_price else PaymentManager.PRICE_USDT
        
        if not title:
            if service_type == 'premium':
                title = "💎 <b>Premium Подписка (1 месяц)</b>"
            elif service_type == 'wallet_review':
                title = "💰 <b>Разбор Кошелька</b>"
            elif service_type == 'vip_consultation':
                title = "💎 <b>VIP-консультация</b>"
            else:
                title = "🛍 <b>Оплата услуги</b>"

        if not description:
            description = ""

        text = (
            f"{title}\n\n"
            f"{description}\n"
            f"💵 Стоимость: <b>{price} USDT</b>\n"
            f"🌐 Сеть: <b>TRC-20 (Tron)</b>\n\n"
        )
            
        text += (
            f"📍 <b>Ваш адрес для пополнения:</b>\n"
            f"<code>{USDT_TRC20_ADDRESS}</code>\n"
            f"(Нажмите на адрес, чтобы скопировать)\n\n"
            f"⚠️ <b>Инструкция:</b>\n"
            f"1. Переведите ровно {price} USDT на указанный адрес.\n"
            f"2. Сохраните Hash транзакции (TxID) или скриншот.\n"
            f"3. Нажмите кнопку <b>«✅ Я оплатил»</b> ниже."
        )
        
        # Передаем цену и тип сервиса в callback_data
        # Format: pay_manual_paid:{price}:{service_type}
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ Я оплатил {price} USDT", callback_data=f"pay_manual_paid:{price}:{service_type}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="pay_back")]
        ])
        
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

    @staticmethod
    async def process_proof(user_id: int, proof_content: Union[str, Message], is_photo: bool = False, 
                            amount: float = None, service_type: str = 'premium'):
        """Processes user proof (text hash or photo)"""
        try:
            proof_text = None
            proof_file_id = None
            price = amount if amount else PaymentManager.PRICE_USDT
            
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
                amount=price,
                currency=PaymentManager.CURRENCY,
                proof_file_id=proof_file_id,
                proof_text=proof_text,
                service_type=service_type
            )
            
            if not order_id:
                await bot.send_message(user_id, "❌ Ошибка создания заявки. Попробуйте позже.")
                return

            # 2. Notify Admin
            service_name = service_type.replace('_', ' ').capitalize()
            admin_text = (
                f"💰 <b>Новая заявка на оплату! ({service_name})</b>\n"
                f"👤 Пользователь: {user_id}\n"
                f"💵 Сумма: {price} USDT\n"
                f"🆔 Order ID: {order_id}\n"
                f"🏷 Тип: {service_type}\n\n"
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
                
            # 3. Notify User with Reassurance & Support
            support_username = "Valentin_Pochotov" # Лучше вынести в конфиг, но пока так
            
            user_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🆘 Написать в поддержку", url=f"https://t.me/{support_username}")]
            ])
            
            await bot.send_message(
                user_id, 
                "✅ <b>Ваша заявка и доказательства приняты!</b>\n\n"
                "⏳ <b>Ожидание проверки:</b> обычно 10-30 минут.\n"
                "Мы проверим оплату и свяжемся с вами в ближайшее время.\n\n"
                "Если проверка затянулась, нажмите кнопку ниже:", 
                parse_mode="HTML",
                reply_markup=user_markup
            )
            
        except Exception as e:
            logger.error(f"Error handling payment proof: {e}", exc_info=True)
            await bot.send_message(user_id, "❌ Произошла ошибка при обработке заявки.")

    @staticmethod
    async def approve_order(order_id: int, admin_id: int):
        """Admin approves order -> Activate Service/Premium"""
        order = await db.get_payment_order(order_id)
        if not order:
            return False, "Заявка не найдена"
            
        if order['status'] != 'pending':
            return False, f"Статус уже {order['status']}"
            
        # 1. Update DB
        if await db.update_payment_order_status(order_id, 'approved', admin_id):
            user_id = order['user_id']
            service_type = order.get('service_type', 'premium')
            
            if service_type == 'premium':
                # 2a. Activate Premium (30 days)
                await db.set_subscription(user_id, days=config.premium_duration_days)
                
                # 3a. Notify User (Premium)
                try:
                    await bot.send_message(
                        user_id, 
                        "🎉 <b>Оплата подтверждена!</b>\n\n"
                        "Premium доступ активирован на 30 дней.\n"
                        "Спасибо за поддержку! 🚀\n\n"
                        "👇 <b>Ваше меню обновлено:</b>", 
                        parse_mode="HTML",
                        reply_markup=get_premium_menu()
                    )
                except Exception as e:
                    logger.warning(f"Could not notify user {user_id}: {e}")
            
            else:
                # 2b. Handle Consultation / Other Services
                # Для консультаций мы пока просто уведомляем, что оплата принята.
                # Можно добавить логику создания записи в таблице consultations, если нужно.
                
                service_name = "Услуга"
                if service_type == 'wallet_review':
                    service_name = "Разбор Кошелька"
                elif service_type == 'vip_consultation':
                    service_name = "VIP-консультация"
                
                try:
                    await bot.send_message(
                        user_id,
                        f"🎉 <b>Оплата за «{service_name}» подтверждена!</b>\n\n"
                        "Мы свяжемся с вами в ближайшее время для согласования времени и деталей.\n"
                        "Если у вас есть вопросы, пишите в поддержку.",
                        parse_mode="HTML"
                    )
                     # Уведомляем админа, что нужно связаться
                    target_admin_id = config.admin_ids[0] if config.admin_ids else 830196453
                    await bot.send_message(
                        target_admin_id,
                        f"✅ <b>Оплата подтверждена!</b>\n"
                        f"👤 User: {user_id}\n"
                        f"🏷 Услуга: {service_name}\n\n"
                        f"👉 <a href='tg://user?id={user_id}'>Написать пользователю</a>",
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

    async def save_payment(self, user_id: int, amount_stars: int, amount_usd: int,
                          payment_type: str, telegram_payment_id: str, status: str = 'completed'):
        """Сохранить платёж в БД"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO payments 
                (user_id, amount, amount_usd, payment_type, telegram_payment_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount_stars, amount_usd, payment_type, telegram_payment_id, status, 
                 datetime.now().isoformat())
            )
            payment_id = cursor.lastrowid
            await conn.commit()
            return payment_id
    
    async def create_consultation(self, user_id: int, consultation_type: str,
                                  amount_paid: int, amount_usd: int, payment_id: int = None):
        """Создать консультацию после оплаты"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO consultations
                (user_id, type, amount_paid, amount_usd, payment_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'paid', ?)
                """,
                (user_id, consultation_type, amount_paid, amount_usd, payment_id,
                 datetime.now().isoformat())
            )
            consultation_id = cursor.lastrowid
            await conn.commit()
            return consultation_id
    
    async def update_consultation_datetime(self, consultation_id: int, scheduled_datetime: str):
        """Обновить дату/время консультации"""
        async with self.get_connection() as conn:
            await conn.execute(
                """
                UPDATE consultations
                SET scheduled_datetime = ?, status = 'scheduled'
                WHERE id = ?
                """,
                (scheduled_datetime, consultation_id)
            )
            await conn.commit()
    
    async def get_consultation(self, consultation_id: int):
        """Получить консультацию по ID"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM consultations WHERE id = ?",
                (consultation_id,)
            )
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
        return None
    
    async def create_reminder(self, consultation_id: int, reminder_type: str, scheduled_time: str):
        """Создать напоминание о консультации"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO consultation_reminders
                (consultation_id, reminder_type, scheduled_time, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (consultation_id, reminder_type, scheduled_time, datetime.now().isoformat())
            )
            await conn.commit()
            return cursor.lastrowid
    
    async def mark_reminder_sent(self, reminder_id: int):
        """Отметить напоминание как отправленное"""
        async with self.get_connection() as conn:
            await conn.execute(
                "UPDATE consultation_reminders SET sent = 1 WHERE id = ?",
                (reminder_id,)
            )
            await conn.commit()

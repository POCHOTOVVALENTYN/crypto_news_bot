# auth.py
import asyncio
import os
from telethon import TelegramClient
from config import TG_API_ID, TG_API_HASH

# Принудительно задаем параметры, чтобы Telegram не считал нас ботом
DEVICE_MODEL = "Desktop"
SYSTEM_VERSION = "Windows 10"
APP_VERSION = "4.16.30"


async def main():
    print("🚀 Запуск мастера авторизации...")

    if not TG_API_ID or not TG_API_HASH:
        print("❌ Ошибка: Проверьте TG_API_ID и TG_API_HASH в файле .env")
        return

    # 1. Инициализация чистого клиента
    client = TelegramClient(
        'anon_session',
        TG_API_ID,
        TG_API_HASH,
        device_model=DEVICE_MODEL,
        system_version=SYSTEM_VERSION,
        app_version=APP_VERSION
    )

    await client.connect()

    if not await client.is_user_authorized():
        print("\n☎️ Введите номер телефона в международном формате.")
        print("Пример: +380631234567 (Обязательно с плюсом!)")

        phone = input("Ваш номер: ").strip()

        if not phone.startswith('+'):
            print("⚠️ Ошибка: Номер должен начинаться с '+'")
            return

        try:
            await client.send_code_request(phone)
            print("\n✅ Код отправлен! Проверьте приложение Telegram (на телефоне или ПК).")
            print("Это НЕ СМС, код придет в чат от Telegram.")
        except Exception as e:
            print(f"\n❌ Ошибка отправки кода: {e}")
            return

        code = input("Введите код из Telegram: ")

        try:
            await client.sign_in(phone, code)
        except Exception as e:
            if "password" in str(e).lower():
                password = input("🔐 Введите ваш облачный пароль (2FA): ")
                await client.sign_in(password=password)
            else:
                print(f"❌ Ошибка входа: {e}")
                return

    user = await client.get_me()
    print(f"\n🎉 Успешно! Вы вошли как: {user.first_name} (@{user.username})")
    print("💾 Файл сессии 'anon_session.session' создан.")
    print("👉 Теперь запускайте 'python main.py'")

    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
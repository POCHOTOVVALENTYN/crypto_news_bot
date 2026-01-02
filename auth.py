# auth.py
from telethon import TelegramClient
from config import TG_API_ID, TG_API_HASH
import asyncio


async def main():
    print("🚀 Запуск модуля авторизации...")

    if not TG_API_ID or not TG_API_HASH:
        print("❌ Ошибка: В .env не указаны TG_API_ID или TG_API_HASH")
        return

    # Используем стандартные параметры, убираем system_version
    client = TelegramClient('anon_session', TG_API_ID, TG_API_HASH)

    print("⏳ Соединение с Telegram...")
    await client.start()

    print("✅ Успешная авторизация!")
    me = await client.get_me()
    print(f"👤 Вы вошли как: {me.first_name} (@{me.username})")
    print("💾 Файл сессии 'anon_session.session' создан.")
    print("🎉 Теперь можно запускать основного бота (python main.py)")

    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
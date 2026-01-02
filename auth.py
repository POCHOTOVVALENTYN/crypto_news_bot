# auth.py
"""
Интерактивная авторизация Userbot для Telegram.
Создает сессию и выводит TG_SESSION_STRING для добавления в .env
"""
import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError
from config import TG_API_ID, TG_API_HASH


async def main():
    print("=" * 60)
    print("🔐 МАСТЕР АВТОРИЗАЦИИ USERBOT")
    print("=" * 60)
    print()

    # Проверка конфигурации
    if not TG_API_ID or TG_API_ID == 0:
        print("❌ Ошибка: TG_API_ID не установлен в .env")
        print("💡 Получите на https://my.telegram.org")
        return 1

    if not TG_API_HASH:
        print("❌ Ошибка: TG_API_HASH не установлен в .env")
        print("💡 Получите на https://my.telegram.org")
        return 1

    # Используем StringSession для получения строки сессии
    session = StringSession()
    client = TelegramClient(session, TG_API_ID, TG_API_HASH)

    try:
        print("🔌 Подключение к Telegram...")
        await client.connect()

        if not await client.is_user_authorized():
            print("\n📱 ТРЕБУЕТСЯ АВТОРИЗАЦИЯ")
            print("-" * 60)

            # Ввод номера телефона
            print("\n☎️ Введите номер телефона в международном формате:")
            print("   Пример: +380635609097 (обязательно с плюсом!)")
            phone = input("\nВаш номер: ").strip()

            if not phone.startswith('+'):
                print("❌ Ошибка: Номер должен начинаться с '+' (например, +380635609097)")
                await client.disconnect()
                return 1

            # Запрос кода
            print("\n⏳ Отправка кода подтверждения...")
            try:
                await client.send_code_request(phone)
                print("✅ Код отправлен!")
                print("\n📬 ВАЖНО: Код придет в ОТКРЫТОЕ приложение Telegram")
                print("   (на телефоне или ПК, где вы уже авторизованы)")
                print("   Это НЕ СМС, а сообщение в чате от Telegram")
            except PhoneNumberInvalidError:
                print(f"❌ Ошибка: Неверный номер телефона: {phone}")
                print("💡 Убедитесь что номер правильный и в международном формате")
                await client.disconnect()
                return 1
            except Exception as e:
                print(f"❌ Ошибка отправки кода: {e}")
                print("\n💡 Возможные причины:")
                print("   - Слишком частые запросы кода (подождите 5-10 минут)")
                print("   - Проблемы с сетью")
                print("   - Telegram заблокирован в вашем регионе")
                await client.disconnect()
                return 1

            # Ввод кода
            print("\n" + "-" * 60)
            code = input("Введите код из Telegram: ").strip()

            if not code:
                print("❌ Код не введен")
                await client.disconnect()
                return 1

            # Авторизация
            try:
                await client.sign_in(phone, code)
            except SessionPasswordNeededError:
                print("\n🔐 Требуется пароль 2FA (облачный пароль)")
                password = input("Введите ваш облачный пароль: ")
                try:
                    await client.sign_in(password=password)
                except Exception as e:
                    print(f"❌ Ошибка входа с паролем: {e}")
                    await client.disconnect()
                    return 1
            except Exception as e:
                print(f"❌ Ошибка входа: {e}")
                print("\n💡 Возможные причины:")
                print("   - Неверный код (проверьте код еще раз)")
                print("   - Код устарел (код действителен несколько минут)")
                print("   - Слишком много неудачных попыток")
                await client.disconnect()
                return 1

        # Получение информации о пользователе
        me = await client.get_me()
        print("\n" + "=" * 60)
        print("✅ АВТОРИЗАЦИЯ УСПЕШНА!")
        print("=" * 60)
        print(f"👤 Пользователь: {me.first_name} {me.last_name or ''}")
        print(f"📱 Username: @{me.username}" if me.username else "📱 Username: (не установлен)")
        print(f"🆔 ID: {me.id}")

        # Получение StringSession
        session_string = client.session.save()
        if not session_string or session_string == "None":
            print("\n❌ Ошибка: Не удалось получить строку сессии")
            await client.disconnect()
            return 1

        # Вывод инструкций
        print("\n" + "=" * 60)
        print("📋 ДОБАВЬТЕ ЭТУ СТРОКУ В .env ФАЙЛ:")
        print("=" * 60)
        print(f"TG_SESSION_STRING={session_string}")
        print("=" * 60)
        print("\n💡 ИНСТРУКЦИИ:")
        print("1. Откройте файл .env")
        print("2. Найдите строку TG_SESSION_STRING (или добавьте новую)")
        print("3. Замените/добавьте значение на строку выше")
        print("4. Сохраните файл")
        print("5. Перезапустите бота: python main.py")
        print("\n⚠️ ВАЖНО: Храните TG_SESSION_STRING в безопасности!")
        print("   Это как пароль от вашего Telegram аккаунта")
        print("=" * 60)

        await client.disconnect()
        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
        await client.disconnect()
        return 1
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        await client.disconnect()
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
import asyncio
import os
import sys

# Добавляем корневую директорию в путь импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot
from aiogram.types import FSInputFile
from config import config
from gtts import gTTS

async def main():
    print("🎤 Запуск теста аудио-генерации (gTTS)...")
    
    try:
        text = (
            "Привет! Это тестовая аудио-сводка для вашего крипто-бота. "
            "Мы проверяем новую функцию: озвучивание ключевых новостей. "
            "Биткоин сегодня торгуется выше 98 тысяч долларов. Настроение рынка — умеренная жадность."
        )
        
        print(f"📝 Текст: {text}")
        print("🔊 Генерация аудио (Google TTS)...")
        
        # gTTS генерация
        tts = gTTS(text=text, lang='ru')
        file_path = "test_digest_audio.mp3"
        tts.save(file_path)
        
        print(f"✅ Аудио сохранено: {file_path}")
        
        # Отправка
        if config.admin_id:
            print(f"📤 Отправка админу ({config.admin_id})...")
            bot_instance = Bot(token=config.telegram_bot_token)
            try:
                audio_file = FSInputFile(file_path)
                await bot_instance.send_voice(
                    chat_id=config.admin_id, 
                    voice=audio_file, 
                    caption="🎙 <b>Тест аудио-сводки</b> (Google TTS)",
                    parse_mode="HTML"
                )
                print("✅ Успешно отправлено!")
            except Exception as e:
                print(f"❌ Ошибка отправки: {e}")
            finally:
                await bot_instance.session.close()
        else:
            print("⚠️ Admin ID не установлен, пропуск отправки.")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())

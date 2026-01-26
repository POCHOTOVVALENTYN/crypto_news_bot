import asyncio
import os
import aiosqlite
from config import (
    GROQ_API_KEY, TOGETHER_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, COHERE_API_KEY,
    GEMINI_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
)
from database import DB_PATH
from services.ai.manager import AIProviderManager

async def check_db():
    print(f"📦 Проверка Базы Данных ({DB_PATH})...", end=" ")
    try:
        if not os.path.exists(DB_PATH):
            print("❌ Файл не найден!")
            return False
            
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("SELECT 1")
            print("✅ OK")
            return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

async def check_ai_providers():
    print("\n🤖 Проверка AI Провайдеров:")
    
    # 1. Groq
    print(f"   - Groq API Key: {'✅ Установлен' if GROQ_API_KEY else '❌ Отсутствует'}")
    
    # 2. Together
    print(f"   - Together API Key: {'✅ Установлен' if TOGETHER_API_KEY else '❌ Отсутствует'}")
    
    # 3. Cloudflare
    cf_ok = CF_ACCOUNT_ID and CF_API_TOKEN
    print(f"   - Cloudflare Credentials: {'✅ Установлены' if cf_ok else '❌ Отсутствуют'}")
    
    # 4. Old providers
    print(f"   - Gemini API Key: {'✅ Установлен' if GEMINI_API_KEY else '❌ Отсутствует'}")
    print(f"   - OpenAI API Key: {'✅ Установлен' if OPENAI_API_KEY else '❌ Отсутствует'}")
    # 4. Cohere
    print(f"   - Cohere API Key: {'✅ Установлен' if COHERE_API_KEY else '❌ Отсутствует'}")
    print(f"   - DeepSeek API Key: {'✅ Установлен' if DEEPSEEK_API_KEY else '❌ Отсутствует'}")

    # Manager instantiation
    try:
        ai_manager = AIProviderManager()
        active = ai_manager.get_active_provider_names()
        print(f"\n   ✅ Активные провайдеры (приоритет): {active}")
        if not active:
            print("   ⚠️ ВНИМАНИЕ: Нет активных AI провайдеров!")
        else:
            if 'Groq' in active or 'TogetherAI' in active:
                print("   🚀 Отлично! Используются быстрые бесплатные провайдеры.")
            else:
                print("   ⚠️ Рекомендуется добавить Groq/Together для экономии.")
    except Exception as e:
        print(f"   ❌ Ошибка инициализации AI Manager: {e}")

async def check_telegram():
    print("\n📱 Проверка Telegram Config:", end=" ")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID:
        print("✅ Токен и ID канала есть")
    else:
        print("❌ Неверная конфигурация Telegram")

async def main():
    print("=== 🏥 CRYPTO BOT HEALTH CHECK 🏥 ===\n")
    
    await check_db()
    await check_ai_providers()
    await check_telegram()
    
    print("\n=== ✨ Проверка завершена ===")
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

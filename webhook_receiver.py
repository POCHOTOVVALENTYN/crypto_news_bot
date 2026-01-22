"""
Instagram Webhook Receiver
Принимает данные от Instagram через Albato/Make
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

from database import db
from loader import bot
from config import config

logger = logging.getLogger(__name__)

app = FastAPI(title="Instagram Webhook Receiver")


@app.post("/webhook/instagram")
async def instagram_webhook(request: Request):
    """Обработка incoming данных от Instagram"""
    
    try:
        data = await request.json()
        logger.info(f"📸 Instagram webhook: {data}")
        
        # Парсим данные
        username = data.get('username')
        source = data.get('source')  # 'direct' | 'comment' | 'story_mention'
        message = data.get('message', '')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        if not username:
            raise HTTPException(400, "Username required")
        
        # Сохраняем лид
        await _save_instagram_lead(username, source, message, timestamp)
        
        # Уведомляем админа
        await _notify_admin(username, source, message)
        
        return JSONResponse({
            "status": "success",
            "message": "Lead saved"
        })
        
    except Exception as e:
        logger.error(f"Ошибка Instagram webhook: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.get("/health")
async def health_check():
    """Health check эндпоинт"""
    return {"status": "ok", "service": "instagram_webhook"}


async def _save_instagram_lead(username: str, source: str, message: str, timestamp: str):
    """Сохранить лид в БД"""
    # TODO: Создать таблицу instagram_leads если нужна аналитика
    # Пока просто логируем
    logger.info(f"💾 Instagram Lead: @{username} ({source})")


async def _notify_admin(username: str, source: str, message: str):
    """Уведомить админа о новом лиде"""
    try:
        source_emoji = {
            'direct': '💬',
            'comment': '💭', 
            'story_mention': '📸'
        }.get(source, '📱')
        
        notification = (
            f"{source_emoji} <b>Новый лид из Instagram!</b>\n\n"
            f"Username: @{username}\n"
            f"Источник: {source}\n"
        )
        
        if message:
            notification += f"\nСообщение:\n{message[:200]}"
        
        await bot.send_message(
            config.admin_id,
            notification,
            parse_mode="HTML"
        )
        
        logger.info(f"✅ Админ уведомлён о лиде @{username}")
        
    except Exception as e:
        logger.error(f"Ошибка уведомления админа: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

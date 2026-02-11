"""
Сервис для локального хранения изображений Stories
"""
import os
import hashlib
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

STORAGE_DIR = Path("storage/stories")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

class ImageStorage:
    """Управление локальным хранилищем изображений"""
    
    @staticmethod
    async def save_image(user_id: int, image_bytes: bytes, timestamp: str) -> Tuple[str, str]:
        """
        Сохранить изображение локально
        
        Returns:
            (file_path, image_hash)
        """
        # Вычисляем хеш для детекции дубликатов
        image_hash = hashlib.md5(image_bytes).hexdigest()
        
        # Формируем путь
        filename = f"{user_id}_{timestamp}_{image_hash[:8]}.jpg"
        file_path = STORAGE_DIR / filename
        
        # Сохраняем
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        
        logger.info(f"💾 Saved story image: {file_path}")
        return str(file_path), image_hash
    
    @staticmethod
    def get_image_path(filename: str) -> Optional[Path]:
        """Получить полный путь к изображению"""
        path = STORAGE_DIR / filename
        return path if path.exists() else None
    
    @staticmethod
    async def check_duplicate(image_hash: str, user_id: int) -> bool:
        """Проверить, не дубликат ли это изображение"""
        from database import db
        import aiosqlite
        
        try:
            async with aiosqlite.connect(db.db_path) as conn:
                async with conn.execute("""
                    SELECT COUNT(*) FROM user_activities
                    WHERE user_id = ? 
                    AND activity_type = 'story_check'
                    AND image_hash = ?
                    AND created_at > datetime('now', '-7 days')
                """, (user_id, image_hash)) as cursor:
                    count = (await cursor.fetchone())[0]
                    return count > 0
        except Exception as e:
            logger.error(f"Ошибка проверки дубликата: {e}")
            return False

image_storage = ImageStorage()

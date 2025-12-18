from typing import Optional, List
from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Валидированная конфигурация с использованием Pydantic.
    Все критические переменные обязательны, бот не запустится без них.
    """

    # === TELEGRAM BOT (Обязательные) ===
    telegram_bot_token: str = Field(..., description="Bot token from @BotFather")
    telegram_channel_id: int = Field(..., description="Channel ID (with minus)")

    # === ADMIN (Новое - для алертов) ===
    admin_id: Optional[int] = Field(None, description="Admin user ID for alerts")

    # === AI PROVIDERS (Хотя бы один обязателен) ===
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    gemini_api_key: Optional[str] = Field(None, description="Google Gemini API key")

    # === TELEGRAM USERBOT (Опциональные) ===
    tg_api_id: int = Field(0, description="Telegram API ID from my.telegram.org")
    tg_api_hash: Optional[str] = Field(None, description="Telegram API Hash")
    tg_session_string: Optional[str] = Field(None, description="Telethon StringSession (base64)")
    source_channels: List[str] = Field(default_factory=list, description="Telegram channels to monitor")

    # === PARSING SETTINGS ===
    parse_interval: int = Field(300, ge=60, le=3600, description="RSS parsing interval (seconds)")
    filter_enabled: bool = Field(True, description="Enable content filtering")

    # === LOGGING ===
    log_level: str = Field("INFO", description="Logging level")

    @field_validator("telegram_channel_id")
    @classmethod
    def validate_channel_id(cls, v: int) -> int:
        """Проверяет что ID канала отрицательный (supergroup/channel)"""
        if v >= 0:
            raise ValueError("TELEGRAM_CHANNEL_ID должен быть отрицательным (например, -1001234567890)")
        return v

    @field_validator("source_channels", mode="before")
    @classmethod
    def parse_source_channels(cls, v) -> List[str]:
        """Парсит SOURCE_CHANNELS из строки через запятую"""
        try:
            # Если пришел None, возвращаем пустой список
            if v is None:
                return []

            # Если это строка (самый частый случай из .env)
            if isinstance(v, str):
                # Удаляем скобки и кавычки, если пользователь случайно их добавил
                clean_v = v.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
                return [ch.strip() for ch in clean_v.split(",") if ch.strip()]

            # Если это уже список (редко, но возможно)
            elif isinstance(v, list):
                return [str(ch).strip() for ch in v if str(ch).strip()]

            # Если пришло что-то другое (число и т.д.)
            return [str(v)]

        except Exception as e:
            # Логируем ошибку, но не роняем приложение, возвращая пустой список
            logger.error(f"⚠️ Ошибка парсинга SOURCE_CHANNELS: {e}. Значение: {v}")
            return []

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Проверяет корректность уровня логирования"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL должен быть одним из: {valid_levels}")
        return v_upper

    def validate_ai_providers(self):
        """Проверяет что хотя бы один AI провайдер настроен"""
        if not self.openai_api_key and not self.gemini_api_key:
            raise ValueError(
                "❌ Необходим хотя бы один AI провайдер!\n"
                "Установите OPENAI_API_KEY или GEMINI_API_KEY в .env"
            )

    def validate_userbot_config(self) -> bool:
        """Проверяет конфигурацию Userbot (не критично, только предупреждение)"""
        if self.tg_api_id == 0 or not self.tg_api_hash:
            logger.warning("⚠️ Userbot не настроен (TG_API_ID/TG_API_HASH отсутствуют)")
            return False
        if not self.source_channels:
            logger.warning("⚠️ SOURCE_CHANNELS пуст, Userbot не будет слушать каналы")
            return False
        return True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # Поддержка и верхнего, и нижнего регистра


# === ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР ===
def load_settings() -> Settings:
    """
    Загружает и валидирует настройки.
    Если критические параметры отсутствуют - бот упадет здесь с понятной ошибкой.
    """
    logger = logging.getLogger(__name__)
    try:
        settings = Settings()

        # Валидация AI провайдеров
        settings.validate_ai_providers()

        # Валидация Userbot (некритично)
        settings.validate_userbot_config()

        logger.info("✅ Конфигурация загружена и валидирована")
        return settings

    except ValidationError as e:
        logger.error("❌ ОШИБКА КОНФИГУРАЦИИ:")
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            message = error["msg"]
            logger.error(f"  • {field}: {message}")

        logger.error("\n💡 Проверьте файл .env и убедитесь что все обязательные поля заполнены.")
        raise SystemExit(1)

    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при загрузке конфигурации: {e}")
        raise SystemExit(1)


# Загружаем настройки при импорте
config = load_settings()

# === ЭКСПОРТ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ===
TELEGRAM_BOT_TOKEN = config.telegram_bot_token
TELEGRAM_CHANNEL_ID = config.telegram_channel_id
ADMIN_ID = config.admin_id
OPENAI_API_KEY = config.openai_api_key
GEMINI_API_KEY = config.gemini_api_key
TG_API_ID = config.tg_api_id
TG_API_HASH = config.tg_api_hash
TG_SESSION_STRING = config.tg_session_string
SOURCE_CHANNELS = config.source_channels
PARSE_INTERVAL = config.parse_interval
FILTER_ENABLED = config.filter_enabled
LOG_LEVEL = config.log_level
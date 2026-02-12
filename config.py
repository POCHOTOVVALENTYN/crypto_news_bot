# config.py
import os
from typing import Optional, List, Union
from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings
import logging

# === АДМИНИСТРАТОРЫ ===
ADMIN_IDS = [
    830196453,   # Валентин
    # 304050247,   # BLEXLER (Основатель) - REMOVED: chat not found
    1363924657   # Ярослав
]

ADMIN_NAMES = {
    830196453: "Валентин",
    # 304050247: "BLEXLER",  # REMOVED: chat not found
    1363924657: "Ярослав"
}

# Каскад поддержки (порядок эскалации)
SUPPORT_CASCADE = [
    # 304050247,   # 1. Основатель BLEXLER - REMOVED: chat not found
    830196453,   # 1. Валентин
    1363924657   # 2. Ярослав
]

def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS


# === ЦЕНЫ КОНСУЛЬТАЦИЙ ===
CONSULTATION_PRICES = {
    'wallet_review': {
        'name': '💰 Разбор Кошелька',
        'usd': 300,
        'stars': 20500  # ~300 / 0.0146
    },
    'vip_consultation': {
        'name': '💎 VIP-консультация',
        'usd': 350,
        'stars': 24000  # ~350 / 0.0146
    }
}

# === ЦЕНЫ PREMIUM (ЗА МЕСЯЦ) ===
PREMIUM_PRICES = {
    'base': {
        'usd': 800,
        'stars': 54800,
        'period_days': 30
    },
    'with_discount': {
        'usd': 700,
        'stars': 47900,
        'period_days': 30,
        'discount_amount': 100
    }
}

# === AI VISION SETTINGS ===
# Отключить OpenAI Vision fallback если нет квоты
OPENAI_VISION_ENABLED = False  # Set to True if you have OpenAI quota


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
    
    # === DISCUSSION GROUP (Предложка/Комментарии) ===
    discussion_group_id: int = Field(-1003810680361, description="ID группы для комментариев")
    disclaimer_url: Optional[str] = Field("https://telegra.ph/Disklejmer-kanala-BLEXLER--INVEST-02-11", description="Ссылка на Telegraph с дисклеймером")

    # === AI PROVIDERS (Хотя бы один обязателен) ===
    # Groq - новый провайдер с щедрым free tier (750k токенов/день)
    groq_api_key: Optional[str] = Field(None, description="Groq API key")
    groq_model: str = Field("llama-3.1-70b-versatile", description="Groq Model Name")
    # Together AI ($25 free credits)
    together_api_key: Optional[str] = Field(None, description="Together AI API key")
    together_model: str = Field("meta-llama/Llama-3-70b-chat-hf", description="Together AI Model")
    
    # Cloudflare Workers AI (Free forever)
    cf_account_id: Optional[str] = Field(None, description="Cloudflare Account ID")
    cf_api_token: Optional[str] = Field(None, description="Cloudflare API Token")
    cf_model: str = Field("@cf/meta/llama-3-8b-instruct", description="Cloudflare Model")
    # Cohere (1000 calls/month free)
    cohere_api_key: Optional[str] = Field(None, description="Cohere API Key")
    cohere_model: str = Field("command-r-plus", description="Cohere Model")
    
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    gemini_api_key: Optional[str] = Field(None, description="Google Gemini API key")
    mistral_api_key: Optional[str] = Field(None, description="Mistral AI API key")
    deepseek_api_key: Optional[str] = Field(None, description="DeepSeek API key")
    deepseek_base_url: str = Field("https://api.deepseek.com", description="DeepSeek API Base URL")
    huggingface_api_key: Optional[str] = Field(None, description="Hugging Face API Token")
    ollama_base_url: str = Field("http://localhost:11434", description="Ollama API Base URL")
    ollama_model: str = Field("llama3", description="Ollama Model Name")

    # === TELEGRAM USERBOT (Опциональные) ===
    tg_api_id: int = Field(0, description="Telegram API ID from my.telegram.org")
    tg_api_hash: Optional[str] = Field(None, description="Telegram API Hash")
    tg_session_string: Optional[str] = Field(None, description="Telethon StringSession (base64)")

    # ⚠️ ИСПРАВЛЕНО: str вместо List[str]
    source_channels: str = Field("", description="Telegram channels to monitor (comma-separated)")

    # === PARSING SETTINGS ===
    parse_interval: int = Field(300, ge=60, le=3600, description="RSS parsing interval (seconds)")
    filter_enabled: bool = Field(True, description="Enable content filtering")

    # === PREMIUM & PAYMENTS ===
    channel_premium_id: int = Field(-1001773544621, description="Premium channel ID")
    premium_price_full: int = Field(500, description="Полная цена Premium в звёздах")
    premium_price_discount: int = Field(400, description="Скидочная цена Premium в звёздах")
    premium_duration_days: int = Field(30, description="Длительность подписки в днях")

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
    def parse_source_channels(cls, v) -> str:
        """Оставляет source_channels как строку (парсинг будет позже)"""
        if v is None:
            return ""
        if isinstance(v, list):
            return ",".join(str(ch).strip() for ch in v if ch)
        return str(v).strip()

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
        if not any([self.openai_api_key, self.gemini_api_key, self.mistral_api_key, 
                   self.deepseek_api_key, self.huggingface_api_key, self.ollama_base_url]):
            raise ValueError(
                "❌ Необходим хотя бы один AI провайдер!\n"
                "Установите API ключи в .env"
            )

    def get_source_channels_list(self) -> List[str]:
        """Возвращает source_channels как список"""
        if not self.source_channels:
            return []
        return [ch.strip() for ch in self.source_channels.split(",") if ch.strip()]

    def validate_userbot_config(self) -> bool:
        """Проверяет конфигурацию Userbot (не критично, только предупреждение)"""
        logger = logging.getLogger(__name__)

        if self.tg_api_id == 0 or not self.tg_api_hash:
            logger.warning("⚠️ Userbot не настроен (TG_API_ID/TG_API_HASH отсутствуют)")
            return False

        channels_list = self.get_source_channels_list()
        if not channels_list:
            logger.warning("⚠️ SOURCE_CHANNELS пуст, Userbot не будет слушать каналы")
            return False

        return True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


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
GROQ_API_KEY = config.groq_api_key
TOGETHER_API_KEY = config.together_api_key
TOGETHER_MODEL = config.together_model
CF_ACCOUNT_ID = config.cf_account_id
CF_API_TOKEN = config.cf_api_token
COHERE_API_KEY = config.cohere_api_key
COHERE_MODEL = config.cohere_model
CF_MODEL = config.cf_model
GROQ_MODEL = config.groq_model
MISTRAL_API_KEY = config.mistral_api_key
DEEPSEEK_API_KEY = config.deepseek_api_key
DEEPSEEK_BASE_URL = config.deepseek_base_url
HUGGINGFACE_API_KEY = config.huggingface_api_key
OLLAMA_BASE_URL = config.ollama_base_url
OLLAMA_MODEL = config.ollama_model
TG_API_ID = config.tg_api_id
TG_API_HASH = config.tg_api_hash
TG_SESSION_STRING = config.tg_session_string
SOURCE_CHANNELS = config.get_source_channels_list()  # ⚠️ ИСПРАВЛЕНО
PARSE_INTERVAL = config.parse_interval
FILTER_ENABLED = config.filter_enabled
LOG_LEVEL = config.log_level

TG_PHONE_NUMBER = os.getenv("TG_PHONE_NUMBER")
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = int(os.getenv("TELEGRAM_CHANNEL_ID"))

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Настройки парсинга
PARSE_INTERVAL = int(os.getenv("PARSE_INTERVAL", 300))  # 5 минут по умолчанию
FILTER_ENABLED = os.getenv("FILTER_ENABLED", "true").lower() == "true"

# Логирование
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
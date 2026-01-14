from aiogram import Bot, Dispatcher
from config import config

# Инициализация бота и диспетчера
bot = Bot(token=config.telegram_bot_token)
dp = Dispatcher()

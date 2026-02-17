from aiogram.types import InlineKeyboardButton
from typing import Optional
import json

class ColoredButton(InlineKeyboardButton):
    style: Optional[str] = None

try:
    b = ColoredButton(text="Test", url="https://google.com", style="primary")
    # aiogram 3.x uses model_dump_json or json() depending on version
    # fallback to __dict__ if needed
    print(f"Serialized: {b.model_dump_json(exclude_none=True)}")
except Exception as e:
    print(f"Error: {e}")

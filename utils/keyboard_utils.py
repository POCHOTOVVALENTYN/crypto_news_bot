from aiogram.types import InlineKeyboardButton
from typing import Optional

class ColoredButton(InlineKeyboardButton):
    """
    Subclass of InlineKeyboardButton to support 'style' parameter 
    introduced in Telegram Bot API 9.4 (Feb 2026).
    
    Styles:
    - primary: Blue (Action)
    - success: Green (Confirmation)
    - danger: Red (Destructive)
    - None: Default (Gray)
    """
    style: Optional[str] = None

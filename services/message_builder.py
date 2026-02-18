"""
Построитель сообщений для Telegram
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime
import re

from loader import bot

logger = logging.getLogger(__name__)


class AdvancedMessageFormatter:
    """Усовершенствованный форматировщик сообщений"""
    
    def __init__(self):
        self.max_length = 4096
        
    async def format_news_message(self, news_item: Dict, is_digest: bool = False, locale: str = 'ru') -> str:
        """
        Форматирование одной новости для публикации
        
        Args:
            news_item: Словарь с данными новости
            is_digest: Это дайджест или отдельная новость?
            locale: Язык (пока только ru)
        """
        title = news_item.get('title', '')
        summary = news_item.get('summary', '')
        source = news_item.get('source', '')
        url = news_item.get('url', '')
        # metadata = news_item.get('metadata', {})
        
        # Очищаем заголовок
        title = self.clean_text(title)
        
        # Очищаем summary
        if summary:
            summary = self.clean_text(summary)
            # Дедупликация: если summary начинается с title (или очень похоже), убираем это
            # Нормализуем для сравнения
            clean_title = re.sub(r'[^\w\s]', '', title.lower())
            clean_summary = re.sub(r'[^\w\s]', '', summary.lower())
            
            if clean_summary.startswith(clean_title):
                # Убираем дубль заголовка из начала summary
                # Берем длину заголовка + небольшой запас на символы
                summary = summary[len(title):].strip()
                # Удаляем возможные оставшиеся знаки препинания в начале
                summary = re.sub(r'^[\.\,\:\-\s]+', '', summary)

        # Формируем тело сообщения
        message_parts = []
        
        if is_digest:
            # Для дайджеста формат: 🔹 <Заголовок>
            # <Текст>
            message_parts.append(f"🔹 <b>{title}</b>\n")
            if summary:
                message_parts.append(f"{summary}\n")
        else:
            # Для отдельного поста:
            # 🔥 <ЗАГОЛОВОК>
            # <Текст>
            # ...
            
            # Эмодзи в зависимости от важности (если есть)
            emoji = "⚡️"
            if news_item.get('priority', 0) >= 8:
                emoji = "🔥"
            
            message_parts.append(f"{emoji} <b>{title.upper()}</b>\n")
            
            if summary:
                message_parts.append(f"{summary}\n")
            
            # Добавляем рыночные данные если есть (mockup)
            # message_parts.append("\n📈 BTC: $65,120 | ETH: $3,450")
            
        # Ссылка на источник (если нужно)
        # if source:
        #    message_parts.append(f"\nИсточник: {source}")
            
        final_text = "\n".join(message_parts)
        
        # Обрезаем если слишком длинно
        if len(final_text) > self.max_length:
            final_text = final_text[:self.max_length-100] + "..."
            
        return final_text

    async def format_professional_news(self, title: str, summary: str, source: str, source_url: str,
                                     prices: Optional[dict] = None, fear_greed: Optional[dict] = None,
                                     image_url: Optional[str] = None, ai_data: Optional[dict] = None,
                                     technical_analysis: Optional[str] = None, key_points: Optional[List[str]] = None,
                                     full_content: Optional[str] = None, footer_template: str = None,
                                     is_breaking: bool = False) -> Dict:
        """
        Форматирует новость в профессиональном стиле (для publish_helper)
        
        Returns:
            Dict: {'text': html_text, 'image_url': image_url}
        """
        # 1. Заголовок
        emoji = "🔥" if is_breaking else "⚡️"
        header = f"{emoji} <b>{title.upper()}</b>"
        
        # 2. Тело новости (summary или full_content если есть и не очень длинный)
        content_text = summary
        if full_content and len(full_content) < 1000:
             content_text = full_content
             
        # Очистка
        content_text = self.clean_text(content_text)
        
        # 3. Ключевые моменты (если есть)
        points_text = ""
        if key_points:
            points_text = "\n\n<b>Ключевые моменты:</b>\n" + "\n".join([f"• {p}" for p in key_points])

        # 4. Рыночные данные
        market_info = ""
        if prices or fear_greed:
            market_parts = []
            if prices:
                btc = prices.get('bitcoin', {})
                eth = prices.get('ethereum', {})
                market_parts.append(f"BTC: ${btc.get('price', 'N/A'):,}")
                market_parts.append(f"ETH: ${eth.get('price', 'N/A'):,}")
            
            if fear_greed:
                 market_parts.append(f"F&G: {fear_greed.get('value')} ({fear_greed.get('classification')})")
            
            if market_parts:
                market_info = "\n\n📈 " + " | ".join(market_parts)

        # 5. Футер
        if not footer_template or footer_template == "По умолчанию":
            footer = self.create_digest_footer()
        else:
            footer = "\n" + footer_template

        # Сборка
        full_text = f"{header}\n\n{content_text}{points_text}{market_info}{footer}"
        
        # Обрезаем
        if len(full_text) > 4096:
             full_text = full_text[:4000] + "...\n(Читать далее в источнике)"

        return {
            'text': full_text,
            'image_url': image_url
        }

    def create_digest_header(self, digest_type: str = "daily") -> str:
        """Заголовок дайджеста"""
        date_str = datetime.now().strftime("%d.%m.%Y")
        
        if digest_type == "daily":
            return (
                f"📰 <b>CRYPTO DAILY • {date_str}</b>\n"
                f"Главные новости за последние 24 часа\n"
                f"➖➖➖➖➖➖➖➖➖➖\n"
            )
        elif digest_type == "weekly":
            return (
                f"🗞 <b>CRYPTO WEEKLY • {date_str}</b>\n"
                f"Главные события недели\n"
                f"➖➖➖➖➖➖➖➖➖➖\n"
            )
        return ""

    def create_digest_footer(self) -> str:
        """Подвал дайджеста"""
        return (
            f"\n➖➖➖➖➖➖➖➖➖➖\n"
            f"🔸 <a href='https://t.me/blexler_support_bot'>BLEXLER SUPPORT</a>\n"
            f"🔸 <a href='https://t.me/blexler_news'>BLEXLER NEWS</a>"
        )
        
    def clean_text(self, text: str) -> str:
        """Очистка текста от мусора, ссылок и лишних символов"""
        if not text:
            return ""

        # 1. Удаляем Markdown ссылки [Text](URL) -> Text
        # Сначала пробуем сохранить текст ссылки
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # 2. Удаляем неудаленные скобки и ссылки
        text = re.sub(r'\[.*?\]', '', text) # [text]
        text = re.sub(r'\(http.*?\)', '', text) # (url)

        # 3. Удаляем прямые ссылки (если они не часть текста)
        # Regex для URL
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        text = re.sub(url_pattern, '', text)

        # 4. Удаляем спецсимволы в начале/конце строк
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            # Удаляем повторяющиеся спецсимволы
            line = re.sub(r'^[\*\_\-\=\#\s]+', '', line) # В начале строки
            line = re.sub(r'[\*\_\-\=\#\s]+$', '', line) # В конце строки
            if line:
                lines.append(line)
        
        text = '\n'.join(lines)

        # 5. Убираем двойные пробелы и множественные переносы
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()


# Глобальный экземпляр
message_formatter = AdvancedMessageFormatter()


# === MISSING COMPONENTS RESTORATION ===

class RichMediaMessage:
    """Class for sending messages with optional images"""
    def __init__(self, text: str, image_url: Optional[str] = None, reply_markup=None):
        self.text = text
        self.image_url = image_url
        self.reply_markup = reply_markup

    async def send(self, bot, chat_id: int):
        try:
            if self.image_url:
                try:
                    return await bot.send_photo(
                        chat_id=chat_id,
                        photo=self.image_url,
                        caption=self.text,
                        parse_mode="HTML",
                        reply_markup=self.reply_markup
                    )
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Failed to send photo, sending text only: {e}")
            
            # Fallback to text
            return await bot.send_message(
                chat_id=chat_id,
                text=self.text,
                parse_mode="HTML",
                reply_markup=self.reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to send message: {e}")
            return None

class FearGreedIndexTracker:
    """Tracker for Fear & Greed Index"""
    @staticmethod
    async def get_fear_greed_index() -> Optional[Dict]:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.alternative.me/fng/", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Returns {"name": "Fear & Greed Index", "data": [{"value": "55", "value_classification": "Greed", ...}]}
                        if data and 'data' in data and len(data['data']) > 0:
                            item = data['data'][0]
                            return {
                                "value": int(item['value']),
                                "classification": item['value_classification']
                            }
            return None
        except Exception as e:
            logger.error(f"Error fetching F&G Index: {e}")
            return None

async def get_multiple_crypto_prices() -> Optional[Dict]:
    """Get crypto prices (BTC, ETH, SOL)"""
    try:
        import aiohttp
        # IDs: bitcoin, ethereum, solana
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Returns {'bitcoin': {'usd': 68000, 'usd_24h_change': -0.2}, ...}
                    result = {}
                    mapping = {
                        'bitcoin': 'BTC',
                        'ethereum': 'ETH',
                        'solana': 'SOL'
                    }
                    
                    for coin_id, symbol in mapping.items():
                        if coin_id in data:
                            c = data[coin_id]
                            result[coin_id] = {
                                'price': c['usd'],
                                'change': c['usd_24h_change'],
                                'symbol': symbol
                            }
                    return result
            # Если 429 или ошибка, пробуем другой источник (резерв)
            # Пока просто возвращаем None или Mock
            return None
            
    except Exception as e:
        logger.error(f"Error fetching crypto prices: {e}")
        return None



class ImageExtractor:
    """Helper for extracting images"""
    pass
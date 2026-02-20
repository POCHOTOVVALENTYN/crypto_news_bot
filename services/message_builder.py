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
        # Исправление 1: берём только ПЕРВУЮ строку title (источник может давать многострочный title)
        title_first_line = title.split('\n')[0].strip()
        # Исправление 1б: сначала удаляем URL целиком (http[s]://...), потом артефакты
        title_no_url = re.sub(r'https?://\S+', '', title_first_line).strip()
        clean_title_header = re.sub(r'[^\w\s\.,!\?\-]', '', title_no_url).strip()
        # Если после очистки заголовок пустой — запасной вариант
        if not clean_title_header:
            clean_title_header = re.sub(r'[^\w\s]', '', title_no_url).strip() or "Breaking News"
        emoji = "🔥" if is_breaking else "⚡️"
        header = f"{emoji} <b>{clean_title_header.upper()}</b>"
        
        # 2. Тело новости (summary или full_content если есть и не очень длинный)
        content_text = summary
        
        # Если есть картинка, ограничиваем текст 900 символами (лимит caption 1024)
        max_caption_len = 900 if image_url else 3800
        
        if full_content and len(full_content) < max_caption_len:
             content_text = full_content
        
        # Обрезаем если слишком длинно
        if len(content_text) > max_caption_len:
            content_text = content_text[:max_caption_len] + "..."
             
        # Очистка текста
        content_text = self.clean_text(content_text)

        # Исправление 3: улучшенная дедупликация по проценту совпадения слов
        # Убираем строки, где >60% слов совпадают с заголовком
        norm_title_words = set(re.sub(r'[^\w]', ' ', title_first_line.lower()).split())
        if norm_title_words:
            filtered_lines = []
            for line in content_text.split('\n'):
                norm_line_words = set(re.sub(r'[^\w]', ' ', line.lower()).split())
                if norm_line_words:
                    overlap = len(norm_title_words & norm_line_words) / len(norm_title_words)
                    if overlap > 0.6:  # Строка — это дубль заголовка
                        continue
                filtered_lines.append(line)
            content_text = '\n'.join(filtered_lines).strip()
        
        # Убираем источник из текста, если он там есть
        if source:
            content_text = content_text.replace(f"Источник: {source}", "").strip()
        
        # 3. Ключевые моменты (если есть)
        points_text = ""
        if key_points:
            points_text = "\n\n<b>Ключевые моменты:</b>\n" + "\n".join([f"• {p}" for p in key_points])

        # 4. Рыночные данные (стиль V3.0 как в дайджесте)
        market_info = ""
        if prices or fear_greed:
             market_parts = []
             
             # Цены
             if prices:
                for coin in ['bitcoin', 'ethereum', 'solana']:
                    if coin in prices:
                        p = prices[coin]
                        symbol = p['symbol']
                        price = p['price']
                        change = p['change']
                        emoji_trend = "🚀" if change >= 0 else "🩸"
                        sign = "+" if change >= 0 else ""
                        market_parts.append(f"{emoji_trend} <b>{symbol}:</b> ${price:,.0f} ({sign}{change:.1f}%)")
             
             # Индекс страха
             if fear_greed:
                 val = fear_greed.get('value', 50)
                 if val >= 75: face = "🤑" # Extreme Greed
                 elif val >= 55: face = "😊" # Greed
                 elif val >= 45: face = "😐" # Neutral
                 elif val >= 25: face = "😰" # Fear
                 else: face = "😱" # Extreme Fear
                 market_parts.append(f"{face} <b>F&G:</b> {val}/100")
             
             if market_parts:
                 market_info = "\n\n" + "\n".join(market_parts)

        # Исправление 7: стандартизированная сборка — единый \n\n между блоками
        # Исправление 6: игнорируем footer_template из БД (старый шаблон), всегда используем create_digest_footer
        footer = self.create_digest_footer()
        
        full_text = header
        if content_text:
            full_text += f"\n\n{content_text.strip()}"
        if points_text:
            full_text += f"\n\n{points_text.strip()}"
        if market_info:
            full_text += f"\n\n{market_info.strip()}"
        full_text += footer
        
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
            f"\n\n🔸 <a href='https://t.me/blexler_support_bot'>BLEXLER SUPPORT</a>\n"
            f"🔸 <a href='https://t.me/blexler_news'>BLEXLER NEWS</a>"
        )


    def clean_text(self, text: str) -> str:
        """Очистка текста от мусора, меншнов, ссылок и лишних символов"""
        if not text:
            return ""

        # 0. Удаляем @mentions (имена каналов)
        text = re.sub(r'@[\w_]+', '', text)
        
        # 0.1 Удаляем t.me ссылки из текста
        text = re.sub(r't\.me/[\w_/]+', '', text)

        # 0.2 Исправление 2: удаляем Telegram-форматирование **жирный**, __курсив__ внутри строк
        # Это оставляет **** от эмодзи и других артефактов телеграм-парсера
        text = re.sub(r'\*{2,}', '', text)   # убираем ** **** ***** и подобное
        text = re.sub(r'_{2,}', '', text)    # убираем __ (цвет курсива в Telegram)

        # 1. Удаляем Markdown ссылки [Text](URL) -> Text
        # Улучшенный regex: захватываем текст в [], игнорируем URL в ()
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # 2. Удаляем неудаленные скобки и ссылки
        text = re.sub(r'\[.*?\]', '', text) # [text]
        text = re.sub(r'\(http.*?\)', '', text) # (url)

        # 3. Удаляем прямые ссылки (если они не часть текста)
        # Regex для URL (улучшенный)
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        text = re.sub(url_pattern, '', text)

        # 4. Удаляем спецсимволы в начале/конце строк
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            # Удаляем повторяющиеся спецсимволы и разделители
            line = re.sub(r'^[\*\_\-\=\#\s]+', '', line) # В начале строки
            line = re.sub(r'[\*\_\-\=\#\s]+$', '', line) # В конце строки
            
            # Удаляем разделители типа ➖➖➖
            if re.match(r'^[➖\-_=]{3,}$', line):
                continue

            # Исправление 4: удаляем артефакты пересылки твита из Telegram
            # "Твит https://... от 08.01.2020:" -> после очистки URL остаётся "Твит от DATE:"
            if re.match(r'^(\u0422вит|tweet)(\s+от|\s+from)?\s*[\d\.\/\-]+', line, re.IGNORECASE):
                continue
            # Удаляем строки вида "httpsx.com..." (артефакт после убрания ://)
            if re.match(r'^https?[a-zA-Z0-9\.\-/_\?=&]+$', line, re.IGNORECASE):
                continue
                
            # Удаляем строки типа "source: ..." или "via ..."
            if re.match(r'^(source|via|credit|photo|image):', line, re.IGNORECASE):
                continue
                
            if line:
                lines.append(line)
        
        text = '\n'.join(lines)

        # 5. Убираем двойные пробелы и множественные переносы
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 6. Финальная зачистка
        text = text.replace('  ', ' ').strip()

        return text


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
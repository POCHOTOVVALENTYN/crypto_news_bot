"""
Построитель сообщений для Telegram
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime
import re

from loader import bot

logger = logging.getLogger(__name__)

# Маркер для надёжного поиска начала footer при smart_truncate (БАГ 1 ИСПРАВЛЕН)
_FOOTER_MARKER = "\n\n\u200b_FOOTER_"  # невидимый символ + метка


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
        # Удаляем URL целиком (http[s]://...), потом артефакты
        title_no_url = re.sub(r'https?://\S+', '', title_first_line).strip()
        # БАГ 7 ИСПРАВЛЕН: добавлены $%/# (важны для крипто-текста: BTC/%)
        clean_title_header = re.sub(r'[^\w\s\.,!\?\-\$\%\/\#\@]', '', title_no_url).strip()
        if not clean_title_header:
            clean_title_header = re.sub(r'[^\w\s]', '', title_no_url).strip() or "Breaking News"
        emoji = "🔥" if is_breaking else "⚡️"
        header = f"{emoji} <b>{clean_title_header.upper()}</b>"
        
        # 2. Тело новости
        # БАГ 5 ИСПРАВЛЕН: не перезаписываем summary полным full_content.
        # summary уже прошёл через AI-рерайт, дедупликацию и перевод — он уже готов.
        content_text = summary
        
        # БАГ 4 ИСПРАВЛЕН: убрали первый smart_truncate (двойная обрезка).
        # Финальный smart_truncate ниже (telegram_limit) — единственный и правильный.
        # Размер тела контролируется в publish_helper через BODY_LIMIT_CAPTION.
        
        # Очистка текста
        content_text = self.clean_text(content_text)

        # БАГ 3+4 ИСПРАВЛЕН: дедупликация в format_professional_news отключена для breaking news.
        # ContentDeduplicator уже сделал её в publish_helper с порогом 0.85.
        # Двойная дедупликация удаляла важные факты.
        # Для обычных новостей дедупликацию по заголовку оставляем.
        if not is_breaking:
            norm_title_words = set(re.sub(r'[^\w]', ' ', title_first_line.lower()).split())
            if norm_title_words:
                filtered_lines = []
                for line in content_text.split('\n'):
                    norm_line_words = set(re.sub(r'[^\w]', ' ', line.lower()).split())
                    if norm_line_words:
                        overlap = len(norm_title_words & norm_line_words) / len(norm_title_words)
                        if overlap > 0.6:
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

        # Исправление 7 + БАГ 4: стандартизированная сборка.
        # Для публичных публикаций — channel_footer (Instagram + Telegram)
        footer = self.create_channel_footer()
        
        full_text = header
        if content_text:
            full_text += f"\n\n{content_text.strip()}"
        if points_text:
            full_text += f"\n\n{points_text.strip()}"
        if market_info:
            full_text += f"\n\n{market_info.strip()}"
        full_text += footer
        
        # Финальный smart_truncate — гарантируем лимиты Telegram
        # caption (с фото): 1024 симв, message (без фото): 4096 симв
        # Используем чуть меньший лимит как страховой запас на HTML-теги
        telegram_limit = 1000 if image_url else 4000
        if len(full_text) > telegram_limit:
            # Обрезаем по предложению: сначала пытаемся вырезать тело,
            # оставляя заголовок и футер нетронутыми
            body_start = len(header) + 2  # +2 за \n\n
            body_end = full_text.rfind(_FOOTER_MARKER)  # БАГ 1 ИСПРАВЛЕН: надёжный маркер footer
            if body_end > body_start:
                # Есть выделенный блок тела — обрезаем только его
                available_for_body = telegram_limit - (len(full_text) - body_end)
                if available_for_body > 100:
                    body_part = self._smart_truncate(
                        full_text[body_start:body_end], available_for_body
                    )
                    full_text = header + '\n\n' + body_part + full_text[body_end:]
                else:
                    # Совсем мало места — просто smart_truncate всего
                    full_text = self._smart_truncate(full_text, telegram_limit)
            else:
                full_text = self._smart_truncate(full_text, telegram_limit)

        return {
            'text': full_text,
            'image_url': image_url
        }

    @staticmethod
    def _smart_truncate(text: str, max_len: int, marker: str = " ...") -> str:
        """Умный обрез — по последнему полному предложению или строке. Никогда не рвёт на полуслове."""
        if len(text) <= max_len:
            return text
        # Ищем последний хороший разрыв внутри первых max_len символов
        truncated = text[:max_len]
        for sep in ('\n', '. ', '! ', '? ', ': ', ', '):
            last_pos = truncated.rfind(sep)
            if last_pos > max_len * 0.55:  # нашли разумный разрыв
                return truncated[:last_pos + 1].strip() + marker
        # Fallback: обрываем по последнему пробелу (хотя бы не на полуслове)
        last_space = truncated.rfind(' ')
        if last_space > max_len * 0.5:
            return truncated[:last_space].strip() + marker
        return truncated.strip() + marker

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
        """Подвал для рассылок в боте (поддержка)"""
        return (
            f"\n\n🔸 <a href='https://t.me/blexler_support_bot'>BLEXLER SUPPORT</a>\n"
            f"🔸 <a href='https://t.me/blexler_news'>BLEXLER NEWS</a>"
        )

    def create_channel_footer(self) -> str:
        """Футер для публикаций в канале. Содержит _FOOTER_MARKER для надёжного rfind при truncate."""
        # БАГ 1 ИСПРАВЛЕН: маркер позволяет точно найти начало footer для smart_truncate
        return (
            _FOOTER_MARKER +
            "\n🔸<a href='https://www.instagram.com/zhenya_eduardovich.2?igsh=M2lwN2p2enhuN3Nl'>BLEXLER INSTAGRAM</a>🔸\n"
            "��<a href='https://t.me/blexler_invest'>BLEXLER TELEGRAM</a>🔸"
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
            # БАГ 4 ИСПРАВЛЕН: удаляем спецсимволы в начале/конце строки,
            # но не если после '-' сразу идёт буква (это AI bullet-point)
            line = re.sub(r'^[\*\_\=\#\s]+', '', line)  # не удаляем '-' и '—' из начала
            # БАГ 5 ИСПРАВЛЕН: защищаем и ASCII дефис '-' и EM dash '—' (U+2014)
            # '— Факт: ...' — это AI bullet-point, не удаляем
            line = re.sub(r'^\-(?!\s*\w)', '', line)    # ASCII дефис только если не за буквой
            line = re.sub(r'^\u2014(?!\s*\w)', '', line) # EM dash только если не за буквой
            line = re.sub(r'[\*\_\=\#\s]+$', '', line)  # конец строки
            
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
                if not isinstance(self.image_url, str) or not self.image_url.startswith('http'):
                    logging.getLogger(__name__).warning(
                        f"⚠️ Невалидный image_url: {repr(self.image_url)[:80]}"
                    )
                else:
                    # БАГ 3 ИСПРАВЛЕН: image proxy — скачиваем и отправляем как FSInputFile
                    # Это обходит 403 Forbidden от CDN при hotlinking
                    sent = await self._try_send_photo(bot, chat_id)
                    if sent:
                        return sent
            
            # Fallback к текстовому сообщению (без фото)
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

    async def _try_send_photo(self, bot, chat_id: int):
        """Попытка отправить фото: сначала прямой URL, потом через скачивание."""
        import aiohttp, os, tempfile
        _log = logging.getLogger(__name__)
        
        # Попытка 1: прямой URL
        try:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=self.image_url,
                caption=self.text,
                parse_mode="HTML",
                reply_markup=self.reply_markup
            )
        except Exception as e1:
            _log.warning(f"⚠️ Прямой URL отклонён ({type(e1).__name__}), пробую скачать: {self.image_url[:80]}")
        
        # Попытка 2: скачать → FSInputFile
        try:
            from aiogram.types import FSInputFile
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; TelegramBot/1.0)',
                'Accept': 'image/webp,image/png,image/jpeg,*/*'
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(self.image_url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get('Content-Type', 'image/jpeg')
                        ext = '.jpg' if 'jpeg' in content_type else '.png' if 'png' in content_type else '.webp'
                        data = await resp.read()
                        if len(data) < 512:  # слишком мал — точно не изображение
                            raise ValueError(f"Слишком маленький файл ({len(data)} bytes)")
                        
                        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                            tmp.write(data)
                            tmp_path = tmp.name
                        
                        try:
                            result = await bot.send_photo(
                                chat_id=chat_id,
                                photo=FSInputFile(tmp_path),
                                caption=self.text,
                                parse_mode="HTML",
                                reply_markup=self.reply_markup
                            )
                            _log.info(f"✅ Фото отправлено через скачивание ({len(data)} байт)")
                            return result
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                    else:
                        _log.warning(f"⚠️ HTTP {resp.status} при скачивании фото")
        except Exception as e2:
            _log.error(f"❌ Не удалось отправить фото через скачивание: {e2} | URL: {self.image_url[:80]}")
        
        return None  # Оба способа не сработали → fallback к тексту


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
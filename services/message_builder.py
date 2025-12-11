# services/message_builder.py
import logging
import re
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class CryptoMultiPriceTracker:
    @staticmethod
    def format_multi_prices(prices: Dict[str, Dict]) -> str:
        if not prices: return ""
        lines = []
        if "bitcoin" in prices:
            lines.append(f"🪙 BTC: ${prices['bitcoin']['price']:,} ({prices['bitcoin']['change']:+.2f}%)")
        if "ethereum" in prices:
            lines.append(f"🔷 ETH: ${prices['ethereum']['price']:,} ({prices['ethereum']['change']:+.2f}%)")
        if "solana" in prices:
            lines.append(f"🟣 SOL: ${prices['solana']['price']:.2f} ({prices['solana']['change']:+.2f}%)")

        return "💰 <b>Цены (24h):</b>\n" + "\n".join(lines)


class FearGreedIndexTracker:
    # Оставляем логику как есть, она работает
    pass


class ImageExtractor:
    @staticmethod
    def is_valid_image_url(url: Optional[str]) -> bool:
        if not url: return False
        valid_ext = ('.jpg', '.jpeg', '.png', '.webp')
        return url.lower().endswith(valid_ext) or 'image' in url.lower()


class AdvancedMessageFormatter:
    COIN_IMAGES = {
        "BTC": "https://s3.coinmarketcap.com/static-gravity/image/5cc0b99a8095453bb209c2963feb7e82.png",
        "ETH": "https://s3.coinmarketcap.com/static-gravity/image/28c114dc354e4444983637402dc4db42.png",
        "SOL": "https://s3.coinmarketcap.com/static-gravity/image/358e2d45387c47d792b0024ba1622325.png",
        "General": "https://images.unsplash.com/photo-1621761191319-c6fb62004040?auto=format&fit=crop&w=1000&q=80"
    }

    @staticmethod
    def get_coin_image(coin: str) -> str:
        return AdvancedMessageFormatter.COIN_IMAGES.get(coin, AdvancedMessageFormatter.COIN_IMAGES["General"])

    @staticmethod
    def clean_text(text: str) -> str:
        # Убираем HTML
        text = re.sub(r'<[^>]+>', '', text)
        # Убираем [...] и читать далее
        text = text.replace('[…]', '').replace('...', '')
        text = re.sub(r'Читать далее.*', '', text, flags=re.IGNORECASE)
        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def smart_truncate(text: str, length: int = 900) -> str:
        if len(text) <= length: return text
        cut = text[:length]
        # Ищем конец предложения
        last_dot = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
        if last_dot > length // 2:
            return cut[:last_dot + 1]
        return cut + "..."

    @staticmethod
    def format_professional_news(
            title: str,
            summary: str,
            source: str,
            source_url: str,
            prices: Optional[Dict] = None,
            fear_greed: Optional[Dict] = None,
            image_url: Optional[str] = None,
            ai_data: Optional[Dict] = None
    ) -> Dict:

        # 1. Заголовок
        sentiment_emoji = "🔔"
        coin_tag = ""

        if ai_data:
            sent = ai_data.get("sentiment", "Neutral")
            if "Bullish" in sent:
                sentiment_emoji = "🟢"
            elif "Bearish" in sent:
                sentiment_emoji = "🔴"

            coin = ai_data.get("coin", "Market")
            if coin and coin != "Market":
                coin_tag = f"#{coin}"
                if not image_url: image_url = AdvancedMessageFormatter.get_coin_image(coin)

        if not image_url: image_url = AdvancedMessageFormatter.COIN_IMAGES["General"]

        header = f"{sentiment_emoji} <b>{title}</b> {coin_tag}\n\n"

        # 2. Тело новости (чистим от [...])
        summary = AdvancedMessageFormatter.clean_text(summary)
        summary_display = AdvancedMessageFormatter.smart_truncate(summary)

        # 3. Футер (Блок информации)
        footer = ""

        if ai_data and ai_data.get("sentiment"):
            footer += f"\n📊 Настроение: {ai_data['sentiment']}"

        if fear_greed:
            footer += f"\n😱 Индекс страха: {fear_greed['value']}/100"

        if prices:
            price_str = CryptoMultiPriceTracker.format_multi_prices(prices)
            if price_str: footer += f"\n\n{price_str}"

        # ✅ ИСПРАВЛЕНО: Убрано слово "Источник", оставлено название как ссылка
        # ✅ ИСПРАВЛЕНО: Новое название чата
        footer += f"\n\n📰 <a href='{source_url}'>{source}</a>"
        footer += f"\n👥 <a href='https://t.me/+hwsBvRtEj2w3NTli'>ОБЩИЙ ЧАТ BLEXLER</a>"

        return {
            "text": f"{header}{summary_display}{footer}",
            "image_url": image_url
        }


class RichMediaMessage:
    def __init__(self, text: str, image_url: Optional[str] = None):
        self.text = text
        self.image_url = image_url

    async def send(self, bot, chat_id: int):
        try:
            if self.image_url and ImageExtractor.is_valid_image_url(self.image_url):
                try:
                    await bot.send_photo(chat_id=chat_id, photo=self.image_url, caption=self.text, parse_mode="HTML")
                    logger.info("✅ Фото + текст отправлены")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка фото: {e}. Шлю текст.")
                    await bot.send_message(chat_id=chat_id, text=self.text, parse_mode="HTML",
                                           disable_web_page_preview=True)
            else:
                await bot.send_message(chat_id=chat_id, text=self.text, parse_mode="HTML",
                                       disable_web_page_preview=True)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
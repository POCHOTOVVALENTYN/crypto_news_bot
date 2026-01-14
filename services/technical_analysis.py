# services/technical_analysis.py
"""
Интеграция TradingView для технического анализа криптовалют.
Получает RSI, MACD, рейтинги для монет без использования AI.
"""
import logging
from typing import Optional, Dict
from functools import lru_cache

logger = logging.getLogger(__name__)

# Попытка импорта tradingview-ta (может быть не установлен)
try:
    from tradingview_ta import TA_Handler, Interval, Exchange
    TRADINGVIEW_AVAILABLE = True
except ImportError:
    TRADINGVIEW_AVAILABLE = False
    logger.warning("⚠️ tradingview-ta не установлен. Технический анализ отключен. Установите: pip install tradingview-ta")


class TechnicalAnalysis:
    """Класс для получения технического анализа с TradingView"""
    
    # Маппинг монет на TradingView символы (exchange, symbol, screener)
    SYMBOL_MAP = {
        'BTC': ('BINANCE', 'BTCUSDT', 'crypto'),
        'ETH': ('BINANCE', 'ETHUSDT', 'crypto'),
        'SOL': ('BINANCE', 'SOLUSDT', 'crypto'),
        'BNB': ('BINANCE', 'BNBUSDT', 'crypto'),
        'ADA': ('BINANCE', 'ADAUSDT', 'crypto'),
        'DOT': ('BINANCE', 'DOTUSDT', 'crypto'),
        'XRP': ('BINANCE', 'XRPUSDT', 'crypto'),
        'DOGE': ('BINANCE', 'DOGEUSDT', 'crypto'),
    }
    
    @staticmethod
    def _get_symbol_info(coin: str) -> Optional[tuple]:
        """Получает информацию о символе для TradingView (exchange, symbol, screener)"""
        coin_upper = coin.upper()
        return TechnicalAnalysis.SYMBOL_MAP.get(coin_upper)
    
    @staticmethod
    @lru_cache(maxsize=32)  # Кеш для 32 последних запросов
    def get_analysis_cached(coin: str) -> Optional[Dict]:
        """
        Получает технический анализ для монеты (с кешированием).
        
        Args:
            coin: Код монеты (BTC, ETH, SOL и т.д.)
        
        Returns:
            Словарь с данными анализа или None
        """
        if not TRADINGVIEW_AVAILABLE:
            return None
        
        symbol_info = TechnicalAnalysis._get_symbol_info(coin)
        if not symbol_info:
            return None
        
        exchange_name, symbol, screener = symbol_info
        
        try:
            # Используем интервал 1 час для анализа
            # В tradingview-ta exchange передается как строка
            handler = TA_Handler(
                symbol=symbol,
                screener=screener,
                exchange=exchange_name,
                interval=Interval.INTERVAL_1_HOUR
            )
            
            analysis = handler.get_analysis()
            
            # Извлекаем нужные данные
            indicators = analysis.indicators if hasattr(analysis, 'indicators') else {}
            summary = analysis.summary if hasattr(analysis, 'summary') else {}
            
            # Получаем RSI
            rsi = indicators.get('RSI')
            
            # Получаем MACD
            macd = indicators.get('MACD.macd')
            macd_signal = indicators.get('MACD.signal')
            
            # Получаем рейтинг (Strong Buy, Buy, Neutral, Sell, Strong Sell)
            recommendation = summary.get('RECOMMENDATION', 'NEUTRAL') if summary else 'NEUTRAL'
            
            result = {
                'coin': coin,
                'rsi': round(rsi, 2) if rsi else None,
                'macd': round(macd, 4) if macd else None,
                'macd_signal': round(macd_signal, 4) if macd_signal else None,
                'recommendation': recommendation,
            }
            
            logger.debug(f"✅ Технический анализ для {coin}: RSI={result['rsi']}, Rating={recommendation}")
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка получения тех. анализа для {coin}: {e}")
            return None
    
    @staticmethod
    async def get_technical_analysis(coin: str) -> Optional[Dict]:
        """
        Асинхронная обертка для получения технического анализа.
        Использует кеширование для снижения нагрузки.
        
        Args:
            coin: Код монеты (BTC, ETH, SOL и т.д.)
        
        Returns:
            Словарь с данными анализа или None
        """
        import asyncio
        # Запускаем синхронную функцию в отдельном потоке
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            TechnicalAnalysis.get_analysis_cached,
            coin.upper()
        )
    
    @staticmethod
    def format_technical_analysis(ta_data: Optional[Dict]) -> str:
        """
        Форматирует технический анализ для отображения в посте.
        
        Args:
            ta_data: Данные технического анализа
        
        Returns:
            Отформатированная строка или пустая строка
        """
        if not ta_data:
            return ""
        
        coin = ta_data.get('coin', '')
        rsi = ta_data.get('rsi')
        recommendation = ta_data.get('recommendation', 'NEUTRAL')
        
        parts = []
        
        # RSI
        if rsi:
            rsi_status = ""
            if rsi > 70:
                rsi_status = "Перекупленность"
            elif rsi < 30:
                rsi_status = "Перепроданность"
            else:
                rsi_status = "Нейтрально"
            
            parts.append(f"RSI {rsi} ({rsi_status})")
        
        # Рекомендация
        if recommendation and recommendation != 'NEUTRAL':
            # Переводим рекомендацию
            recommendation_ru = {
                'STRONG_BUY': 'Сильная покупка',
                'BUY': 'Покупка',
                'NEUTRAL': 'Нейтрально',
                'SELL': 'Продажа',
                'STRONG_SELL': 'Сильная продажа',
            }.get(recommendation, recommendation)
            
            parts.append(f"Рейтинг: {recommendation_ru}")
        
        if not parts:
            return ""
        
        return f"📊 {coin}: " + " | ".join(parts)


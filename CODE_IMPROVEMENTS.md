# 🔧 Конкретные улучшения кода

## 📝 Готовые исправления для внедрения

---

## 1. Система динамических приоритетов

### Файл: `services/priority_calculator.py` (новый файл)

```python
# services/priority_calculator.py
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PriorityCalculator:
    """Калькулятор приоритетов для новостей"""
    
    # Ключевые слова с весами важности
    CRITICAL_KEYWORDS = {
        # Критические события
        'hack': 10, 'hacked': 10, 'взлом': 10, 'взломали': 10,
        'exploit': 9, 'breach': 9, 'security breach': 10,
        'bankruptcy': 9, 'банкротство': 9, 'bankrupt': 9,
        
        # ETF и регуляция
        'etf approved': 9, 'etf approval': 9, 'etf одобрен': 9,
        'sec approval': 9, 'sec одобрил': 9,
        'sec rejects': 8, 'etf rejected': 8, 'etf отклонен': 8,
        'regulation': 6, 'регуляция': 6, 'regulatory': 6,
        
        # Листинги
        'listing': 7, 'листинг': 7, 'listed': 7,
        'coinbase listing': 8, 'binance listing': 8,
        'delisting': 6, 'делистинг': 6,
        
        # Институциональные
        'blackrock': 8, 'microstrategy': 8, 'grayscale': 7,
        'institutional': 7, 'институционалы': 7,
        'fidelity': 7, 'vanguard': 7,
        
        # Персоны
        'elon musk': 8, 'маск': 8, 'elon': 7,
        'michael saylor': 7, 'сайлор': 7,
        'gary gensler': 7, 'sec chairman': 7,
        'jerome powell': 6, 'джером пауэлл': 6,
        'cz binance': 6, 'changpeng zhao': 6,
    }
    
    # Влиятельные персоны (дополнительные бонусы)
    INFLUENTIAL_PERSONS = [
        'elon musk', 'маск', 'michael saylor', 'сайлор',
        'gary gensler', 'джером пауэлл', 'jerome powell',
        'cz binance', 'changpeng zhao', 'brian armstrong',
        'sam bankman-fried', 'sbf',
    ]
    
    # Премиум источники
    PREMIUM_SOURCES = [
        'coindesk', 'cointelegraph', 'the block', 'decrypt',
        'forklog', 'bits.media',
    ]
    
    @staticmethod
    def calculate_priority(news_item: Dict, ai_data: Optional[Dict] = None) -> int:
        """
        Вычисляет приоритет новости от 0 до 10
        
        Args:
            news_item: Словарь с новостью (title, summary, source)
            ai_data: Результат AI анализа (опционально)
        
        Returns:
            Приоритет от 0 до 10
        """
        priority = 0
        text = (news_item.get('title', '') + ' ' + news_item.get('summary', '')).lower()
        source = news_item.get('source', '').lower()
        
        # 1. Критические ключевые слова
        for keyword, weight in PriorityCalculator.CRITICAL_KEYWORDS.items():
            if keyword in text:
                priority = max(priority, weight)
                logger.debug(f"Найдено ключевое слово '{keyword}' → приоритет {weight}")
        
        # 2. Влиятельные персоны (дополнительный бонус)
        for person in PriorityCalculator.INFLUENTIAL_PERSONS:
            if person in text:
                priority = max(priority, 6)
                logger.debug(f"Упомянута персона '{person}' → приоритет минимум 6")
        
        # 3. Премиум источники
        if any(ps in source for ps in PriorityCalculator.PREMIUM_SOURCES):
            priority = max(priority, 4)
            logger.debug(f"Премиум источник '{source}' → приоритет минимум 4")
        
        # 4. AI анализ важности
        if ai_data:
            importance = ai_data.get('importance', '').lower()
            importance_score = ai_data.get('importance_score', 0)
            
            if importance == 'critical':
                priority = max(priority, 9)
            elif importance == 'very high':
                priority = max(priority, 8)
            elif importance == 'high':
                priority = max(priority, 7)
            elif importance == 'medium':
                priority = max(priority, 5)
            
            # Используем score если доступен
            if isinstance(importance_score, (int, float)) and importance_score > 0:
                priority = max(priority, min(int(importance_score), 10))
        
        # 5. Insider источники - максимальный приоритет
        if 'insider' in source:
            priority = 10
            logger.debug("Insider источник → приоритет 10")
        
        return min(priority, 10)  # Ограничиваем максимумом 10
```

---

## 2. Улучшенный AI промпт

### Файл: `services/ai_summary.py` (обновление метода analyze_text)

```python
# В классе NewsAnalyzer, метод analyze_text:

async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
    """Универсальный метод анализа с улучшенным промптом"""
    
    prompt = f"""Ты эксперт-аналитик криптовалютного рынка с 10+ летним опытом.

ВХОДНАЯ НОВОСТЬ:
"{text}"

ЗАДАЧА:
1. Определить КРИТИЧЕСКУЮ ВАЖНОСТЬ новости (0-10)
2. Создать цепляющий заголовок на русском (до 10 слов)
3. Написать краткое описание (2-3 предложения, только суть)
4. Определить тональность (Extreme Bullish / Bullish / Neutral / Bearish / Extreme Bearish)
5. Указать монету (BTC, ETH, SOL, или Market)
6. Оценить влияние на рынок (High / Medium / Low)

КРИТЕРИИ ВАЖНОСТИ:
- 10 (Critical): Взломы, банкротства, критические регуляторные решения
- 9 (Very High): ETF одобрения, крупные листинги, институциональные инвестиции >$100M
- 8 (High): Регуляторные новости, средние листинги, заявления ключевых персон
- 7 (High): Крупные транзакции >$50M, важные обновления протоколов
- 6 (Medium): Значимые обновления, средние новости
- 4-5 (Medium): Обычные новости
- 0-3 (Low): Низкая важность, рутинные обновления

ВАЖНО:
- Заголовок должен быть информативным и цепляющим
- Описание - только ключевая информация, без воды
- Тональность должна отражать возможное влияние на цену
- Если новость не относится к крипто - верни importance: "Low"

ФОРМАТ ОТВЕТА (только JSON, без Markdown):
{{
    "importance": "Critical|Very High|High|Medium|Low",
    "importance_score": 10,
    "ru_title": "...",
    "ru_summary": "...",
    "sentiment": "Bullish|Bearish|Neutral|Extreme Bullish|Extreme Bearish",
    "coin": "BTC|ETH|SOL|Market",
    "market_impact": "High|Medium|Low"
}}"""

    # ... остальной код без изменений
```

---

## 3. Предварительный анализ RSS новостей

### Файл: `main.py` (обновление функции scheduled_parsing)

```python
# Добавить импорт
from services.priority_calculator import PriorityCalculator

# Обновить функцию scheduled_parsing:
@safe_task("RSS Parsing")
async def scheduled_parsing():
    """Сбор новостей с предварительным анализом"""
    logger.info("🔍 Парсер: ищу свежие новости...")
    news_list = await rss_parser.get_all_news()
    count = 0
    high_priority_count = 0

    for news in news_list:
        if await db.news_exists(news['link']):
            continue
        
        # ПРЕДВАРИТЕЛЬНЫЙ AI АНАЛИЗ для определения приоритета
        ai_analysis = None
        try:
            ai_analysis = await ai_analyzer.analyze_text(
                news['title'] + " " + news['summary']
            )
            if ai_analysis:
                logger.debug(f"✅ AI анализ выполнен для: {news['title'][:50]}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предварительного AI анализа: {e}")
        
        # Вычисляем приоритет на основе ключевых слов и AI
        priority = PriorityCalculator.calculate_priority(news, ai_analysis)
        
        # Фильтруем очень низкоприоритетные новости (можно настроить порог)
        if priority < 2:
            logger.debug(f"⏭️ Пропуск низкоприоритетной новости (priority={priority}): {news['title'][:50]}")
            continue
        
        # Сохраняем с вычисленным приоритетом
        success = await db.add_news(
            url=news['link'],
            title=news['title'],
            summary=news['summary'],
            source=news['source'],
            published_at=news['published'],
            image_url=news['image_url'],
            priority=priority  # Используем вычисленный приоритет
        )
        
        if success:
            count += 1
            if priority >= 6:
                high_priority_count += 1
                logger.info(f"🔥 Высокоприоритетная новость (priority={priority}): {news['title'][:50]}")

    if count > 0:
        logger.info(f"📥 Добавлено {count} новостей (из них {high_priority_count} высокоприоритетных)")
```

---

## 4. Проверка актуальности новостей

### Файл: `utils/news_validator.py` (новый файл)

```python
# utils/news_validator.py
import re
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class NewsValidator:
    """Валидатор новостей"""
    
    MAX_AGE_HOURS = 48  # Максимальный возраст новости в часах
    
    @staticmethod
    def is_news_relevant(news_item: Dict, max_age_hours: int = None) -> bool:
        """
        Проверяет актуальность новости
        
        Args:
            news_item: Словарь с новостью
            max_age_hours: Максимальный возраст в часах (по умолчанию MAX_AGE_HOURS)
        
        Returns:
            True если новость актуальна, False если устарела
        """
        if max_age_hours is None:
            max_age_hours = NewsValidator.MAX_AGE_HOURS
        
        try:
            published_at = news_item.get('published_at', '')
            if not published_at:
                # Если даты нет, считаем актуальной
                return True
            
            # Различные форматы дат
            date_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%S%z',
                '%a, %d %b %Y %H:%M:%S %Z',
                '%a, %d %b %Y %H:%M:%S %z',
                '%d %b %Y %H:%M:%S',
            ]
            
            pub_date = None
            for fmt in date_formats:
                try:
                    pub_date = datetime.strptime(published_at, fmt)
                    break
                except ValueError:
                    continue
            
            if not pub_date:
                # Если не удалось распарсить, считаем актуальной
                logger.warning(f"⚠️ Не удалось распарсить дату: {published_at}")
                return True
            
            age = datetime.now() - pub_date.replace(tzinfo=None) if pub_date.tzinfo else datetime.now() - pub_date
            
            if age > timedelta(hours=max_age_hours):
                logger.debug(f"⏰ Новость устарела ({age.total_seconds()/3600:.1f}ч): {news_item.get('title', '')[:50]}")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки актуальности: {e}")
            return True  # В случае ошибки считаем актуальной
    
    @staticmethod
    def validate_news_item(news_item: Dict) -> tuple[bool, Optional[str]]:
        """
        Валидация новости перед сохранением
        
        Returns:
            (is_valid, error_message)
        """
        # Проверка заголовка
        title = news_item.get('title', '').strip()
        if not title or len(title) < 5:
            return False, "Заголовок слишком короткий"
        
        if len(title) > 500:
            return False, "Заголовок слишком длинный"
        
        # Проверка URL
        url = news_item.get('url', '').strip()
        if not url:
            return False, "URL не указан"
        
        # Проверка источника
        source = news_item.get('source', '').strip()
        if not source:
            return False, "Источник не указан"
        
        # Проверка на подозрительные символы
        if any(char in title for char in ['--', ';', '/*', '*/']):
            return False, "Подозрительные символы в заголовке"
        
        return True, None
```

---

## 5. Обновление scheduled_parsing с валидацией

### Файл: `main.py` (полная версия)

```python
from utils.news_validator import NewsValidator

@safe_task("RSS Parsing")
async def scheduled_parsing():
    """Сбор новостей с предварительным анализом и валидацией"""
    logger.info("🔍 Парсер: ищу свежие новости...")
    news_list = await rss_parser.get_all_news()
    count = 0
    high_priority_count = 0
    filtered_count = 0

    for news in news_list:
        # Валидация
        is_valid, error = NewsValidator.validate_news_item(news)
        if not is_valid:
            logger.debug(f"❌ Новость не прошла валидацию: {error}")
            filtered_count += 1
            continue
        
        # Проверка актуальности
        if not NewsValidator.is_news_relevant(news):
            filtered_count += 1
            continue
        
        # Проверка дубликатов
        if await db.news_exists(news['link']):
            continue
        
        # ПРЕДВАРИТЕЛЬНЫЙ AI АНАЛИЗ
        ai_analysis = None
        try:
            ai_analysis = await ai_analyzer.analyze_text(
                news['title'] + " " + news['summary']
            )
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предварительного AI анализа: {e}")
        
        # Вычисляем приоритет
        priority = PriorityCalculator.calculate_priority(news, ai_analysis)
        
        # Фильтруем низкоприоритетные новости
        if priority < 2:
            logger.debug(f"⏭️ Пропуск низкоприоритетной новости (priority={priority})")
            filtered_count += 1
            continue
        
        # Сохраняем
        success = await db.add_news(
            url=news['link'],
            title=news['title'],
            summary=news['summary'],
            source=news['source'],
            published_at=news['published'],
            image_url=news['image_url'],
            priority=priority
        )
        
        if success:
            count += 1
            if priority >= 6:
                high_priority_count += 1
                logger.info(f"🔥 Высокоприоритетная (priority={priority}): {news['title'][:50]}")

    logger.info(f"📥 Добавлено {count} новостей ({high_priority_count} высокоприоритетных), отфильтровано {filtered_count}")
```

---

## 6. Обновление базы данных для поддержки расширенного приоритета

### Файл: `database.py` (миграция не требуется, но можно добавить индекс)

```python
async def init(self):
    async with aiosqlite.connect(self.db_path) as db:
        # Создание таблицы (без изменений, priority уже INTEGER)
        await db.execute("""
                         CREATE TABLE IF NOT EXISTS news
                         (
                             id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                             url                TEXT UNIQUE NOT NULL,
                             title              TEXT        NOT NULL,
                             summary            TEXT,
                             image_url          TEXT,
                             source             TEXT        NOT NULL,
                             published_at       TEXT        NOT NULL,
                             added_at           TEXT    DEFAULT CURRENT_TIMESTAMP,
                             posted_to_telegram BOOLEAN DEFAULT 0,
                             priority           INTEGER DEFAULT 0
                         )
                         """)
        
        # Добавляем индекс для быстрого поиска по приоритету
        await db.execute("""
                         CREATE INDEX IF NOT EXISTS idx_priority_posted 
                         ON news(priority DESC, posted_to_telegram, id ASC)
                         """)
        
        await db.commit()
```

---

## 7. Обновление get_hot_news для поддержки разных уровней приоритета

### Файл: `database.py`

```python
async def get_hot_news(self, min_priority: int = 6):
    """
    Ищет самую старую НЕОПУБЛИКОВАННУЮ новость с высоким приоритетом
    
    Args:
        min_priority: Минимальный приоритет для "горячей" новости (по умолчанию 6)
    
    Returns:
        Словарь с новостью или None
    """
    async with aiosqlite.connect(self.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
                "SELECT * FROM news WHERE posted_to_telegram = 0 AND priority >= ? ORDER BY priority DESC, id ASC LIMIT 1",
                (min_priority,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
```

---

## 8. Обновление main.py для использования нового get_hot_news

### Файл: `main.py`

```python
@safe_task("Queue Poster")
async def check_queue_and_post():
    """Проверка очереди и публикация (защищено декоратором)"""
    # 1. Горячие новости (приоритет >= 6)
    hot_news = await db.get_hot_news(min_priority=6)
    is_hot = False

    if hot_news:
        news_item = hot_news
        is_hot = True
        priority = news_item.get('priority', 0)
        logger.info(f"🔥 Молния! Публикую вне очереди (priority={priority}).")
    else:
        # 2. Обычная очередь
        if not rate_limiter.can_post():
            return
        news_item = await db.get_oldest_unposted_news()

    if not news_item:
        return

    # ... остальной код без изменений
```

---

## 📋 Чеклист внедрения

- [ ] Создать файл `services/priority_calculator.py`
- [ ] Обновить `services/ai_summary.py` с новым промптом
- [ ] Создать файл `utils/news_validator.py`
- [ ] Обновить `main.py` - функция `scheduled_parsing`
- [ ] Обновить `database.py` - добавить индекс, обновить `get_hot_news`
- [ ] Обновить `main.py` - функция `check_queue_and_post`
- [ ] Протестировать систему приоритетов
- [ ] Проверить работу валидации
- [ ] Убедиться что AI анализ работает корректно

---

*Документ с готовыми исправлениями*
*Последнее обновление: $(date)*


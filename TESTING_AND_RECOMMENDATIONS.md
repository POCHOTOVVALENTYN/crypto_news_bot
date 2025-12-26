# 🧪 Тестирование и рекомендации после исправлений

## ✅ Выполненные исправления

1. ✅ **Исправлен импорт Gemini API** - заменен `google-genai` на `google-generativeai` в requirements.txt
2. ✅ **Улучшена обработка ошибок в check_queue_and_post** - добавлен try-except для AI обработки
3. ✅ **Улучшена обработка исключений в database.add_news** - добавлена обработка всех типов ошибок БД
4. ✅ **Улучшена проверка данных в telegram_listener** - добавлена валидация структуры данных от AI
5. ✅ **Добавлен безопасный запуск listener** - функция `safe_start_listener()` с обработкой ошибок
6. ✅ **Исправлен rate limiter** - теперь обновляется для всех постов, включая горячие новости

---

## 🧪 План тестирования

### Тест 1: Проверка импортов и синтаксиса

```bash
# Проверка синтаксиса Python файлов
python -m py_compile main.py
python -m py_compile database.py
python -m py_compile services/ai_summary.py
python -m py_compile services/telegram_listener.py

# Проверка импортов (если есть виртуальное окружение)
python -c "import google.generativeai; print('✅ google-generativeai импортирован')"
python -c "from database import db; print('✅ database импортирован')"
python -c "from services.ai_summary import NewsAnalyzer; print('✅ NewsAnalyzer импортирован')"
```

**Ожидаемый результат:** Все файлы компилируются без ошибок, импорты работают.

---

### Тест 2: Тестирование обработки ошибок в database.add_news

**Сценарий:** Попытка добавить новость с дубликатом URL и с некорректными данными.

```python
# Тест дубликата (должен вернуть False без ошибки)
result1 = await db.add_news(
    url="test_url_123",
    title="Test Title",
    summary="Test Summary",
    source="Test Source",
    published_at="2024-01-01",
    priority=0
)
print(f"Первая запись: {result1}")  # Ожидается True

result2 = await db.add_news(
    url="test_url_123",  # Дубликат
    title="Test Title 2",
    summary="Test Summary 2",
    source="Test Source 2",
    published_at="2024-01-02",
    priority=0
)
print(f"Дубликат: {result2}")  # Ожидается False

# Тест с None значениями (должен обработать без падения)
result3 = await db.add_news(
    url="test_url_456",
    title=None,  # Может быть проблема с NOT NULL
    summary="Test Summary",
    source="Test Source",
    published_at="2024-01-01",
    priority=0
)
print(f"None title: {result3}")  # Ожидается False или Exception (но обработанный)
```

**Ожидаемый результат:** 
- Дубликат возвращает False без исключения
- Другие ошибки логируются и возвращают False

---

### Тест 3: Тестирование обработки ошибок AI в check_queue_and_post

**Сценарий:** Симуляция ошибки AI анализатора.

```python
# Мокируем ai_analyzer для теста
class MockAI:
    async def analyze_text(self, text):
        raise Exception("Simulated AI error")
    
    async def translate_and_analyze(self, title, summary):
        return None  # Симуляция возврата None

# В check_queue_and_post должна быть обработка
# и логирование ошибки без падения функции
```

**Ожидаемый результат:**
- Ошибка логируется с полным traceback
- Функция продолжает работу с оригинальными данными
- Пост публикуется даже при ошибке AI

---

### Тест 4: Тестирование валидации данных в telegram_listener

**Сценарий:** AI возвращает неполные данные или None.

```python
# Симуляция неполных данных
processed = {"ru_title": "Title"}  # Нет ru_summary
# Должен быть обработан и пропущен с предупреждением

processed = None  # None значение
# Должен быть обработан и пропущен с debug сообщением

processed = {"ru_title": "Title", "ru_summary": "Summary"}  # Корректные данные
# Должен быть обработан и сохранен
```

**Ожидаемый результат:**
- Неполные данные логируются с предупреждением
- None значения обрабатываются корректно
- Корректные данные сохраняются в БД

---

### Тест 5: Тестирование rate limiter

**Сценарий:** Проверка обновления rate limiter для всех типов постов.

```python
# Обычная новость
rate_limiter.mark_posted()  # Обновляется
print(f"Last post time: {rate_limiter.last_post_time}")

# Горячая новость (молния)
# rate_limiter.mark_posted() также должен вызываться
# Проверить что timestamp обновляется
```

**Ожидаемый результат:**
- Rate limiter обновляется для всех постов
- Время последнего поста корректно сохраняется

---

### Тест 6: Интеграционное тестирование

**Сценарий:** Полный цикл от RSS парсинга до публикации.

1. **Парсинг RSS:**
   ```python
   news_list = await rss_parser.get_all_news()
   # Проверить что новости получены и отфильтрованы
   ```

2. **Добавление в БД:**
   ```python
   for news in news_list:
       await db.add_news(...)
   # Проверить что новости добавлены
   ```

3. **Обработка очереди:**
   ```python
   await check_queue_and_post()
   # Проверить что пост опубликован
   ```

**Ожидаемый результат:**
- Все этапы выполняются без ошибок
- Новости публикуются корректно
- Логи содержат информативные сообщения

---

## 📊 Рекомендации для улучшения

### 1. 🔄 Добавить retry механизм для критических операций

**Проблема:** При временных сбоях (сеть, блокировка БД) операции могут упасть.

**Решение:**
```python
import asyncio
from functools import wraps

def retry_on_failure(max_retries=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait_time = delay * (backoff ** attempt)
                    logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась. Повтор через {wait_time}с")
                    await asyncio.sleep(wait_time)
        return wrapper
    return decorator

# Использование:
@retry_on_failure(max_retries=3, delay=1)
async def add_news(...):
    ...
```

**Где применить:**
- `database.add_news()` - для обработки временных блокировок БД
- `get_multiple_crypto_prices()` - для сетевых запросов
- `FearGreedIndexTracker.get_fear_greed_index()` - для сетевых запросов

---

### 2. 📈 Добавить метрики и мониторинг

**Проблема:** Нет статистики по успешности операций.

**Решение:**
```python
from collections import defaultdict
from datetime import datetime

class Metrics:
    def __init__(self):
        self.counters = defaultdict(int)
        self.timings = defaultdict(list)
        self.errors = []
    
    def increment(self, metric: str, value: int = 1):
        self.counters[metric] += value
    
    def record_timing(self, metric: str, duration: float):
        self.timings[metric].append(duration)
    
    def record_error(self, error: Exception, context: str):
        self.errors.append({
            'error': str(error),
            'context': context,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_stats(self) -> dict:
        return {
            'counters': dict(self.counters),
            'avg_timings': {
                k: sum(v) / len(v) if v else 0
                for k, v in self.timings.items()
            },
            'error_count': len(self.errors),
            'recent_errors': self.errors[-10:]
        }

# Глобальный экземпляр
metrics = Metrics()

# Использование:
async def check_queue_and_post():
    start_time = time.time()
    try:
        # ... код ...
        metrics.increment('posts_successful')
    except Exception as e:
        metrics.increment('posts_failed')
        metrics.record_error(e, 'check_queue_and_post')
    finally:
        duration = time.time() - start_time
        metrics.record_timing('post_duration', duration)
```

**Где применить:**
- Счетчики: успешных/неуспешных постов, парсингов, AI обработок
- Тайминги: время обработки AI, время публикации
- Ошибки: логирование последних ошибок

---

### 3. 🗄️ Улучшить управление соединениями с БД

**Проблема:** Каждая операция открывает новое соединение, что может быть неэффективно.

**Решение:**
```python
class NewsDatabase:
    def __init__(self):
        self.db_path = DB_PATH
        self._connection = None
        self._lock = asyncio.Lock()
    
    async def get_connection(self):
        """Получить или создать соединение с БД"""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            # Настройка соединения
            self._connection.row_factory = aiosqlite.Row
        return self._connection
    
    async def close(self):
        """Закрыть соединение"""
        if self._connection:
            await self._connection.close()
            self._connection = None
```

**Альтернатива (рекомендуется):** Использовать пул соединений или сохранить текущий подход (каждое соединение закрывается автоматически), но добавить обработку блокировок.

---

### 4. 🔍 Добавить более детальное логирование

**Проблема:** Недостаточно контекста в логах для отладки.

**Решение:**
```python
import logging
import json
from datetime import datetime

class StructuredLogger:
    def __init__(self, logger):
        self.logger = logger
    
    def _log(self, level, message, **kwargs):
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'message': message,
            **kwargs
        }
        self.logger.log(level, json.dumps(log_data))
    
    def info(self, message, **kwargs):
        self._log(logging.INFO, message, **kwargs)
    
    def error(self, message, **kwargs):
        self._log(logging.ERROR, message, **kwargs)

# Использование:
structured_logger = StructuredLogger(logger)
structured_logger.info("Публикация новости", 
                       news_id=news_item['id'],
                       source=news_item['source'],
                       has_ai_data=ai_data is not None)
```

---

### 5. 🛡️ Добавить валидацию данных на входе

**Проблема:** Недостаточно валидации входных данных.

**Решение:**
```python
from typing import Optional
import re

def validate_news_item(news_item: dict) -> tuple[bool, Optional[str]]:
    """Валидация новости перед сохранением"""
    if not news_item.get('title') or len(news_item['title'].strip()) < 5:
        return False, "Заголовок слишком короткий"
    
    if not news_item.get('url') or not news_item['url'].startswith(('http://', 'https://', 'tg_')):
        return False, "Некорректный URL"
    
    if not news_item.get('source'):
        return False, "Источник не указан"
    
    # Проверка на SQL инъекции (хотя используется параметризованный запрос)
    if any(char in news_item.get('title', '') for char in ['--', ';', '/*']):
        return False, "Подозрительные символы в заголовке"
    
    return True, None

# Использование:
is_valid, error = validate_news_item(news_item)
if not is_valid:
    logger.warning(f"Новость не прошла валидацию: {error}")
    return
```

---

### 6. 🔐 Добавить rate limiting для внешних API

**Проблема:** Возможны превышения лимитов запросов к CoinGecko и другим API.

**Решение:**
```python
from collections import deque
import time

class APIRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
    
    async def acquire(self):
        """Ожидать возможности сделать запрос"""
        now = time.time()
        # Удаляем старые запросы
        while self.requests and self.requests[0] < now - self.window_seconds:
            self.requests.popleft()
        
        # Если лимит превышен, ждем
        if len(self.requests) >= self.max_requests:
            wait_time = self.window_seconds - (now - self.requests[0])
            if wait_time > 0:
                logger.info(f"⏳ Rate limit: ожидание {wait_time:.1f}с")
                await asyncio.sleep(wait_time)
                return await self.acquire()  # Рекурсивный вызов
        
        self.requests.append(time.time())

# Использование:
coingecko_limiter = APIRateLimiter(max_requests=50, window_seconds=60)

async def get_multiple_crypto_prices():
    await coingecko_limiter.acquire()
    # ... запрос к API ...
```

---

### 7. 🧪 Добавить unit тесты

**Рекомендация:** Создать тесты для критических функций.

```python
# tests/test_database.py
import pytest
import asyncio
from database import NewsDatabase

@pytest.mark.asyncio
async def test_add_news_success():
    db = NewsDatabase()
    await db.init()
    result = await db.add_news(
        url="test_url_1",
        title="Test Title",
        summary="Test Summary",
        source="Test Source",
        published_at="2024-01-01"
    )
    assert result is True

@pytest.mark.asyncio
async def test_add_news_duplicate():
    db = NewsDatabase()
    await db.init()
    await db.add_news(
        url="test_url_2",
        title="Test Title",
        summary="Test Summary",
        source="Test Source",
        published_at="2024-01-01"
    )
    result = await db.add_news(
        url="test_url_2",  # Дубликат
        title="Test Title 2",
        summary="Test Summary 2",
        source="Test Source 2",
        published_at="2024-01-02"
    )
    assert result is False
```

---

### 8. 📝 Добавить документацию к функциям

**Рекомендация:** Добавить docstrings с примерами использования.

```python
async def add_news(self, url: str, title: str, summary: str, source: str,
                   published_at: str, image_url: str = None, priority: int = 0) -> bool:
    """
    Добавляет новость в базу данных.
    
    Args:
        url: Уникальный URL новости (может быть 'tg_chatid_msgid' для Telegram)
        title: Заголовок новости
        summary: Краткое описание
        source: Источник новости
        published_at: Дата публикации (строка)
        image_url: URL изображения (опционально)
        priority: Приоритет (0 - обычный, 1 - молния)
    
    Returns:
        True если новость добавлена, False если дубликат или ошибка
    
    Example:
        >>> result = await db.add_news(
        ...     url="https://example.com/news/1",
        ...     title="Bitcoin reached new ATH",
        ...     summary="BTC price hit $100k",
        ...     source="CoinDesk",
        ...     published_at="2024-01-01",
        ...     priority=0
        ... )
        >>> assert result is True
    """
    ...
```

---

### 9. 🚨 Улучшить систему алертов

**Рекомендация:** Добавить разные типы алертов с приоритетами.

```python
class AlertManager:
    async def send_alert(self, text: str, level: str = "ERROR", 
                         tags: list = None, metric_value: float = None):
        """
        Отправляет алерт с дополнительными метаданными.
        
        Args:
            text: Текст сообщения
            level: Уровень важности (ERROR, CRITICAL, WARNING, INFO)
            tags: Теги для категоризации (например, ['database', 'critical'])
            metric_value: Численное значение метрики (например, время ответа)
        """
        message = f"{emoji} <b>{level}</b>\n\n{text}"
        
        if tags:
            message += f"\n\n🏷️ Теги: {', '.join(tags)}"
        
        if metric_value is not None:
            message += f"\n📊 Значение: {metric_value}"
        
        # Отправка...
```

---

### 10. 🔄 Добавить механизм миграций БД

**Рекомендация:** Для будущих изменений схемы БД.

```python
class DatabaseMigrator:
    async def migrate(self):
        """Выполняет миграции БД"""
        current_version = await self.get_schema_version()
        migrations = [
            (1, self._migration_001_add_priority),
            (2, self._migration_002_add_indexes),
        ]
        
        for version, migration_func in migrations:
            if version > current_version:
                logger.info(f"Применение миграции {version}...")
                await migration_func()
                await self.set_schema_version(version)
```

---

## ✅ Чеклист проверки после изменений

- [x] Все исправления внесены в код
- [ ] Код скомпилирован без ошибок
- [ ] Импорты работают корректно
- [ ] Обработка ошибок в database.add_news протестирована
- [ ] Обработка ошибок AI протестирована
- [ ] Валидация данных в telegram_listener протестирована
- [ ] Rate limiter работает корректно
- [ ] Логи содержат информативные сообщения
- [ ] Нет критических ошибок в логах
- [ ] Бот успешно запускается и работает

---

## 📋 Приоритеты внедрения рекомендаций

1. **Высокий приоритет:**
   - ✅ Retry механизм для критических операций
   - ✅ Метрики и мониторинг
   - ✅ Unit тесты для database методов

2. **Средний приоритет:**
   - ⚠️ Улучшенное логирование
   - ⚠️ Валидация данных на входе
   - ⚠️ Rate limiting для внешних API

3. **Низкий приоритет:**
   - ℹ️ Документация
   - ℹ️ Улучшенные алерты
   - ℹ️ Миграции БД

---

*Документ создан после исправления критических ошибок*
*Дата: $(date)*


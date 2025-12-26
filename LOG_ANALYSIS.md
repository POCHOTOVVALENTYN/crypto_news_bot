# 🔍 Детальный анализ логов и найденные проблемы

## 📊 Общая статистика работы бота

- ✅ Бот успешно запустился
- ✅ БД подключена
- ✅ Планировщик работает
- ✅ Посты публикуются (2 поста за период)
- ❌ Множественные 429 ошибки (превышение квоты API)
- ❌ Userbot не запускается
- ⚠️ Задачи пропускаются из-за блокировки

---

## 🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### 1. Превышение квоты API (429 ошибки) - КРИТИЧНО

**Проблема:**
```
429 RESOURCE_EXHAUSTED - You exceeded your current quota
Quota exceeded for: gemini-2.0-flash-exp (free tier limit: 0)
```

**Частота:** Встречается при каждом AI запросе

**Последствия:**
- ❌ AI анализ не работает
- ❌ Новости публикуются без AI обработки
- ❌ Предварительный анализ RSS не работает
- ❌ Бот тратит ресурсы на бесполезные запросы

**Причины:**
1. Использование `gemini-2.0-flash-exp` (экспериментальная модель) - возможно нет квоты на free tier
2. Нет retry механизма с exponential backoff
3. Нет rate limiting для AI запросов
4. Слишком много запросов при парсинге RSS

**Решение:**

#### 1.1. Использовать стабильную модель вместо экспериментальной

**Проблема:** `gemini-2.0-flash-exp` может не поддерживаться на free tier

**Исправление:**
```python
# services/ai_summary.py, метод _find_best_model()
preferred_models = [
    'gemini-1.5-flash',  # Стабильная модель для free tier
    'gemini-1.5-pro',    # Альтернатива
]
# Убрать экспериментальные модели
```

#### 1.2. Добавить rate limiting для AI запросов

**Проблема:** Слишком много запросов подряд при парсинге RSS

**Решение:** Ограничить количество параллельных AI запросов

#### 1.3. Добавить retry с exponential backoff для 429 ошибок

**Проблема:** Нет обработки 429 ошибок с автоматическим retry

**Решение:** Реализовать retry механизм, который:
- Парсит `retryDelay` из ответа API
- Использует exponential backoff
- Ограничивает количество попыток

---

### 2. Userbot не запускается - ВАЖНО

**Проблема:**
```
⚠️ ОБНАРУЖЕН ФАЙЛ СЕССИИ (небезопасно!)
🔄 Мигрирую в StringSession...
ERROR: Task was destroyed but it is pending
ALERT: Userbot не запущен, хотя TG_API_ID настроен!
```

**Причины:**
1. Миграция сессии блокируется или падает
2. Task уничтожается до завершения
3. Нет правильной обработки асинхронных операций при миграции

**Последствия:**
- ❌ Userbot не работает
- ❌ Не получаются инсайды из Telegram каналов
- ⚠️ Алерты каждые 10 минут

**Решение:**
- Исправить логику миграции сессии
- Добавить правильный cleanup для async задач
- Улучшить обработку ошибок при запуске userbot

---

### 3. Задачи пропускаются (Missed jobs) - СРЕДНЯЯ ВАЖНОСТЬ

**Проблема:**
```
WARNING - Run time of job "Queue Poster" was missed by 0:00:25.626214
WARNING - Run time of job "RSS Parsing" was missed by 0:06:25.628643
```

**Причины:**
- Задачи блокируются долгими операциями (AI анализ, сетевые запросы)
- Нет обработки таймаутов
- Слишком частый запуск Queue Poster (30 секунд) при долгих операциях

**Последствия:**
- ⚠️ Нестабильная работа планировщика
- ⚠️ Возможная потеря новостей

**Решение:**
- Увеличить интервал Queue Poster до 60 секунд
- Добавить таймауты для долгих операций
- Оптимизировать AI запросы (batch processing)

---

## ⚠️ ВАЖНЫЕ ПРОБЛЕМЫ

### 4. Отсутствие информации о добавленных новостях

**Проблема:**
В логах нет информации о количестве добавленных новостей после RSS парсинга:
```
✅ Found 20 entries from Forklog
✅ Found 10 entries from Coinspot
...
Job "RSS Parsing" executed successfully
```

**Решение:**
Добавить логирование итоговой статистики (количество добавленных, отфильтрованных новостей)

---

### 5. Task was destroyed but it is pending

**Проблема:**
```
asyncio - ERROR - Task was destroyed but it is pending!
task: <Task pending name='Task-2' coro=<safe_start_listener()>
```

**Причины:**
- Task создается через `asyncio.create_task()` но не дожидается завершения
- При выходе из программы tasks уничтожаются до завершения

**Решение:**
- Правильный cleanup при выходе
- Использование `asyncio.gather()` или отслеживание tasks

---

### 6. Pydantic warnings (не критично)

**Проблема:**
```
UserWarning: Field name "name" shadows an attribute in parent "Operation"
```

**Решение:**
Подавить warnings или обновить зависимости

---

### 7. Network errors (временные)

**Проблема:**
```
Failed to fetch updates - TelegramNetworkError: HTTP Client says - Request timeout error
Cannot connect to host api.telegram.org:443
```

**Причины:**
- Временные проблемы с сетью
- Таймауты подключения

**Решение:**
- Aiogram автоматически обрабатывает (есть retry)
- Это нормально, не требует исправления

---

### 8. Update not handled (нормально)

**Проблема:**
```
Update id=752072526 is not handled
```

**Причина:**
- Обновления от Telegram, для которых нет обработчиков

**Решение:**
- Это нормально, не критично
- Можно добавить обработчики если нужно

---

## 🔧 КОНКРЕТНЫЕ ИСПРАВЛЕНИЯ

### Исправление 1: Заменить экспериментальную модель на стабильную

**Файл:** `services/ai_summary.py`

```python
def _find_best_model(self):
    """Выбирает лучшую доступную модель"""
    try:
        # Приоритетный список моделей (БЕЗ экспериментальных для free tier)
        preferred_models = [
            'gemini-1.5-flash',      # Стабильная модель для free tier
            'gemini-1.5-pro',        # Альтернатива
        ]
        
        # Просто возвращаем стабильную модель
        logger.info("✅ Используем стабильную модель: gemini-1.5-flash")
        return 'gemini-1.5-flash'
        
    except Exception as e:
        logger.error(f"❌ Ошибка выбора модели: {e}")
        return 'gemini-1.5-flash'  # Fallback
```

---

### Исправление 2: Добавить retry механизм для 429 ошибок

**Файл:** `services/ai_summary.py` (новый метод)

```python
import time
from typing import Optional, Dict

async def _retry_with_backoff(self, func, max_retries=3, initial_delay=1):
    """Retry с exponential backoff для 429 ошибок"""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            error_str = str(e)
            
            # Проверяем на 429 ошибку
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str or 'quota' in error_str.lower():
                if attempt < max_retries - 1:
                    # Парсим retryDelay из ошибки (если есть)
                    retry_delay = initial_delay * (2 ** attempt)
                    
                    # Пробуем извлечь retryDelay из ошибки Gemini
                    if 'retryDelay' in error_str or 'Please retry in' in error_str:
                        import re
                        match = re.search(r'retry in ([\d.]+)s', error_str)
                        if match:
                            retry_delay = float(match.group(1))
                            logger.warning(f"⏳ API квота превышена, ожидание {retry_delay:.1f}с...")
                            await asyncio.sleep(retry_delay)
                            continue
                    
                    logger.warning(f"⏳ Rate limit (попытка {attempt + 1}/{max_retries}), ожидание {retry_delay}с...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    logger.error(f"❌ Превышен лимит попыток для AI API")
                    raise
            else:
                # Другие ошибки - пробрасываем
                raise
    
    return None

async def analyze_text(self, text: str, context: str = "news") -> Optional[Dict]:
    """Универсальный метод анализа с retry механизмом"""
    
    # ... промпт без изменений ...
    
    # 1. Попытка через Gemini с retry
    if self.client and self.model_name:
        try:
            async def gemini_call():
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model=self.model_name,
                        contents=prompt
                    ),
                    timeout=20.0
                )
                return response
            
            response = await self._retry_with_backoff(gemini_call, max_retries=3)
            
            if response and hasattr(response, 'text') and response.text:
                result = self._clean_json_response(response.text)
                if result:
                    return result
                    
        except Exception as e:
            logger.error(f"❌ Gemini Error после retry: {e}")
    
    # 2. Попытка через OpenAI с retry
    if self.openai_client:
        try:
            async def openai_call():
                return await self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[...],
                    timeout=15
                )
            
            response = await self._retry_with_backoff(openai_call, max_retries=2)
            if response:
                content = response.choices[0].message.content
                return json.loads(content)
        except Exception as e:
            logger.error(f"❌ OpenAI Error после retry: {e}")
    
    return None
```

---

### Исправление 3: Ограничить AI запросы при RSS парсинге

**Проблема:** При парсинге RSS делается AI анализ для КАЖДОЙ новости, что быстро исчерпывает квоту

**Решение:** 
1. Ограничить количество AI запросов за один цикл парсинга
2. Использовать только ключевые слова для определения приоритета (без AI) для большинства новостей
3. AI анализ только для явно важных новостей (по ключевым словам)

**Файл:** `main.py`, функция `scheduled_parsing()`

```python
@safe_task("RSS Parsing")
async def scheduled_parsing():
    """Сбор новостей с умным AI анализом"""
    logger.info("🔍 Парсер: ищу свежие новости...")
    news_list = await rss_parser.get_all_news()
    count = 0
    high_priority_count = 0
    filtered_count = 0
    ai_requests_count = 0
    max_ai_requests_per_cycle = 10  # Ограничение AI запросов

    for news in news_list:
        # Валидация
        is_valid, error = NewsValidator.validate_news_item(news)
        if not is_valid:
            filtered_count += 1
            continue
        
        # Проверка актуальности
        if not NewsValidator.is_news_relevant(news):
            filtered_count += 1
            continue
        
        # Проверка дубликатов
        if await db.news_exists(news['link']):
            continue
        
        # Предварительный расчет приоритета БЕЗ AI (быстро)
        priority_quick = PriorityCalculator.calculate_priority(news, None)
        
        # AI анализ ТОЛЬКО для потенциально важных новостей
        ai_analysis = None
        if priority_quick >= 6 and ai_requests_count < max_ai_requests_per_cycle:
            try:
                ai_analysis = await ai_analyzer.analyze_text(
                    news['title'] + " " + news['summary']
                )
                ai_requests_count += 1
                if ai_analysis:
                    logger.debug(f"✅ AI анализ выполнен ({ai_requests_count}/{max_ai_requests_per_cycle})")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка AI анализа: {e}")
        
        # Финальный расчет приоритета (с учетом AI если был)
        priority = PriorityCalculator.calculate_priority(news, ai_analysis)
        
        # Фильтруем низкоприоритетные
        if priority < 2:
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

    logger.info(f"📥 RSS: найдено {len(news_list)}, добавлено {count} ({high_priority_count} высокоприоритетных), "
                f"отфильтровано {filtered_count}, AI запросов {ai_requests_count}")
```

---

### Исправление 4: Исправить запуск Userbot

**Файл:** `services/telegram_listener.py`, метод `_load_or_migrate_session()`

**Проблема:** Миграция сессии блокирует выполнение

**Решение:** Исправить логику миграции, убрать блокирующие операции

```python
async def _load_or_migrate_session(self) -> StringSession:
    """Загружает StringSession из переменной окружения или мигрирует файл сессии."""
    
    # 1. Проверяем переменную окружения
    if config.tg_session_string:
        logger.info("✅ Использую StringSession из TG_SESSION_STRING")
        return StringSession(config.tg_session_string)
    
    # 2. Проверяем файл сессии (legacy)
    session_file = Path("anon_session.session")
    if session_file.exists():
        logger.warning("⚠️ ОБНАРУЖЕН ФАЙЛ СЕССИИ (небезопасно!)")
        logger.warning("🔄 Мигрирую в StringSession...")
        
        # Используем sync версию для миграции (быстрее)
        from telethon.sessions import StringSession as SyncStringSession
        from telethon import TelegramClient as SyncTelegramClient
        
        try:
            # Создаем синхронный клиент для миграции
            temp_client = SyncTelegramClient(
                "anon_session",
                config.tg_api_id,
                config.tg_api_hash
            )
            
            # Синхронная миграция
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: temp_client.connect())
            
            if not await loop.run_in_executor(None, lambda: temp_client.is_user_authorized()):
                logger.error("❌ Сессия не авторизована!")
                await loop.run_in_executor(None, lambda: temp_client.disconnect())
                return StringSession()
            
            session_str = temp_client.session.save()
            await loop.run_in_executor(None, lambda: temp_client.disconnect())
            
            logger.info("=" * 60)
            logger.info("📋 СКОПИРУЙТЕ ЭТУ СТРОКУ В .env:")
            logger.info(f"TG_SESSION_STRING={session_str}")
            logger.info("=" * 60)
            logger.warning(f"⚠️ После добавления в .env удалите файл: rm {session_file}")
            
            return StringSession(session_str)
            
        except Exception as e:
            logger.error(f"❌ Ошибка миграции сессии: {e}")
            return StringSession()
    
    # 3. Пустая сессия (первый запуск)
    logger.info("🆕 Создаю новую сессию (потребуется авторизация)")
    return StringSession()
```

**Альтернативное решение (проще):** Просто пропустить миграцию если она не удалась:

```python
async def _load_or_migrate_session(self) -> StringSession:
    if config.tg_session_string:
        return StringSession(config.tg_session_string)
    
    session_file = Path("anon_session.session")
    if session_file.exists():
        logger.warning("⚠️ Обнаружен файл сессии. Используйте TG_SESSION_STRING в .env")
        logger.warning("💡 Для миграции запустите отдельно: python -m services.telegram_listener")
        # Возвращаем пустую сессию, userbot не запустится
        return StringSession()
    
    return StringSession()
```

---

### Исправление 5: Улучшить cleanup при выходе

**Файл:** `main.py`, функция `main()`

```python
async def main():
    """Главная функция с глобальной обработкой ошибок"""
    background_tasks = []  # Отслеживаем задачи
    
    try:
        # ... инициализация ...
        
        # Запуск Userbot
        if config.tg_api_id and config.tg_api_hash:
            logger.info("🎧 Запуск Telegram Userbot...")
            task = asyncio.create_task(safe_start_listener())
            background_tasks.append(task)
        
        # ... остальной код ...
        
        await dp.start_polling(bot)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Получен сигнал остановки (Ctrl+C)")
    
    except Exception as e:
        await critical_error_handler("Критическая ошибка в main()", e)
        sys.exit(1)
    
    finally:
        logger.info("🧹 Очистка ресурсов...")
        
        # Отменяем фоновые задачи
        for task in background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Остановка планировщика
        if scheduler.running:
            scheduler.shutdown(wait=False)
        
        # Остановка Userbot
        if listener.is_running:
            await listener.stop()
        
        # Закрытие бота
        await bot.session.close()
```

---

### Исправление 6: Добавить обработку ошибок для цен и индекса страха

**Файл:** `main.py`, функция `check_queue_and_post()`

```python
# Подготовка данных
ai_data = None
try:
    # ... AI анализ ...
except Exception as e:
    logger.error(f"❌ Ошибка AI обработки: {e}", exc_info=True)

# Получение цен и индекса с обработкой ошибок
try:
    prices = await get_multiple_crypto_prices()
except Exception as e:
    logger.warning(f"⚠️ Ошибка получения цен: {e}")
    prices = None

try:
    fear_greed = await FearGreedIndexTracker.get_fear_greed_index()
except Exception as e:
    logger.warning(f"⚠️ Ошибка получения индекса страха: {e}")
    fear_greed = None
```

---

### Исправление 7: Увеличить интервал Queue Poster

**Проблема:** Queue Poster запускается каждые 30 секунд, что может быть слишком часто

**Решение:** Увеличить до 60 секунд

**Файл:** `main.py`

```python
scheduler.add_job(
    check_queue_and_post,
    IntervalTrigger(seconds=60),  # Было 30, стало 60
    id="queue_poster",
    name="Queue Poster"
)
```

---

## 📊 РЕКОМЕНДАЦИИ

### 1. Мониторинг использования API

Отслеживать:
- Количество AI запросов в день
- Процент успешных/неуспешных запросов
- Время до исчерпания квоты

### 2. Приоритизация AI запросов

Использовать AI анализ только для:
- Новостей с высоким приоритетом по ключевым словам (>= 6)
- Insider новостей из Telegram
- Не более 10-20 запросов за цикл парсинга

### 3. Использование кэширования

Кэшировать результаты AI анализа для похожих новостей

### 4. Альтернативные AI провайдеры

Рассмотреть использование других AI API (Claude, Local LLM) как дополнительные fallback

---

## ✅ ЧЕКЛИСТ ИСПРАВЛЕНИЙ

- [ ] Заменить gemini-2.0-flash-exp на gemini-1.5-flash
- [ ] Добавить retry механизм для 429 ошибок
- [ ] Ограничить количество AI запросов при RSS парсинге
- [ ] Исправить миграцию сессии userbot
- [ ] Улучшить cleanup при выходе
- [ ] Добавить обработку ошибок для цен и индекса страха
- [ ] Увеличить интервал Queue Poster до 60 секунд
- [ ] Добавить логирование статистики RSS парсинга

---

*Анализ выполнен на основе логов от 2025-12-26*
*Выявлено проблем: 8 (3 критических, 5 важных)*

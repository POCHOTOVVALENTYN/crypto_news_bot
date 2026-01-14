# 🔧 Исправление ошибки safe_task декоратора

## ❌ Проблема

```
TypeError: safe_task.<locals>.wrapper() takes 0 positional arguments but 1 was given
```

**Местоположение:** `main.py:140` при использовании `@safe_task("RSS Parsing")`

---

## 🔍 Анализ бага

### Причина ошибки:

Декоратор `safe_task` был реализован неправильно:

1. **Было:** Декоратор ожидал корутину как аргумент (`coro`)
2. **Использование:** `@safe_task("RSS Parsing")` передает строку, а не корутину
3. **Проблема:** Декоратор возвращал функцию `wrapper()` без аргументов, но Python пытался передать функцию как аргумент

### Код до исправления:

```python
def safe_task(coro):
    """Неправильная реализация"""
    async def wrapper():
        try:
            await coro  # Ожидает корутину
        except Exception as e:
            ...
    return wrapper
```

---

## ✅ Исправление

### Что было исправлено:

1. **Декоратор переписан** для правильной работы с именем задачи
2. **Поддержка обоих вариантов использования:**
   - `@safe_task("Task Name")` - с именем задачи
   - `@safe_task` - без имени задачи (будет использовано имя функции)
3. **Добавлен метод `send_alert`** в `AlertManager` (использовался в коде, но не был определен)

### Код после исправления:

```python
def safe_task(task_name=None):
    """
    Декоратор для защиты фоновых задач.
    Ловит исключения, чтобы они не ломали Event Loop.
    
    Использование:
        @safe_task("Task Name")
        async def my_task():
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                pass  # Обычная остановка задачи
            except Exception as e:
                task_display = task_name or func.__name__
                logger.error(f"❌ Ошибка в задаче '{task_display}': {e}", exc_info=True)
                # ... обработка ошибки
        return wrapper
    
    # Если декоратор вызван без скобок (@safe_task), task_name будет функцией
    if callable(task_name):
        # Декоратор использован без аргументов: @safe_task
        func = task_name
        task_name = None
        return decorator(func)
    
    # Декоратор использован с аргументом: @safe_task("Name")
    return decorator
```

---

## 📝 Внесенные изменения

### 1. Файл: `utils/error_handling.py`

**Изменения:**
- ✅ Переписан декоратор `safe_task` для правильной работы
- ✅ Добавлена поддержка использования с/без аргументов
- ✅ Добавлен метод `send_alert` в `AlertManager`
- ✅ Добавлено поле `admin_id` в `AlertManager`

---

## 🎯 Как это работает теперь

### Вариант 1: С именем задачи
```python
@safe_task("RSS Parsing")
async def scheduled_parsing():
    ...
```

### Вариант 2: Без имени задачи
```python
@safe_task
async def my_task():
    ...
```

Оба варианта работают корректно!

---

## ✅ Результат

После исправления:
- ✅ Декоратор работает правильно
- ✅ Ошибка `TypeError` исправлена
- ✅ Бот может запускаться без ошибок
- ✅ Обработка ошибок в задачах работает корректно

---

*Исправление выполнено: $(date)*


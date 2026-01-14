# ✅ Исправление проблемы со статусом Userbot

## Проблема

Race condition: алерт о статусе отправлялся ДО завершения запуска Userbot, поэтому `listener.is_running` был еще `False`.

---

## ✅ Решение

**Файл:** `main.py`, строки 356-362

**Было:**
```python
# 2. Запуск Userbot
if config.tg_api_id and config.tg_api_hash:
    logger.info("🎧 Запуск Telegram Userbot...")
    task = asyncio.create_task(safe_start_listener())
    background_tasks.append(task)
```

**Стало:**
```python
# 2. Запуск Userbot
if config.tg_api_id and config.tg_api_hash:
    logger.info("🎧 Запуск Telegram Userbot...")
    # Ожидаем завершения запуска для правильной проверки статуса
    await safe_start_listener()
```

---

## Объяснение

1. **Раньше:** `create_task()` запускал задачу асинхронно, но не ждал ее завершения
2. **Теперь:** `await` ждет завершения запуска Userbot
3. **Результат:** Когда отправляется алерт, `listener.is_running` уже установлен в `True` (если запуск успешен)

---

## Примечание

Убрана переменная `background_tasks` для userbot, так как теперь мы ожидаем его запуска. Это правильно, потому что:
- Userbot должен запуститься до отправки алерта
- Если userbot не запустится, мы узнаем об этом сразу
- Остальные фоновые задачи (RSS парсинг и т.д.) продолжают работать асинхронно

---

*Исправление применено: $(date)*


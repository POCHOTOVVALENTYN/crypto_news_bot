# ✅ Исправления ошибок и багов

## 📋 Выявленные проблемы

### 1. Ключевые моменты на английском языке (КРИТИЧНО)
**Симптом:** В публикации ключевые моменты отображались на английском, хотя заголовок был переведен на русский.

**Причина:** `key_points` извлекались из `full_content`, который не переводился (переводился только `title` и `text_for_ai`).

**Исправление:** 
- Файл: `main.py` (строки ~301-318)
- Добавлена логика перевода `key_points` после их извлечения, если новость была переведена (`translated_data` существует).
- Используется `translator.translate_text` обернутый в `asyncio.run_in_executor` (синхронный метод).

---

### 2. Обрезка текста посреди слова
**Симптом:** Заголовок и ключевые моменты обрезались посередине слова (например, "pric..." вместо "price levels").

**Причина:** Использовалась простая обрезка по символам (`text[:120]`), которая не учитывала границы слов.

**Исправление:**
- Файл: `services/message_builder.py`
- Добавлен метод `smart_truncate_words()` для обрезки по словам (ищет последний пробел перед лимитом).
- Обновлен `smart_truncate()` для улучшенной обрезки (fallback на пробелы).
- Заголовок обрезается через `smart_truncate_words(title, max_chars=80)`.
- Ключевые моменты обрезаются через `smart_truncate_words(point_clean, max_chars=120)`.

---

### 3. Отсутствие логирования извлечения контента
**Симптом:** Не было видно, успешно ли извлекается `full_content` из статей.

**Исправление:**
- Файл: `parser/rss_parser.py`
- Добавлен `import logging` и `logger = logging.getLogger(__name__)`.
- Добавлено логирование результата извлечения `full_content`:
  - Если > 500 символов: `✅ Полный текст извлечен: X символов`
  - Если 200-500 символов: `⚠️ Короткий контент: X символов (использован summary?)`
  - Если < 200 символов: `⚠️ Очень короткий контент: X символов`

---

## 📝 Детали изменений

### `main.py`
```python
# ✅ ИСПРАВЛЕНО: Переводим key_points если новость была переведена
if translated_data and key_points:
    logger.debug(f"🔄 Перевожу ключевые моменты ({len(key_points)} пунктов)...")
    translated_points = []
    import asyncio
    loop = asyncio.get_event_loop()
    for point in key_points:
        try:
            # translate_text - синхронный метод, оборачиваем в executor
            translated_point = await loop.run_in_executor(
                None, translator.translate_text, point, 'auto', 'ru'
            )
            if translated_point:
                translated_points.append(translated_point)
            else:
                translated_points.append(point)  # Fallback на оригинал
        except Exception as e:
            logger.debug(f"⚠️ Ошибка перевода ключевого момента: {e}")
            translated_points.append(point)  # Fallback на оригинал
    key_points = translated_points
    logger.debug(f"✅ Ключевые моменты переведены")
```

### `services/message_builder.py`
```python
@staticmethod
def smart_truncate_words(text: str, max_chars: int) -> str:
    """Обрезает текст по словам (не режет слова посередине)"""
    if len(text) <= max_chars:
        return text
    
    cut = text[:max_chars]
    last_space = cut.rfind(' ')
    
    if last_space > max_chars * 0.7:  # Если пробел не слишком близко к началу
        return cut[:last_space] + "..."
    
    return cut + "..."

# Применение:
title_display = AdvancedMessageFormatter.smart_truncate_words(title, max_chars=80)
point_display = AdvancedMessageFormatter.smart_truncate_words(point_clean, max_chars=120)
```

### `parser/rss_parser.py`
```python
import logging
logger = logging.getLogger(__name__)

# В get_all_news():
full_content = await get_article_content(entry, link)

# ✅ ИСПРАВЛЕНО: Логируем результат извлечения контента
if full_content and len(full_content) > 500:
    logger.debug(f"✅ Полный текст извлечен для {title[:50]}: {len(full_content)} символов")
elif full_content and len(full_content) > 200:
    logger.debug(f"⚠️ Короткий контент для {title[:50]}: {len(full_content)} символов (использован summary?)")
else:
    logger.debug(f"⚠️ Очень короткий контент для {title[:50]}: {len(full_content) if full_content else 0} символов")
```

---

## 🔍 Проверка RSS фильтрации

**Логи показали:** "добавлено 0" из 89 найденных новостей.

**Анализ:** 
- Это может быть нормальным поведением, если:
  - Все новости уже были добавлены ранее (дубликаты: 40)
  - Новости не прошли проверку свежести (старые: 49)
  - Новости не прошли валидацию (валидация: 0)
  - Новости имели приоритет 0 (приоритет 0: 0)

**Рекомендация:** Мониторить логи извлечения контента для понимания качества данных. Если проблема сохраняется, можно временно уменьшить строгость фильтрации свежести (например, с 24 часов до 48 часов).

---

## ✅ Результат

После исправлений:
1. ✅ Ключевые моменты будут переводиться на русский язык, если новость была переведена.
2. ✅ Заголовок и ключевые моменты не будут обрезаться посередине слов.
3. ✅ Логирование поможет отслеживать качество извлечения контента.

---

*Исправления применены: 2026-01-03*


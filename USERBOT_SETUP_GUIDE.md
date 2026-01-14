# 📱 Инструкция по настройке Userbot

## 🎯 Что такое Userbot?

Userbot - это компонент бота, который мониторит Telegram каналы как обычный пользователь и собирает важные инсайды.

---

## 📋 Предварительные требования

1. **Telegram API credentials:**
   - `TG_API_ID` - получить на https://my.telegram.org
   - `TG_API_HASH` - получить на https://my.telegram.org

2. **Сессия Telegram:**
   - Нужна строка сессии (StringSession)
   - Получается один раз через интерактивную авторизацию

---

## 🔧 Пошаговая настройка

### ШАГ 1: Получите API credentials

1. Перейдите на https://my.telegram.org
2. Войдите с вашим номером телефона
3. Перейдите в "API development tools"
4. Создайте приложение (любое название)
5. Скопируйте:
   - `api_id` → это ваш `TG_API_ID`
   - `api_hash` → это ваш `TG_API_HASH`

### ШАГ 2: Добавьте credentials в .env

```bash
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890abcdef1234567890
```

### ШАГ 3: Создайте сессию

Выполните команду для создания сессии:

```bash
python -c "from services.telegram_listener import setup_userbot; import asyncio; asyncio.run(setup_userbot())"
```

**Что произойдет:**
1. Вам будет предложено ввести номер телефона (в формате +380635609097)
2. Вам будет отправлен код в Telegram
3. Введите код
4. Если включена 2FA - введите пароль
5. Вы получите строку `TG_SESSION_STRING`

### ШАГ 4: Добавьте сессию в .env

Скопируйте строку `TG_SESSION_STRING` из вывода команды и добавьте в `.env`:

```bash
TG_SESSION_STRING=1BVtsOHwBu5Q7v...
```

### ШАГ 5: Настройте каналы для мониторинга

В `.env` добавьте:

```bash
SOURCE_CHANNELS=@WalterBloomberg,@RBCCrypto,@Defiscamcheck,@drops_daily,@crypttwitter
```

**Важно:** Каналы должны быть доступны вашему аккаунту (вы должны быть подписаны)

### ШАГ 6: Перезапустите бота

```bash
python main.py
```

---

## ⚠️ Возможные проблемы

### Проблема 1: "Сессия не авторизована"

**Решение:**
- Проверьте что `TG_SESSION_STRING` скопирован правильно (полностью, без пробелов)
- Создайте сессию заново (ШАГ 3)

### Проблема 2: "Не удалось подключиться к каналу"

**Решение:**
- Убедитесь что вы подписаны на канал
- Проверьте правильность имени канала (с @ или без)
- Попробуйте использовать username канала

### Проблема 3: "Требуется 2FA пароль"

**Решение:**
- Включите 2FA в настройках Telegram
- При создании сессии введите пароль 2FA
- Или отключите 2FA (не рекомендуется)

### Проблема 4: "3 consecutive sign-in attempts failed"

**Решение:**
- Это означает что сессия не валидна или истекла
- Создайте новую сессию (ШАГ 3)
- Обновите `TG_SESSION_STRING` в .env

---

## 📝 Пример полного .env файла

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TELEGRAM_CHANNEL_ID=-1001234567890
ADMIN_ID=830196453

# AI Providers
GEMINI_API_KEY=AIza...
OPENAI_API_KEY=sk-...

# Userbot
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890abcdef1234567890
TG_SESSION_STRING=1BVtsOHwBu5Q7v...
SOURCE_CHANNELS=@WalterBloomberg,@RBCCrypto,@Defiscamcheck

# Settings
LOG_LEVEL=INFO
```

---

## 🔒 Безопасность

⚠️ **ВАЖНО:**
- `TG_SESSION_STRING` - это как пароль от вашего Telegram аккаунта
- НЕ публикуйте его в открытом доступе
- НЕ добавляйте в git (должен быть в .gitignore)
- Храните в безопасности

---

*Инструкция создана: $(date)*


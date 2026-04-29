# ✅ Чеклист развёртывания Webhook версии

## До развёртывания

- [ ] Прочитай WEBHOOK_MIGRATION.md
- [ ] Убедись что используешь Railway
- [ ] Есть доступ к Railway Project Settings
- [ ] Знаешь свой MAX_BOT_TOKEN
- [ ] Знаешь свой MAX_ADMIN_USER_ID

## Шаг 1: Коммит кода

```bash
cd /Users/denispostnikov/Desktop/Клод/max_secretary_bot

# Проверить изменения
git status

# Закоммитить
git add -A
git commit -m "Migrate to webhooks instead of long polling

- Replace polling with FastAPI webhook server
- Add webhook registration in Max API
- Update requirements with fastapi, uvicorn, aiohttp
- Add WEBHOOK_SECRET for request verification"

# Отправить на Railway
git push railway main
```

## Шаг 2: Развёртывание на Railway

1. **Открой Railway Dashboard:**
   - https://railway.app/dashboard

2. **Выбери проект:**
   - `max-secretary-bot`

3. **Жди развёртывания:**
   - Статус должен стать "Success" (зелёная галочка)
   - Это займёт 2-5 минут

4. **Проверь логи:**
   - Deployments → Latest → View Logs
   - Должны быть логи вроде:
     ```
     ✅ Webhook успешно зарегистрирован: https://...
     ```

## Шаг 3: Получить Domain и обновить WEBHOOK_URL

1. **В Railway Dashboard:**
   - Выбери `max-secretary-bot` проект
   - Перейди на вкладку Settings
   - Найди Domain (вроде `max-bot-production-abc123.railway.app`)

2. **Скопируй это значение:**
   ```
   https://max-bot-production-abc123.railway.app
   ```

3. **Обновить переменную WEBHOOK_URL:**
   - Settings → Variables
   - Найди `WEBHOOK_URL`
   - Установи значение:
     ```
     https://max-bot-production-abc123.railway.app/webhook
     ```
   - Сохрани (Save)

4. **Перезапусти приложение:**
   - Deployments → Redeploy latest

## Шаг 4: Проверка

1. **Проверить здоровье:**
   ```
   curl https://YOUR_DOMAIN/health
   ```
   Должен вернуть:
   ```json
   {"status": "ok", "service": "max-secretary-bot"}
   ```

2. **Проверить логи:**
   ```
   Deployments → View Logs
   ```
   Должны быть логи типа:
   ```
   🚀 MAX БОТ-СЕКРЕТАРЬ (Webhook версия)
   ✅ Webhook готов: https://...
   ```

3. **Отправить тестовое сообщение:**
   - Открой чат с ботом в Max
   - Отправь `/start`
   - Должно придти приветствие с кнопками

## Шаг 5: Finalize

- [ ] Webhook зарегистрирован в Max API (в логах ✅)
- [ ] /health возвращает 200 OK
- [ ] Бот отвечает на команды в чате Max
- [ ] Нет ошибок в логах

## Готово! 🚀

Бот теперь работает на **webhooks** вместо long polling!

## Если что-то не сработало

1. **Проверить логи:**
   ```bash
   Railway Deployments → View Logs
   ```

2. **Проверить переменные окружения:**
   ```bash
   Railway Settings → Variables
   - MAX_BOT_TOKEN (должен быть установлен)
   - MAX_ADMIN_USER_ID (должен быть установлен)
   - WEBHOOK_URL (должен быть https://...)
   - WEBHOOK_SECRET (может быть любая строка)
   ```

3. **Проверить что деплой успешный:**
   ```bash
   Railway Deployments → Статус должен быть "Success"
   ```

4. **Перезапустить приложение:**
   ```bash
   Railway Deployments → Redeploy latest
   ```

## Откат (если критичные проблемы)

```bash
git log                    # Найти предыдущий коммит
git revert HEAD            # Откатить последний коммит
git push railway main      # Отправить на Railway
```

Railway автоматически перестроит приложение на старую версию.

---

**Вопросы?** Проверь WEBHOOK_MIGRATION.md или логи Railway.

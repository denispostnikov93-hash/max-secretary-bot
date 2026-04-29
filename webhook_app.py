"""
Max бот-секретарь - Webhook версия (вместо long polling)
Использует FastAPI для получения событий от Max API
"""
import logging
import json
import hmac
import hashlib
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import aiohttp

from config import MAX_BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PORT, WEBHOOK_SECRET, MAX_ADMIN_USER_ID
from database import db
from max_bot import (
    bot, send_admin_message, send_start_message,
    make_keyboard, validate_phone, parse_category_and_description,
    user_data, user_states
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Max Secretary Bot")

admin_id = int(MAX_ADMIN_USER_ID) if isinstance(MAX_ADMIN_USER_ID, str) else MAX_ADMIN_USER_ID

# ===== WEBHOOK РЕГИСТРАЦИЯ =====

async def register_webhook():
    """Регистрировать webhook URL в Max API"""
    try:
        logger.info(f"📝 Регистрирую webhook: {WEBHOOK_URL}")

        async with aiohttp.ClientSession() as session:
            # Сначала получим список существующих подписок
            async with session.get(
                "https://platform-api.max.ru/subscriptions",
                headers={"Authorization": MAX_BOT_TOKEN}
            ) as resp:
                if resp.status == 200:
                    subs = await resp.json()
                    logger.info(f"📋 Существующие подписки: {subs}")

                    # Если уже есть подписка на тот же URL, пропускаем
                    if subs.get("data"):
                        for sub in subs["data"]:
                            if sub.get("url") == WEBHOOK_URL:
                                logger.info(f"✓ Webhook уже зарегистрирован: {WEBHOOK_URL}")
                                return True

            # Регистрируем новый webhook
            payload = {
                "url": WEBHOOK_URL,
                "secret": WEBHOOK_SECRET
            }

            async with session.post(
                "https://platform-api.max.ru/subscriptions",
                headers={"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"},
                json=payload
            ) as resp:
                logger.info(f"📤 POST /subscriptions статус: {resp.status}")
                result = await resp.json()
                logger.info(f"📝 Ответ: {result}")

                if resp.status in [200, 201]:
                    logger.info(f"✅ Webhook успешно зарегистрирован: {WEBHOOK_URL}")
                    return True
                else:
                    logger.error(f"❌ Ошибка регистрации webhook: {result}")
                    return False

    except Exception as e:
        logger.error(f"❌ Ошибка при регистрации webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def unregister_webhook():
    """Удалить webhook из Max API"""
    try:
        logger.info(f"🗑️ Удаляю webhook: {WEBHOOK_URL}")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://platform-api.max.ru/subscriptions",
                headers={"Authorization": MAX_BOT_TOKEN}
            ) as resp:
                if resp.status == 200:
                    subs = await resp.json()

                    if subs.get("data"):
                        for sub in subs["data"]:
                            if sub.get("url") == WEBHOOK_URL:
                                sub_id = sub.get("id")

                                # Удаляем подписку
                                async with session.delete(
                                    f"https://platform-api.max.ru/subscriptions/{sub_id}",
                                    headers={"Authorization": MAX_BOT_TOKEN}
                                ) as del_resp:
                                    if del_resp.status in [200, 204]:
                                        logger.info(f"✅ Webhook удалён")
                                        return True

        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при удалении webhook: {e}")
        return False


def verify_webhook_signature(data: bytes, signature: str) -> bool:
    """Проверить подпись webhook"""
    expected_signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        data,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


# ===== WEBHOOK ENDPOINT =====

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Обработчик webhook событий от Max API"""
    try:
        # Получаем тело запроса
        body = await request.body()

        # Проверяем сигнатуру
        signature = request.headers.get("X-Max-Bot-Api-Signature", "")
        if not verify_webhook_signature(body, signature):
            logger.warning("⚠️ Неверная сигнатура webhook")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Парсим JSON
        event = json.loads(body)
        logger.info(f"📨 Webhook событие: {event.get('event_type', 'unknown')}")

        # Обрабатываем события
        await process_webhook_event(event)

        # Возвращаем 200 OK за 30 секунд
        return JSONResponse({"status": "ok"})

    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


async def process_webhook_event(event: dict):
    """Обработать событие webhook"""
    event_type = event.get("event_type")
    data = event.get("data", {})

    logger.info(f"🔄 Обработка события: {event_type}")

    try:
        if event_type == "message_created":
            await handle_webhook_message(data)
        elif event_type == "message_callback":
            await handle_webhook_callback(data)
        elif event_type == "bot_started":
            await handle_webhook_bot_started(data)
        elif event_type == "dialog_cleared":
            await handle_webhook_dialog_cleared(data)
        else:
            logger.warning(f"⚠️ Неизвестный тип события: {event_type}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки события {event_type}: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def handle_webhook_message(data: dict):
    """Обработать message_created событие"""
    try:
        message = data.get("message", {})
        sender_id = str(message.get("sender", {}).get("user_id"))
        text = message.get("text", "")

        logger.info(f"📨 Сообщение от {sender_id}: {text[:50]}...")

        # Проверяем команды
        if text == "/start":
            await send_start_message(sender_id)
        elif text == "/my_id":
            await bot.send_message(chat_id=sender_id, text=f"ℹ️ Ваш Max ID: `{sender_id}`")
        else:
            # Обработка как обычное сообщение для заявки
            await handle_webhook_application_message(sender_id, text, message)

    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")


async def handle_webhook_callback(data: dict):
    """Обработать message_callback событие"""
    try:
        callback = data.get("callback", {})
        user_id = str(callback.get("user_id"))
        payload = callback.get("payload")

        logger.info(f"🔘 Callback от {user_id}: {payload}")

        # Обработка callbacks (кнопки)
        if payload == "record":
            await handle_record_button(user_id)
        elif payload == "help":
            await handle_help_button(user_id)
        elif payload == "agree_all":
            await handle_agree_all(user_id)
        elif payload == "refuse":
            await handle_refuse_button(user_id)
        elif payload in ["individual", "company"]:
            await handle_client_type(user_id, payload)

    except Exception as e:
        logger.error(f"❌ Ошибка обработки callback: {e}")


async def handle_webhook_bot_started(data: dict):
    """Обработать bot_started событие"""
    try:
        user_id = str(data.get("user_id"))
        chat_id = data.get("chat_id")

        logger.info(f"🟢 Bot started: user_id={user_id}, chat_id={chat_id}")
        await send_start_message(user_id)

    except Exception as e:
        logger.error(f"❌ Ошибка обработки bot_started: {e}")


async def handle_webhook_dialog_cleared(data: dict):
    """Обработать dialog_cleared событие"""
    try:
        user_id = str(data.get("user_id"))

        logger.info(f"🗑️ Dialog cleared: user_id={user_id}")

        # Очищаем данные пользователя
        if user_id in user_data:
            del user_data[user_id]
        if user_id in user_states:
            del user_states[user_id]

    except Exception as e:
        logger.error(f"❌ Ошибка обработки dialog_cleared: {e}")


# ===== ОБРАБОТЧИКИ КНОПОК И СООБЩЕНИЙ =====

async def handle_record_button(user_id: str):
    """Кнопка 'Записаться'"""
    logger.info(f"📝 Нажата кнопка Записаться от {user_id}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }
    user_states[user_id] = "consent"

    text = "📋 Перед записью на консультацию, пожалуйста:\n\n1️⃣ Ознакомьтесь с Политикой конфиденциальности\n2️⃣ Согласитесь с Условиями обслуживания"

    await bot.send_message(
        chat_id=user_id,
        text=text,
        attachments=make_keyboard(
            ("📄 Политика", "policy"),
            ("📋 Условия", "agreement"),
            ("✅ Согласиться", "agree_all"),
            ("❌ Отказать", "refuse")
        )
    )


async def handle_help_button(user_id: str):
    """Кнопка 'Позвонить'"""
    logger.info(f"☎️ Нажата кнопка Позвонить от {user_id}")

    text = "☎️ **Свяжитесь с нами по телефону:**\n\n📞 +7 (985) 999-85-89\n\n⏰ Режим работы:\nПн-Пт: 09:00 - 20:00\nСб-Вс: 10:00 - 18:00"

    await bot.send_message(chat_id=user_id, text=text)


async def handle_agree_all(user_id: str):
    """Согласие со всеми условиями"""
    logger.info(f"✅ Согласие от {user_id}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }

    user_data[user_id]['consent_pd'] = True
    user_data[user_id]['consent_policy'] = True
    user_states[user_id] = "client_type"

    text = "👤 Выберите, как вас классифицировать:"

    await bot.send_message(
        chat_id=user_id,
        text=text,
        attachments=make_keyboard(
            ("👤 Физическое лицо", "individual"),
            ("🏢 Юридическое лицо", "company")
        )
    )


async def handle_refuse_button(user_id: str):
    """Отказ от условий"""
    logger.info(f"❌ Отказ от {user_id}")

    text = "❌ Вы отказались от условий. Для записи на консультацию необходимо согласиться с политикой конфиденциальности и условиями обслуживания.\n\nМожете попробовать снова."

    await bot.send_message(
        chat_id=user_id,
        text=text,
        attachments=make_keyboard(("📝 Записаться заново", "record"))
    )

    user_states[user_id] = "menu"


async def handle_client_type(user_id: str, client_type_key: str):
    """Выбор типа клиента"""
    client_type = "Физическое лицо" if client_type_key == "individual" else "Юридическое лицо"

    logger.info(f"🏢 Выбран тип клиента {client_type} от {user_id}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }

    user_data[user_id]['client_type'] = client_type
    user_states[user_id] = "waiting_name"

    text = f"✅ Вы выбрали: {client_type}\n\n📝 Введите ваше имя (или название компании):"

    await bot.send_message(chat_id=user_id, text=text)


async def handle_webhook_application_message(user_id: str, text: str, message: dict):
    """Обработка сообщения для заявки"""
    if user_id not in user_data:
        await send_start_message(user_id)
        return

    state = user_states.get(user_id, "menu")

    logger.info(f"🔄 Обработка сообщения от {user_id}, состояние: {state}")

    if state == "waiting_name":
        user_data[user_id]['name'] = text
        user_states[user_id] = "waiting_phone"

        text_resp = "📞 Спасибо! Введите ваш номер телефона:"
        await bot.send_message(chat_id=user_id, text=text_resp)

    elif state == "waiting_phone":
        if not validate_phone(text):
            await bot.send_message(chat_id=user_id, text="❌ Некорректный номер телефона. Попробуйте снова.")
            return

        user_data[user_id]['phone'] = text
        user_states[user_id] = "waiting_description"

        client_type = user_data[user_id].get('client_type', 'Клиент')
        text_resp = f"📋 Спасибо, {user_data[user_id]['name']}!\n\nОпишите кратко вашу проблему или вопрос:"

        await bot.send_message(chat_id=user_id, text=text_resp)

    elif state == "waiting_description":
        category, description = parse_category_and_description(text, user_data[user_id].get('client_type', ''))

        user_data[user_id]['category'] = category
        user_data[user_id]['description'] = description
        user_states[user_id] = "completed"

        # Отправляем заявку админу
        admin_text = f"""
📋 **НОВАЯ ЗАЯВКА**

👤 Имя: {user_data[user_id]['name']}
📱 Телефон: {user_data[user_id]['phone']}
👨‍⚖️ Тип клиента: {user_data[user_id]['client_type']}
📌 Категория: {category}
📝 Описание: {description}

👤 Max ID: {user_id}
⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""

        await send_admin_message(admin_text)

        text_resp = "✅ Спасибо за заявку! Мы свяжемся с вами в ближайшее время."
        await bot.send_message(chat_id=user_id, text=text_resp)


# ===== ЗДОРОВЬЕ И ИНИЦИАЛИЗАЦИЯ =====

@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    return {"status": "ok", "service": "max-secretary-bot"}


@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    logger.info("=" * 60)
    logger.info("🚀 MAX БОТ-СЕКРЕТАРЬ (Webhook версия)")
    logger.info("=" * 60)

    logger.info("📦 Инициализирую БД...")
    await db.init()
    logger.info("✓ БД готова")

    logger.info("📝 Регистрирую webhook...")
    webhook_registered = await register_webhook()

    if webhook_registered:
        logger.info(f"✅ Webhook готов: {WEBHOOK_URL}")
    else:
        logger.warning("⚠️ Проблема с регистрацией webhook")

    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при остановке"""
    logger.info("⏹️ Бот останавливается...")
    await unregister_webhook()
    logger.info("✅ Бот остановлен")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WEBHOOK_PORT)

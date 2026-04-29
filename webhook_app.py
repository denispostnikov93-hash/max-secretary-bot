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

from config import MAX_BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PORT, WEBHOOK_SECRET, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
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
        logger.info(f"📝 Secret (первые 20 символов): {WEBHOOK_SECRET[:20]}")

        async with aiohttp.ClientSession() as session:
            # Получим список существующих подписок
            async with session.get(
                "https://platform-api.max.ru/subscriptions",
                headers={"Authorization": MAX_BOT_TOKEN}
            ) as resp:
                if resp.status == 200:
                    subs = await resp.json()
                    logger.info(f"📋 Существующие подписки: {subs}")

                    subscriptions = subs.get("subscriptions", [])

                    # УДАЛЯЕМ ВСЕ webhook подписки (старые secret может быть другой!)
                    for sub in subscriptions:
                        sub_url = sub.get("url", "")
                        sub_id = sub.get("id")

                        if sub_url and "webhook" in sub_url:
                            logger.info(f"🗑️ Удаляю подписку: {sub_url}")
                            async with session.delete(
                                f"https://platform-api.max.ru/subscriptions/{sub_id}",
                                headers={"Authorization": MAX_BOT_TOKEN}
                            ) as del_resp:
                                logger.info(f"  Статус: {del_resp.status}")

            # Регистрируем новый webhook с текущим secret
            payload = {
                "url": WEBHOOK_URL,
                "secret": WEBHOOK_SECRET
            }
            logger.info(f"📤 Отправляю новую подписку...")

            async with session.post(
                "https://platform-api.max.ru/subscriptions",
                headers={"Authorization": MAX_BOT_TOKEN, "Content-Type": "application/json"},
                json=payload
            ) as resp:
                logger.info(f"📤 POST /subscriptions статус: {resp.status}")
                result = await resp.json()
                logger.info(f"📝 Ответ: {result}")

                if resp.status in [200, 201]:
                    logger.info(f"✅ Webhook успешно зарегистрирован с НОВЫМ secret: {WEBHOOK_URL}")
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
                    subscriptions = subs.get("subscriptions", [])

                    for sub in subscriptions:
                        if sub.get("url") == WEBHOOK_URL:
                            sub_id = sub.get("id")
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

    # Логирование для отладки
    match = hmac.compare_digest(signature, expected_signature)
    logger.debug(f"🔐 Подпись проверка: expected={expected_signature[:16]}... received={signature[:16]}...")
    if not match:
        logger.warning(f"⚠️ Сигнатуры не совпадают!")
        logger.warning(f"  Ожидаем: {expected_signature}")
        logger.warning(f"  Получили: {signature}")
        logger.warning(f"  Secret (first 20): {WEBHOOK_SECRET[:20]}")
        logger.warning(f"  Body length: {len(data)}")

    return match


# ===== WEBHOOK ENDPOINT =====

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Обработчик webhook событий от Max API"""
    try:
        # Получаем тело запроса
        body = await request.body()

        # Логируем входящие данные для отладки
        logger.info(f"📨 Webhook запрос получен")
        logger.info(f"  Content-Type: {request.headers.get('content-type', 'not set')}")
        logger.info(f"  Body (первые 100 символов): {body[:100]}")

        # Логируем ВСЕ заголовки для отладки
        logger.info(f"  Заголовки: {dict(request.headers)}")

        # TODO: Max API не отправляет X-Max-Bot-Api-Signature
        # Временно отключаем проверку сигнатуры
        # signature = request.headers.get("X-Max-Bot-Api-Signature", "")
        # if not verify_webhook_signature(body, signature):
        #     logger.warning("⚠️ Неверная сигнатура webhook - ОТКЛОНЯЕМ СОБЫТИЕ")
        #     raise HTTPException(status_code=401, detail="Invalid signature")

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
    logger.info(f"📋 Структура события: {list(event.keys())}")

    try:
        # Определяем тип события по структуре (Max не присылает event_type)
        # Callback имеет приоритет, так как может быть в одном событии с message
        if "callback" in event:
            logger.info(f"🔄 Тип события: message_callback")
            await handle_webhook_callback(event)
        elif "message" in event:
            logger.info(f"🔄 Тип события: message_created")
            await handle_webhook_message(event)
        elif "user" in event and "chat_id" in event:
            logger.info(f"🔄 Тип события: bot_started")
            await handle_webhook_bot_started(event)
        else:
            logger.warning(f"⚠️ Неизвестный тип события. Структура: {list(event.keys())}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки события: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def handle_webhook_message(event: dict):
    """Обработать message_created событие"""
    try:
        message = event.get("message", {})
        logger.info(f"📨 DEBUG message content: {json.dumps(message, ensure_ascii=False)}")

        recipient = message.get("recipient", {})

        # В Max API нужно использовать dialog chat_id, не user_id!
        chat_id = str(recipient.get("chat_id", ""))
        user_id = str(recipient.get("user_id", ""))
        text = message.get("text", "")

        logger.info(f"📨 Сообщение от user_id={user_id}, chat_id={chat_id}: {text[:50] if text else '(пусто)'}...")

        if not chat_id:
            logger.warning(f"⚠️ Нет chat_id в сообщении")
            return

        # Проверяем команды
        if text == "/start":
            await send_start_message(chat_id)
        elif text == "/my_id":
            await bot.send_message(chat_id=chat_id, text=f"ℹ️ Ваш Max ID: `{user_id}`")
        else:
            # Обработка как обычное сообщение для заявки
            await handle_webhook_application_message(chat_id, text, message, user_id)

    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def handle_webhook_callback(event: dict):
    """Обработать message_callback событие"""
    try:
        callback = event.get("callback", {})
        message = event.get("message", {})
        recipient = message.get("recipient", {})

        # user_id может быть в callback или в message.recipient
        user_id = str(callback.get("user_id", "") or recipient.get("user_id", ""))
        chat_id = str(recipient.get("chat_id", ""))
        payload = callback.get("payload")

        if not user_id or not chat_id:
            logger.warning(f"⚠️ Нет user_id или chat_id в callback. callback={callback}, recipient={recipient}")
            return

        logger.info(f"🔘 Callback от user_id={user_id}, chat_id={chat_id}: {payload}")

        # Инициализируем user_data если нужно (используем chat_id как ключ)
        if chat_id not in user_data:
            user_data[chat_id] = {
                'consent_pd': False, 'consent_policy': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
            }

        # Главное меню
        if payload == "record":
            user_states[chat_id] = "consent"
            msg = (
                f"📋 Подтвердите два согласия:\n\n"
                f"📄 Политика обработки данных:\n{PRIVACY_POLICY_URL}\n\n"
                f"📄 Согласие на обработку ПД:\n{AGREEMENT_URL}"
            )
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                attachments=make_keyboard(
                    ("✅ Согласен на обработку ПД", "consent_pd"),
                    ("✅ Ознакомлен с политикой", "consent_policy"),
                    ("❌ Отказать", "refuse")
                )
            )
        elif payload == "help":
            await bot.send_message(chat_id=chat_id, text="☎️ Позвоните нам: 8-495-999-85-89")

        # Согласия
        elif payload == "consent_pd":
            user_data[chat_id]['consent_pd'] = True
            await bot.send_message(chat_id=chat_id, text="✅ Согласие на обработку ПД получено!")
            if user_data[chat_id]['consent_policy']:
                await ask_client_type(chat_id, user_id)
        elif payload == "consent_policy":
            user_data[chat_id]['consent_policy'] = True
            await bot.send_message(chat_id=chat_id, text="✅ Вы ознакомлены с политикой!")
            if user_data[chat_id]['consent_pd']:
                await ask_client_type(chat_id, user_id)
        elif payload == "refuse":
            await send_refusal_notification(user_id)
            user_states[chat_id] = "consent_retry"
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "😔 Мы уважаем ваше решение.\n\n"
                    "Однако по закону мы не можем продолжить прием заявки в данном формате без согласия на обработку персональных данных.\n\n"
                    "Это не означает, что мы не можем помочь вам! Есть несколько вариантов:\n\n"
                    "☎️ Позвоните нам: 8-495-999-85-89\n\n"
                    "Или дайте согласие и оставьте заявку через этот формат:"
                ),
                attachments=make_keyboard(("✅ Дать согласие и оставить заявку", "back_consent"))
            )
        elif payload == "back_consent":
            user_data[chat_id] = {
                'consent_pd': False, 'consent_policy': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
            }
            user_states[chat_id] = "consent"
            msg = (
                f"📋 Подтвердите два согласия:\n\n"
                f"📄 Политика обработки данных:\n{PRIVACY_POLICY_URL}\n\n"
                f"📄 Согласие на обработку ПД:\n{AGREEMENT_URL}"
            )
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                attachments=make_keyboard(
                    ("✅ Согласен на обработку ПД", "consent_pd"),
                    ("✅ Ознакомлен с политикой", "consent_policy"),
                    ("❌ Отказать", "refuse")
                )
            )

        # Выбор типа клиента
        elif payload == "physical":
            user_data[chat_id]['client_type'] = "Физическое лицо"
            user_states[chat_id] = "category_and_desc"
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "Напишите категорию вопроса и кратко опишите ситуацию:\n\n"
                    "Категории для физических лиц:\n"
                    "• ДТП\n"
                    "• Семейное право\n"
                    "• Недвижимость\n"
                    "• Трудовые споры\n"
                    "• Другое\n\n"
                    "Пример: \"ДТП. Со мной произошло ДТП на перекрёстке\""
                )
            )
        elif payload == "legal":
            user_data[chat_id]['client_type'] = "Юридическое лицо"
            user_states[chat_id] = "category_and_desc"
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "Напишите категорию вопроса и кратко опишите ситуацию:\n\n"
                    "Категории для юридических лиц:\n"
                    "• Регистрация бизнеса\n"
                    "• Договоры и споры\n"
                    "• Трудовые вопросы\n"
                    "• Налоги и штрафы\n"
                    "• Другое\n\n"
                    "Пример: \"Регистрация бизнеса. Нужно помочь с регистрацией ООО\""
                )
            )

    except Exception as e:
        logger.error(f"❌ Ошибка обработки callback: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def handle_webhook_bot_started(event: dict):
    """Обработать bot_started событие"""
    try:
        # Max отправляет: {"chat_id": ..., "user": {"user_id": ..., ...}}
        user_data_obj = event.get("user", {})
        user_id = str(user_data_obj.get("user_id", ""))
        chat_id = str(event.get("chat_id", ""))

        if not chat_id:
            logger.warning(f"⚠️ Нет chat_id в bot_started")
            return

        logger.info(f"🟢 Bot started: user_id={user_id}, chat_id={chat_id}")
        await send_start_message(chat_id)

    except Exception as e:
        logger.error(f"❌ Ошибка обработки bot_started: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def handle_webhook_dialog_cleared(data: dict):
    """Обработать dialog_cleared событие"""
    try:
        user_id = str(data.get("user_id"))

        logger.info(f"🗑️ Dialog cleared: user_id={user_id}")

        # Очищаем данные пользователя
        if user_id in user_data:
            del user_data[chat_id]
        if user_id in user_states:
            del user_states[chat_id]

    except Exception as e:
        logger.error(f"❌ Ошибка обработки dialog_cleared: {e}")


# ===== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ =====

async def ask_client_type(chat_id: str, user_id: str):
    """Спросить тип клиента после получения обоих согласий"""
    user_states[chat_id] = "client_type"
    await bot.send_message(
        chat_id=chat_id,
        text="✅ Спасибо! Теперь выберите тип клиента:",
        attachments=make_keyboard(
            ("👤 Физическое лицо", "physical"),
            ("🏢 Юридическое лицо", "legal")
        )
    )


async def send_refusal_notification(user_id: str):
    """Отправить админу уведомление об отказе пользователя"""
    try:
        logger.info(f"📋 Создание уведомления об отказе для {user_id}")
        message = (
            f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
            f"{'━' * 40}\n"
            f"Пользователь отказал в согласии на обработку ПД\n"
            f"👤 Профиль: https://web.max.ru/{user_id}\n"
            f"📲 Источник: Max\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"{'━' * 40}"
        )
        logger.info(f"📤 Отправляю уведомление об отказе")
        await send_admin_message(message)
    except Exception as e:
        logger.error(f"✗ ОШИБКА отправки уведомления об отказе: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ===== ОБРАБОТЧИКИ КНОПОК И СООБЩЕНИЙ =====

async def handle_record_button(user_id: str):
    """Кнопка 'Записаться'"""
    logger.info(f"📝 Нажата кнопка Записаться от {user_id}")

    if user_id not in user_data:
        user_data[chat_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }
    user_states[chat_id] = "consent"

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
        user_data[chat_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }

    user_data[chat_id]['consent_pd'] = True
    user_data[chat_id]['consent_policy'] = True
    user_states[chat_id] = "client_type"

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

    user_states[chat_id] = "menu"


async def handle_client_type(user_id: str, client_type_key: str):
    """Выбор типа клиента"""
    client_type = "Физическое лицо" if client_type_key == "individual" else "Юридическое лицо"

    logger.info(f"🏢 Выбран тип клиента {client_type} от {user_id}")

    if user_id not in user_data:
        user_data[chat_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }

    user_data[chat_id]['client_type'] = client_type
    user_states[chat_id] = "waiting_name"

    text = f"✅ Вы выбрали: {client_type}\n\n📝 Введите ваше имя (или название компании):"

    await bot.send_message(chat_id=user_id, text=text)


async def handle_webhook_application_message(chat_id: str, text: str, message: dict, user_id: str = ""):
    """Обработка сообщения для заявки"""
    try:
        # Используем chat_id как основной ключ (консистентно во всех событиях)
        if chat_id not in user_data:
            await send_start_message(chat_id)
            return

        state = user_states.get(chat_id, "menu")

        logger.info(f"🔄 Обработка сообщения от user_id={user_id}, chat_id={chat_id}, состояние: {state}")

        # Если в главном меню - показываем приветствие
        if state == "menu" or state is None:
            await send_start_message(chat_id)
            return

        # Категория и описание ситуации
        if state == "category_and_desc":
            category, description = parse_category_and_description(text, user_data[chat_id].get('client_type', ''))
            user_data[chat_id]['category'] = category
            user_data[chat_id]['description'] = description
            user_states[chat_id] = "name"
            await bot.send_message(chat_id=chat_id, text="Как вас зовут?")
            return

        # Ожидание имени
        if state == "name":
            user_data[chat_id]['name'] = text
            user_states[chat_id] = "phone"
            await bot.send_message(chat_id=chat_id, text="Ваш номер телефона?")
            return

        # Ожидание номера телефона
        if state == "phone":
            if not validate_phone(text):
                await bot.send_message(
                    chat_id=chat_id,
                    text="❌ Пожалуйста, введите корректный номер телефона.\nПримеры: +7 999 123-45-67 или 79991234567"
                )
                return

            user_data[chat_id]['phone'] = text
            await submit_application(chat_id)
            return

    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def submit_application(chat_id: str):
    """Отправить заявку админу и подтверждение пользователю"""
    try:
        data = user_data[chat_id]
        name = data.get('name', 'Неизвестно')

        await db.save_application(
            name=data['name'], phone=data.get('phone', ''), client_type=data.get('client_type', ''),
            category=data.get('category', ''), description=data.get('description', ''), source="Max",
            consent_pd=data.get('consent_pd', False), consent_policy=data.get('consent_policy', False)
        )
        logger.info(f"✓ Заявка {name} сохранена в БД")

        # Отправляем подтверждение пользователю
        await bot.send_message(
            chat_id=chat_id,
            text="✅ Спасибо! Ваша заявка отправлена. Наш специалист свяжется с вами в течение 24 часов."
        )

        # Отправляем заявку админу
        admin_text = f"📋 Новая заявка:\n\n" \
                    f"👤 Имя: {data.get('name', '—')}\n" \
                    f"📞 Телефон: {data.get('phone', '—')}\n" \
                    f"🏢 Тип: {data.get('client_type', '—')}\n" \
                    f"❓ Вопрос: {data.get('category', '—')}\n" \
                    f"📝 Описание: {data.get('description', '—')}\n"
        await bot.send_message(chat_id=admin_id, text=admin_text)

        # Очищаем данные пользователя
        if chat_id in user_data:
            del user_data[chat_id]
        if chat_id in user_states:
            del user_states[chat_id]

    except Exception as e:
        logger.error(f"✗ Ошибка сохранения заявки: {e}")
        import traceback
        logger.error(traceback.format_exc())

    await bot.send_message(
        chat_id=chat_id,
        text=f"✅ Спасибо, {user_data[chat_id].get('name', 'вы')}! Заявка принята.\nНаш специалист свяжется с вами в ближайшее время."
    )

    try:
        admin_message = (
            f"🔔 НОВАЯ ЗАЯВКА\n"
            f"{'━' * 30}\n"
            f"👤 Имя: {user_data[chat_id].get('name', '—')}\n"
            f"☎️ Телефон: {user_data[chat_id].get('phone', '—')}\n"
            f"🏷️ Тип: {user_data[chat_id].get('client_type', '—')}\n"
            f"📂 Категория: {user_data[chat_id].get('category', '—')}\n"
        )
        if user_data[chat_id].get('description'):
            admin_message += f"💬 Описание: {user_data[chat_id]['description']}\n"
        admin_message += (
            f"\n✅ Согласия:\n"
            f"  • Обработка ПД: {'✅ Да' if user_data[chat_id].get('consent_pd') else '❌ Нет'}\n"
            f"  • Политика: {'✅ Да' if user_data[chat_id].get('consent_policy') else '❌ Нет'}\n"
            f"\n👤 Профиль: https://web.max.ru/{user_id}\n"
            f"📲 Источник: Max\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"{'━' * 30}"
        )
        await send_admin_message(admin_message)
    except Exception as e:
        logger.error(f"✗ Ошибка отправки уведомления: {e}")

    user_states[chat_id] = None
    if user_id in user_data:
        del user_data[chat_id]


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

"""
Max бот-секретарь — приём заявок на консультации
Использует maxapi с Long Polling и интерактивными кнопками
"""
import logging
import re
from datetime import datetime
from maxapi import Bot, Dispatcher
from maxapi.types import Command, MessageCreated, MessageCallback

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)

import os
import sys

if not MAX_BOT_TOKEN or MAX_BOT_TOKEN == '':
    raise ValueError("MAX_BOT_TOKEN environment variable is not set or empty")

bot = Bot(token=MAX_BOT_TOKEN)
dp = Dispatcher()

admin_id = int(MAX_ADMIN_USER_ID) if isinstance(MAX_ADMIN_USER_ID, str) else MAX_ADMIN_USER_ID

user_data = {}
user_states = {}

logger.info(f"🔐 MAX_BOT_TOKEN установлен: {bool(MAX_BOT_TOKEN)}")
logger.info(f"👤 MAX_ADMIN_USER_ID: {admin_id}")


def make_keyboard(buttons):
    """Создать inline keyboard с кнопками
    buttons: список кортежей (text, payload)
    """
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [[
                    {"type": "callback", "text": text, "payload": payload}
                    for text, payload in buttons
                ]]
            }
        }
    ]


async def send_message_with_buttons(chat_id, text, buttons):
    """Отправить сообщение с интерактивными кнопками"""
    try:
        await bot.send_message(
            chat_id=str(chat_id),
            text=text,
            attachments=make_keyboard(buttons)
        )
        logger.info(f"✓ Сообщение с кнопками отправлено пользователю {chat_id}")
        return True
    except Exception as e:
        logger.error(f"✗ Ошибка отправки сообщения с кнопками: {e}")
        return False


def validate_phone(phone: str) -> bool:
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    return bool(
        re.match(r'^\+?7\d{9,10}$', cleaned) or
        re.match(r'^\+?\d{10,15}$', cleaned)
    )


async def send_admin_message(text: str):
    """Отправить сообщение админу"""
    try:
        await bot.send_message(chat_id=str(admin_id), text=text)
        logger.info(f"✓ Сообщение админу отправлено")
        return True
    except Exception as e:
        logger.error(f"✗ Ошибка отправки админу: {e}")
        return False


# ===== ОБРАБОТЧИКИ =====

@dp.message_created(Command('start'))
async def handle_start(message: MessageCreated):
    user_id = str(message.message.sender.user_id)
    user_data[user_id] = {
        'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
        'client_type': None, 'category': None, 'name': None, 'phone': None
    }
    user_states[user_id] = "menu"

    text = (
        "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
        "Мы поможем защитить ваши права."
    )

    await send_message_with_buttons(
        user_id,
        text,
        [("📝 Записаться", "record"), ("☎️ Помощь", "help")]
    )
    logger.info(f"📨 /start от {user_id}")


@dp.message_created(Command('my_id'))
async def handle_my_id(message: MessageCreated):
    user_id = message.message.sender.user_id
    await message.message.answer(text=f"ℹ️ Ваш Max ID: `{user_id}`")
    logger.info(f"📨 /my_id от {user_id}")


@dp.message_created()
async def handle_message(message: MessageCreated):
    user_id = str(message.message.sender.user_id)
    text = message.message.body.text if message.message.body and hasattr(message.message.body, 'text') else ""

    if not text or text.startswith('/'):
        return

    text = text.strip()
    state = user_states.get(user_id)
    logger.info(f"📨 Текст от {user_id} (state={state}): {text[:50]}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None
        }

    # Ожидание имени
    if state == "name":
        user_data[user_id]['name'] = text
        user_states[user_id] = "phone"
        await bot.send_message(chat_id=user_id, text="Ваш номер телефона?")
        return

    # Ожидание номера телефона
    if state == "phone":
        if not validate_phone(text):
            await bot.send_message(
                chat_id=user_id,
                text="❌ Пожалуйста, введите корректный номер телефона.\nПримеры: +7 999 123-45-67 или 79991234567"
            )
            return

        user_data[user_id]['phone'] = text
        user_states[user_id] = "description_choice"
        await send_message_with_buttons(
            user_id,
            "Кратко опишите ситуацию (необязательно):",
            [("✏️ Написать описание", "write_desc"), ("⏭️ Пропустить", "skip_desc")]
        )
        return

    # Ожидание описания
    if state == "description":
        await submit_application(user_id, description=text)
        return


async def ask_client_type(user_id: str):
    """Спросить тип клиента после согласия"""
    user_states[user_id] = "client_type"
    await send_message_with_buttons(
        user_id,
        "✅ Спасибо! Теперь выберите тип клиента:",
        [("👤 Физическое лицо", "physical"), ("🏢 Юридическое лицо", "legal")]
    )


async def ask_category_individual(user_id: str):
    """Спросить категорию для физ. лица"""
    await send_message_with_buttons(
        user_id,
        "Выберите категорию вопроса:",
        [
            ("🚗 ДТП", "cat_ind_dtp"),
            ("👨‍👩‍👧 Семейное право", "cat_ind_family"),
            ("🏠 Недвижимость", "cat_ind_realty"),
            ("⚖️ Трудовые споры", "cat_ind_work"),
            ("📋 Другое", "cat_ind_other")
        ]
    )


async def ask_category_business(user_id: str):
    """Спросить категорию для юр. лица"""
    await send_message_with_buttons(
        user_id,
        "Выберите категорию вопроса:",
        [
            ("📝 Регистрация бизнеса", "cat_bus_reg"),
            ("📄 Договоры и споры", "cat_bus_contracts"),
            ("👥 Трудовые вопросы", "cat_bus_hr"),
            ("💰 Налоги и штрафы", "cat_bus_tax"),
            ("📋 Другое", "cat_bus_other")
        ]
    )


@dp.message_callback()
async def handle_callback(callback: MessageCallback):
    user_id = str(callback.callback.user.user_id)
    payload = callback.callback.payload
    logger.info(f"📘 Callback от {user_id}: {payload}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None
        }

    # Главное меню
    if payload == "record":
        user_states[user_id] = "consent_step"
        msg = (
            f"📋 Чтобы продолжить, подтвердите согласия:\n\n"
            f"📄 Политика обработки данных:\n{PRIVACY_POLICY_URL}\n\n"
            f"📄 Согласие на обработку ПД:\n{AGREEMENT_URL}"
        )
        await send_message_with_buttons(
            user_id,
            msg,
            [
                ("✅ Согласен на обработку ПД", "consent_pd"),
                ("✅ Ознакомлен с политикой", "consent_policy"),
                ("❌ Отказать", "refuse")
            ]
        )
    elif payload == "help":
        await bot.send_message(
            chat_id=user_id,
            text="☎️ Позвоните нам: 8-495-999-85-89"
        )

    # Согласия
    elif payload == "consent_pd":
        user_data[user_id]['consent_pd'] = True
        await bot.send_message(chat_id=user_id, text="✅ Спасибо за согласие на обработку ПД!")
        # Проверяем, если оба согласия получены
        if user_data[user_id]['consent_policy']:
            await ask_client_type(user_id)
    elif payload == "consent_policy":
        user_data[user_id]['consent_policy'] = True
        await bot.send_message(chat_id=user_id, text="✅ Спасибо! Вы ознакомлены с политикой.")
        # Проверяем, если оба согласия получены
        if user_data[user_id]['consent_pd']:
            await ask_client_type(user_id)
    elif payload == "refuse":
        await send_refusal_notification(user_id)
        user_states[user_id] = None
        user_data[user_id] = {}
        await bot.send_message(
            chat_id=user_id,
            text="😔 Мы уважаем ваше решение.\n\n☎️ Позвоните нам: 8-495-999-85-89"
        )

    # Выбор типа клиента
    elif payload == "physical":
        user_data[user_id]['client_type'] = "Физическое лицо"
        user_states[user_id] = "category_individual"
        await ask_category_individual(user_id)
    elif payload == "legal":
        user_data[user_id]['client_type'] = "Юридическое лицо"
        user_states[user_id] = "category_business"
        await ask_category_business(user_id)

    # Категории физлица
    elif payload.startswith("cat_ind_"):
        cat = payload.replace("cat_ind_", "")
        cats = {
            "dtp": "ДТП", "family": "Семейное право", "realty": "Недвижимость",
            "work": "Трудовые споры", "other": "Другое"
        }
        user_data[user_id]['category'] = cats.get(cat, cat)
        user_states[user_id] = "name"
        await bot.send_message(chat_id=user_id, text="Как вас зовут?")

    # Категории юрлица
    elif payload.startswith("cat_bus_"):
        cat = payload.replace("cat_bus_", "")
        cats = {
            "reg": "Регистрация бизнеса", "contracts": "Договоры и споры",
            "hr": "Трудовые вопросы", "tax": "Налоги и штрафы", "other": "Другое"
        }
        user_data[user_id]['category'] = cats.get(cat, cat)
        user_states[user_id] = "name"
        await bot.send_message(chat_id=user_id, text="Как вас зовут?")

    # Описание ситуации
    elif payload == "write_desc":
        user_states[user_id] = "description"
        await bot.send_message(chat_id=user_id, text="Опишите вашу ситуацию:")
    elif payload == "skip_desc":
        await submit_application(user_id, description=None)

    await callback.answer_callback()


async def send_refusal_notification(user_id: str):
    try:
        phone = user_data.get(user_id, {}).get('phone', 'Не указан')
        message = (
            f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
            f"{'━' * 30}\n"
            f"Пользователь отказал в согласии на обработку ПД\n"
            f"👤 User ID: {user_id}\n"
            f"📱 Телефон: {phone}\n"
            f"📲 Источник: Max\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"{'━' * 30}"
        )
        await send_admin_message(message)
    except Exception as e:
        logger.error(f"✗ Ошибка отправки уведомления: {e}")


async def submit_application(user_id: str, description=None):
    data = user_data[user_id]
    name = data.get('name', 'Неизвестно')

    try:
        await db.save_application(
            name=data['name'], phone=data['phone'], client_type=data['client_type'],
            category=data['category'], description=description, source="Max",
            consent_pd=data['consent_pd'], consent_policy=data['consent_policy']
        )
        logger.info(f"✓ Заявка {name} сохранена")
    except Exception as e:
        logger.error(f"✗ Ошибка сохранения заявки: {e}")

    await bot.send_message(
        chat_id=user_id,
        text=f"✅ Спасибо, {name}! Заявка принята.\n"
             f"Наш специалист свяжется с вами в ближайшее время."
    )

    try:
        message = (
            f"🔔 НОВАЯ ЗАЯВКА\n"
            f"{'━' * 30}\n"
            f"👤 Имя: {data['name']}\n"
            f"📱 Телефон: {data['phone']}\n"
            f"🏷️ Тип: {data['client_type']}\n"
            f"📂 Категория: {data['category']}\n"
        )
        if description:
            message += f"💬 Суть: {description}\n"
        message += (
            f"\n✅ Согласия:\n"
            f"  • Обработка ПД: {'✅ Да' if data['consent_pd'] else '❌ Нет'}\n"
            f"  • Политика обработки: {'✅ Да' if data['consent_policy'] else '❌ Нет'}\n"
            f"\n👤 Max ID: {user_id}\n"
            f"📲 Источник: Max\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"{'━' * 30}"
        )
        await send_admin_message(message)
    except Exception as e:
        logger.error(f"✗ Ошибка отправки уведомления: {e}")

    user_states[user_id] = None
    if user_id in user_data:
        del user_data[user_id]


async def start_polling():
    """Запустить long polling"""
    logger.info("🚀 Запускаю Max бота (Long Polling)...")
    logger.info("=" * 60)
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка polling: {e}")
        import traceback
        logger.error(traceback.format_exc())

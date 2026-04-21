"""
Max бот-секретарь — приём заявок на консультации
Использует maxapi с интерактивными кнопками
"""
import logging
import re
from datetime import datetime
from maxapi import Bot, Dispatcher
from maxapi.types import Command, MessageCreated, MessageCallback, CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)

if not MAX_BOT_TOKEN or MAX_BOT_TOKEN == '':
    raise ValueError("MAX_BOT_TOKEN environment variable is not set or empty")

bot = Bot(token=MAX_BOT_TOKEN)
dp = Dispatcher()

admin_id = int(MAX_ADMIN_USER_ID) if isinstance(MAX_ADMIN_USER_ID, str) else MAX_ADMIN_USER_ID

user_data = {}
user_states = {}

logger.info(f"🔐 MAX_BOT_TOKEN установлен: {bool(MAX_BOT_TOKEN)}")
logger.info(f"👤 MAX_ADMIN_USER_ID: {admin_id}")


def make_keyboard(*buttons):
    """Создать InlineKeyboard из кортежей (text, payload)"""
    kb = InlineKeyboardBuilder()
    kb.row(*[CallbackButton(text=text, payload=payload) for text, payload in buttons])
    return [kb.as_markup()]


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
        'consent_pd': False, 'consent_policy': False,
        'client_type': None, 'category': None, 'name': None, 'phone': None
    }
    user_states[user_id] = "menu"

    text = "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\nМы поможем защитить ваши права."

    await message.message.answer(
        text=text,
        attachments=make_keyboard(("📝 Записаться", "record"), ("☎️ Позвонить", "help"))
    )
    logger.info(f"📨 /start от {user_id}")


@dp.message_created(Command('my_id'))
async def handle_my_id(message: MessageCreated):
    user_id = message.message.sender.user_id
    await message.message.answer(text=f"ℹ️ Ваш Max ID: `{user_id}`")
    logger.info(f"📨 /my_id от {user_id}")


@dp.message_callback()
async def handle_callback(callback: MessageCallback):
    user_id = str(callback.callback.user.user_id)
    payload = callback.callback.payload
    logger.info(f"📘 Callback от {user_id}: {payload}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None
        }

    # Главное меню
    if payload == "record":
        user_states[user_id] = "consent"
        msg = (
            f"📋 Подтвердите два согласия:\n\n"
            f"📄 Политика обработки данных:\n{PRIVACY_POLICY_URL}\n\n"
            f"📄 Согласие на обработку ПД:\n{AGREEMENT_URL}"
        )
        await callback.message.answer(
            text=msg,
            attachments=make_keyboard(
                ("✅ Согласен на обработку ПД", "consent_pd"),
                ("✅ Ознакомлен с политикой", "consent_policy"),
                ("❌ Отказать", "refuse")
            )
        )
    elif payload == "help":
        await callback.message.answer(text="☎️ Позвоните нам: 8-495-999-85-89")

    # Согласия
    elif payload == "consent_pd":
        user_data[user_id]['consent_pd'] = True
        await callback.message.answer(text="✅ Согласие на обработку ПД получено!")
        if user_data[user_id]['consent_policy']:
            await ask_client_type(callback.message, user_id)
    elif payload == "consent_policy":
        user_data[user_id]['consent_policy'] = True
        await callback.message.answer(text="✅ Вы ознакомлены с политикой!")
        if user_data[user_id]['consent_pd']:
            await ask_client_type(callback.message, user_id)
    elif payload == "refuse":
        await send_refusal_notification(user_id)
        user_states[user_id] = None
        user_data[user_id] = {}
        await callback.message.answer(text="😔 Мы уважаем ваше решение.\n\n☎️ Позвоните нам: 8-495-999-85-89")

    # Выбор типа клиента
    elif payload == "physical":
        user_data[user_id]['client_type'] = "Физическое лицо"
        user_states[user_id] = "category_individual"
        await callback.message.answer(
            text="Выберите категорию вопроса:",
            attachments=make_keyboard(
                ("🚗 ДТП", "cat_ind_dtp"),
                ("👨‍👩‍👧 Семейное право", "cat_ind_family"),
                ("🏠 Недвижимость", "cat_ind_realty"),
                ("⚖️ Трудовые споры", "cat_ind_work"),
                ("📋 Другое", "cat_ind_other")
            )
        )
    elif payload == "legal":
        user_data[user_id]['client_type'] = "Юридическое лицо"
        user_states[user_id] = "category_business"
        await callback.message.answer(
            text="Выберите категорию вопроса:",
            attachments=make_keyboard(
                ("📝 Регистрация бизнеса", "cat_bus_reg"),
                ("📄 Договоры и споры", "cat_bus_contracts"),
                ("👥 Трудовые вопросы", "cat_bus_hr"),
                ("💰 Налоги и штрафы", "cat_bus_tax"),
                ("📋 Другое", "cat_bus_other")
            )
        )

    # Категории физлица
    elif payload.startswith("cat_ind_"):
        cat = payload.replace("cat_ind_", "")
        cats = {
            "dtp": "ДТП", "family": "Семейное право", "realty": "Недвижимость",
            "work": "Трудовые споры", "other": "Другое"
        }
        user_data[user_id]['category'] = cats.get(cat, cat)
        user_states[user_id] = "name"
        await callback.message.answer(text="Как вас зовут?")

    # Категории юрлица
    elif payload.startswith("cat_bus_"):
        cat = payload.replace("cat_bus_", "")
        cats = {
            "reg": "Регистрация бизнеса", "contracts": "Договоры и споры",
            "hr": "Трудовые вопросы", "tax": "Налоги и штрафы", "other": "Другое"
        }
        user_data[user_id]['category'] = cats.get(cat, cat)
        user_states[user_id] = "name"
        await callback.message.answer(text="Как вас зовут?")

    # Описание ситуации
    elif payload == "write_desc":
        user_states[user_id] = "description"
        await callback.message.answer(text="Опишите вашу ситуацию:")
    elif payload == "skip_desc":
        await submit_application(user_id, description=None)

    await callback.answer_callback()


async def ask_client_type(message, user_id: str):
    """Спросить тип клиента после согласия"""
    user_states[user_id] = "client_type"
    await message.answer(
        text="✅ Спасибо! Теперь выберите тип клиента:",
        attachments=make_keyboard(
            ("👤 Физическое лицо", "physical"),
            ("🏢 Юридическое лицо", "legal")
        )
    )


@dp.message_created()
async def handle_message(message: MessageCreated):
    user_id = str(message.message.sender.user_id)
    text = message.message.body.text if message.message.body and hasattr(message.message.body, 'text') else ""

    if not text or text.startswith('/'):
        return

    text = text.strip()
    state = user_states.get(user_id)
    logger.info(f"📨 {user_id} (state={state}): {text[:50]}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None
        }

    # Ожидание имени
    if state == "name":
        user_data[user_id]['name'] = text
        user_states[user_id] = "phone"
        await message.message.answer(text="Ваш номер телефона?")
        return

    # Ожидание номера телефона
    if state == "phone":
        if not validate_phone(text):
            await message.message.answer(
                text="❌ Пожалуйста, введите корректный номер телефона.\nПримеры: +7 999 123-45-67 или 79991234567"
            )
            return

        user_data[user_id]['phone'] = text
        user_states[user_id] = "description_choice"
        await message.message.answer(
            text="Кратко опишите ситуацию (необязательно):",
            attachments=make_keyboard(
                ("✏️ Написать описание", "write_desc"),
                ("⏭️ Пропустить", "skip_desc")
            )
        )
        return

    # Ожидание описания
    if state == "description":
        await submit_application(user_id, description=text)
        return


async def send_refusal_notification(user_id: str):
    try:
        phone = user_data.get(user_id, {}).get('phone', 'Не указан')
        message = (
            f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
            f"{'━' * 30}\n"
            f"Пользователь отказал в согласии\n"
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
        text=f"✅ Спасибо, {name}! Заявка принята.\nНаш специалист свяжется с вами в ближайшее время."
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
            f"  • Политика: {'✅ Да' if data['consent_policy'] else '❌ Нет'}\n"
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
    logger.info("🚀 Запускаю Max бота...")
    logger.info("=" * 60)
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())

"""
Max бот-секретарь — приём заявок на консультации
Использует maxapi с Long Polling
"""
import logging
import re
from datetime import datetime
from maxapi import Bot, Dispatcher
from maxapi.types import Command, MessageCreated, MessageCallback

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

    text = (
        "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
        "Мы поможем защитить ваши права.\n\n"
        "Выберите:\n"
        "1️⃣ Записаться на консультацию\n"
        "2️⃣ Позвонить нам"
    )

    await message.message.answer(text=text)
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
    logger.info(f"📨 {user_id} (state={state}): {text[:50]}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None
        }

    # Главное меню
    if state == "menu":
        if text == "1":
            user_states[user_id] = "consent"
            msg = (
                f"📋 Подтвердите два согласия:\n\n"
                f"📄 Политика обработки данных:\n{PRIVACY_POLICY_URL}\n\n"
                f"📄 Согласие на обработку ПД:\n{AGREEMENT_URL}\n\n"
                f"Ответьте:\n"
                f"1️⃣ Согласен на обработку ПД\n"
                f"2️⃣ Ознакомлен с политикой\n"
                f"3️⃣ Отказать"
            )
            await message.message.answer(text=msg)
        elif text == "2":
            await message.message.answer(text="☎️ Позвоните нам: 8-495-999-85-89")
        return

    # Согласия (первое и второе)
    if state == "consent":
        if text == "1":
            user_data[user_id]['consent_pd'] = True
            await message.message.answer(text="✅ Спасибо! Согласие на обработку ПД получено.")
            if user_data[user_id]['consent_policy']:
                await ask_client_type(user_id)
        elif text == "2":
            user_data[user_id]['consent_policy'] = True
            await message.message.answer(text="✅ Спасибо! Вы ознакомлены с политикой.")
            if user_data[user_id]['consent_pd']:
                await ask_client_type(user_id)
        elif text == "3":
            await send_refusal_notification(user_id)
            user_states[user_id] = None
            user_data[user_id] = {}
            await message.message.answer(
                text="😔 Мы уважаем ваше решение.\n\n☎️ Позвоните нам: 8-495-999-85-89"
            )
        return

    # Выбор типа клиента
    if state == "client_type":
        if text == "1":
            user_data[user_id]['client_type'] = "Физическое лицо"
            user_states[user_id] = "category_individual"
            msg = (
                "Выберите категорию вопроса:\n\n"
                "1️⃣ ДТП\n"
                "2️⃣ Семейное право\n"
                "3️⃣ Недвижимость\n"
                "4️⃣ Трудовые споры\n"
                "5️⃣ Другое"
            )
            await message.message.answer(text=msg)
        elif text == "2":
            user_data[user_id]['client_type'] = "Юридическое лицо"
            user_states[user_id] = "category_business"
            msg = (
                "Выберите категорию вопроса:\n\n"
                "1️⃣ Регистрация бизнеса\n"
                "2️⃣ Договоры и споры\n"
                "3️⃣ Трудовые вопросы\n"
                "4️⃣ Налоги и штрафы\n"
                "5️⃣ Другое"
            )
            await message.message.answer(text=msg)
        return

    # Категория физлица
    if state == "category_individual":
        cat_map = {"1": "ДТП", "2": "Семейное право", "3": "Недвижимость",
                   "4": "Трудовые споры", "5": "Другое"}
        if text in cat_map:
            user_data[user_id]['category'] = cat_map[text]
            user_states[user_id] = "name"
            await message.message.answer(text="Как вас зовут?")
        return

    # Категория юрлица
    if state == "category_business":
        cat_map = {"1": "Регистрация бизнеса", "2": "Договоры и споры",
                   "3": "Трудовые вопросы", "4": "Налоги и штрафы", "5": "Другое"}
        if text in cat_map:
            user_data[user_id]['category'] = cat_map[text]
            user_states[user_id] = "name"
            await message.message.answer(text="Как вас зовут?")
        return

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
        msg = (
            "Кратко опишите ситуацию (необязательно):\n\n"
            "1️⃣ Написать описание\n"
            "2️⃣ Пропустить"
        )
        await message.message.answer(text=msg)
        return

    # Выбор описания
    if state == "description_choice":
        if text == "1":
            user_states[user_id] = "description"
            await message.message.answer(text="Опишите вашу ситуацию:")
        elif text == "2":
            await submit_application(user_id, description=None)
        return

    # Ожидание описания
    if state == "description":
        await submit_application(user_id, description=text)
        return


async def ask_client_type(user_id: str):
    """Спросить тип клиента после согласия"""
    user_states[user_id] = "client_type"
    msg = (
        "✅ Спасибо! Теперь выберите тип клиента:\n\n"
        "1️⃣ Физическое лицо\n"
        "2️⃣ Юридическое лицо"
    )
    await bot.send_message(chat_id=user_id, text=msg)


@dp.message_callback()
async def handle_callback(callback: MessageCallback):
    logger.info(f"📘 Callback от {callback.callback.user.user_id}: {callback.callback.payload}")
    await callback.answer_callback()


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

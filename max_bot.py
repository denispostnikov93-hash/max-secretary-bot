"""
Max бот-секретарь — приём заявок на консультации
Использует maxapi с Long Polling (без класса, как в примерах)
"""
import logging
import re
from datetime import datetime
from maxapi import Bot, Dispatcher
from maxapi.types import Command, MessageCreated, MessageCallback

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)

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


# ===== КЛАВИАТУРЫ =====

def _get_buttons_main():
    return [[{"type": "callback", "text": "📝 Записаться на консультацию", "payload": "record"}]]

def _get_buttons_consent():
    return [
        [{"type": "callback", "text": "✅ Согласен на обработку персональных данных", "payload": "consent_pd"}],
        [{"type": "callback", "text": "✅ Ознакомлен с политикой обработки данных", "payload": "consent_policy"}],
        [{"type": "callback", "text": "❌ Отказать в согласии", "payload": "refuse"}]
    ]

def _get_buttons_client_type():
    return [[
        {"type": "callback", "text": "👤 Физическое лицо", "payload": "physical"},
        {"type": "callback", "text": "🏢 Юридическое лицо", "payload": "legal"}
    ]]

def _get_buttons_individual_categories():
    return [
        [{"type": "callback", "text": "🚗 ДТП", "payload": "cat_dtp"}],
        [{"type": "callback", "text": "👨‍👩‍👧 Семейное право", "payload": "cat_family"}],
        [{"type": "callback", "text": "🏠 Недвижимость", "payload": "cat_realty"}],
        [{"type": "callback", "text": "⚖️ Трудовые споры", "payload": "cat_work"}],
        [{"type": "callback", "text": "❓ Другое", "payload": "cat_other"}]
    ]

def _get_buttons_business_categories():
    return [
        [{"type": "callback", "text": "📋 Регистрация бизнеса", "payload": "cat_reg"}],
        [{"type": "callback", "text": "📝 Договоры и споры", "payload": "cat_contracts"}],
        [{"type": "callback", "text": "👔 Трудовые вопросы", "payload": "cat_hr"}],
        [{"type": "callback", "text": "💰 Налоги и штрафы", "payload": "cat_tax"}],
        [{"type": "callback", "text": "❓ Другое", "payload": "cat_other"}]
    ]

def _get_buttons_description():
    return [[
        {"type": "callback", "text": "✏️ Написать", "payload": "write_desc"},
        {"type": "callback", "text": "➡️ Пропустить", "payload": "skip_desc"}
    ]]

def _get_buttons_refusal():
    return [
        [{"type": "callback", "text": "☎️ Позвонить: 8-495-999-85-89", "payload": "call"}],
        [{"type": "callback", "text": "↩️ Дать согласие и оставить заявку", "payload": "back_consent"}]
    ]


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
    user_states[user_id] = None

    await message.message.answer(
        text="👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
             "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
        attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_main()}}]
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
    logger.info(f"📨 Текст от {user_id}: {text[:50]}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None
        }

    # Ожидание имени
    if user_states.get(user_id) == "waiting_name":
        user_data[user_id]['name'] = text
        user_states[user_id] = "waiting_phone"
        await message.message.answer(text="Ваш номер телефона?")
        return

    # Ожидание номера телефона
    if user_states.get(user_id) == "waiting_phone":
        if not validate_phone(text):
            await message.message.answer(
                text="❌ Пожалуйста, введите корректный номер телефона.\n"
                     "Примеры: +7 999 123-45-67 или 79991234567"
            )
            return

        user_data[user_id]['phone'] = text
        user_states[user_id] = "waiting_description_choice"
        await message.message.answer(
            text="Кратко опишите ситуацию (необязательно):",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_description()}}]
        )
        return

    # Ожидание описания
    if user_states.get(user_id) == "waiting_description":
        await submit_application(user_id, description=text)
        return


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

    # Запись на консультацию
    if payload == "record":
        user_data[user_id]['in_consent_step'] = True
        await callback.answer_callback()
        await bot.send_message(
            chat_id=user_id,
            text=f"📋 Чтобы продолжить, прочитайте и подтвердите:\n\n"
                 f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                 f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                 f"Нажмите обе кнопки ниже для подтверждения:",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_consent()}}]
        )
        return

    # Согласие ПД
    if payload == "consent_pd":
        if user_data[user_id].get('in_consent_step'):
            user_data[user_id]['consent_pd'] = True
            await callback.answer_callback()
            await check_consents(user_id)
        return

    # Согласие политика
    if payload == "consent_policy":
        if user_data[user_id].get('in_consent_step'):
            user_data[user_id]['consent_policy'] = True
            await callback.answer_callback()
            await check_consents(user_id)
        return

    # Отказ
    if payload == "refuse":
        await callback.answer_callback()
        await send_refusal_notification(user_id)
        user_states[user_id] = None
        user_data[user_id] = {}
        await bot.send_message(
            chat_id=user_id,
            text="😔 Мы уважаем ваше решение и соблюдаем закон о защите персональных данных.\n\n"
                 "Без согласия на обработку ПД мы не можем продолжить стандартный процесс консультации.\n\n"
                 "Выберите один из вариантов:\n"
                 "• Позвоните нам по номеру 8-495-999-85-89 и получите бесплатную консультацию\n"
                 "• Или дайте согласие и оставьте заявку через бота",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_refusal()}}]
        )
        return

    # Тип клиента
    if payload == "physical":
        user_data[user_id]['client_type'] = "Физическое лицо"
        user_states[user_id] = "waiting_category"
        await callback.answer_callback()
        await bot.send_message(
            chat_id=user_id,
            text="Выберите категорию вопроса:",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_individual_categories()}}]
        )
        return

    if payload == "legal":
        user_data[user_id]['client_type'] = "Юридическое лицо"
        user_states[user_id] = "waiting_category"
        await callback.answer_callback()
        await bot.send_message(
            chat_id=user_id,
            text="Выберите категорию вопроса:",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_business_categories()}}]
        )
        return

    # Категория
    cat_map = {
        "cat_dtp": "ДТП", "cat_family": "Семейное право", "cat_realty": "Недвижимость",
        "cat_work": "Трудовые споры", "cat_other": "Другое",
        "cat_reg": "Регистрация бизнеса", "cat_contracts": "Договоры и споры",
        "cat_hr": "Трудовые вопросы", "cat_tax": "Налоги и штрафы"
    }

    if payload in cat_map:
        user_data[user_id]['category'] = cat_map[payload]
        user_states[user_id] = "waiting_name"
        await callback.answer_callback()
        await bot.send_message(chat_id=user_id, text="Как вас зовут?")
        return

    # Описание
    if payload == "write_desc":
        user_states[user_id] = "waiting_description"
        await callback.answer_callback()
        await bot.send_message(chat_id=user_id, text="Опишите вашу ситуацию:")
        return

    if payload == "skip_desc":
        await callback.answer_callback()
        await submit_application(user_id, description=None)
        return

    if payload == "call":
        await callback.answer_callback()
        await bot.send_message(
            chat_id=user_id,
            text="✅ Спасибо! Ждем вашего звонка.\n\n"
                 "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_main()}}]
        )
        return

    if payload == "back_consent":
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False, 'in_consent_step': True,
            'client_type': None, 'category': None, 'name': None, 'phone': None
        }
        await callback.answer_callback()
        await bot.send_message(
            chat_id=user_id,
            text=f"📋 Чтобы продолжить, прочитайте и подтвердите:\n\n"
                 f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                 f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                 f"Нажмите обе кнопки ниже для подтверждения:",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_consent()}}]
        )
        return


async def check_consents(user_id: str):
    data = user_data[user_id]
    if data['consent_pd'] and data['consent_policy']:
        data['in_consent_step'] = False
        user_states[user_id] = "waiting_client_type"
        await bot.send_message(
            chat_id=user_id,
            text="✅ Спасибо! Теперь выберите тип клиента:",
            attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_client_type()}}]
        )


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
             f"Наш специалист свяжется с вами в ближайшее время.",
        attachments=[{"type": "inline_keyboard", "payload": {"buttons": _get_buttons_main()}}]
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

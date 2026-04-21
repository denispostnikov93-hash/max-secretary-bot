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


async def get_user_profile_phone(user_id: str) -> str:
    """Попыт получить номер телефона из профиля Max через API"""
    try:
        # Пытаемся через разные методы получить информацию
        # Проверяем наличие метода get_me (получить информацию о боте или пользователе)
        if hasattr(bot, 'get_me'):
            result = await bot.get_me()
            logger.info(f"🔍 get_me result: {result}")

        # Проверяем get_user если он существует
        if hasattr(bot, 'get_user'):
            try:
                user_info = await bot.get_user(user_id=int(user_id))
                logger.info(f"🔍 get_user result: {vars(user_info) if hasattr(user_info, '__dict__') else user_info}")

                if hasattr(user_info, 'phone') and user_info.phone:
                    return user_info.phone
            except Exception as e:
                logger.warning(f"⚠️ get_user failed: {e}")

        logger.warning(f"⚠️ Не удалось получить номер из профиля Max (API ограничение или метод недоступен)")
        return ""

    except Exception as e:
        logger.warning(f"⚠️ Ошибка при попытке получить профиль: {type(e).__name__}: {e}")
        return ""


def validate_phone(phone: str) -> bool:
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    return bool(
        re.match(r'^\+?7\d{9,10}$', cleaned) or
        re.match(r'^\+?\d{10,15}$', cleaned)
    )


def parse_category_and_description(text: str, client_type: str) -> tuple:
    """Распознать категорию из текста и вернуть (категория, описание)"""
    text_lower = text.lower()

    if client_type == "Физическое лицо":
        categories = {
            "ДТП": ["дтп", "авария", "автомобиль"],
            "Семейное право": ["семейн", "развод", "алимент", "опека", "ребен"],
            "Недвижимость": ["недвижимость", "квартира", "дом", "имущество", "жилищ"],
            "Трудовые споры": ["трудов", "работ", "сотрудник", "уволен", "зарплат"],
            "Другое": []
        }
    else:  # Юридическое лицо
        categories = {
            "Регистрация бизнеса": ["регистр", "ооо", "ип", "компани", "бизнес"],
            "Договоры и споры": ["договор", "спор", "контракт", "исск", "претензи"],
            "Трудовые вопросы": ["кадр", "сотрудник", "персонал", "найм", "трудов"],
            "Налоги и штрафы": ["налог", "штраф", "ндс", "декларац", "проверк"],
            "Другое": []
        }

    # Ищем совпадение по ключевым словам
    for cat, keywords in categories.items():
        if cat == "Другое":
            continue
        for keyword in keywords:
            if keyword in text_lower:
                return cat, text

    # Если не нашли, возвращаем "Другое"
    return "Другое", text


async def send_admin_message(text: str):
    """Отправить сообщение админу"""
    try:
        logger.info(f"📤 Попытка отправить сообщение админу (ID: {admin_id}, type: {type(admin_id).__name__})")
        logger.info(f"📝 Текст: {text[:100]}...")
        # Пробуем отправить по user_id (как int и как str)
        try:
            result = await bot.send_message(chat_id=admin_id, text=text)
            logger.info(f"✓ Сообщение админу отправлено (chat_id как int)")
            return True
        except Exception as e1:
            logger.warning(f"⚠️ Не получилось с int, пробуем со str: {e1}")
            result = await bot.send_message(chat_id=str(admin_id), text=text)
            logger.info(f"✓ Сообщение админу отправлено (chat_id как str)")
            return True
    except Exception as e:
        logger.error(f"✗ ОШИБКА отправки админу: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


# ===== ОБРАБОТЧИКИ =====

@dp.message_created(Command('start'))
async def handle_start(message: MessageCreated):
    user_id = str(message.message.sender.user_id)
    user_data[user_id] = {
        'consent_pd': False, 'consent_policy': False,
        'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
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


@dp.message_created()
async def handle_any_message(message: MessageCreated):
    """Обработчик для любого текста - инициирует процесс если это первое сообщение"""
    user_id = str(message.message.sender.user_id)
    text = message.message.body.text if message.message.body and hasattr(message.message.body, 'text') else ""

    # Игнорируем команды (уже обработаны выше)
    if text.startswith('/'):
        return

    # Если пользователь уже в процессе - обработаем как обычное сообщение в других обработчиках
    if user_id in user_states and user_states[user_id] != "menu":
        return

    # Первое сообщение или в главном меню - показываем стартовое сообщение
    if user_id not in user_data:
        logger.info(f"📨 Первое сообщение от {user_id}: {text[:30]}")
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }
        user_states[user_id] = "menu"

        await message.message.answer(
            text="👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\nМы поможем защитить ваши права.",
            attachments=make_keyboard(("📝 Записаться", "record"), ("☎️ Позвонить", "help"))
        )


@dp.message_callback()
async def handle_callback(callback: MessageCallback):
    user_id = str(callback.callback.user.user_id)
    payload = callback.callback.payload
    logger.info(f"📘 Callback от {user_id}: {payload}")

    if user_id not in user_data:
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
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
        user_states[user_id] = "consent_retry"
        await callback.message.answer(
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
        user_data[user_id] = {
            'consent_pd': False, 'consent_policy': False,
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }
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

    # Выбор типа клиента
    elif payload == "physical":
        user_data[user_id]['client_type'] = "Физическое лицо"
        user_states[user_id] = "category_and_desc"
        await callback.message.answer(
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
        user_data[user_id]['client_type'] = "Юридическое лицо"
        user_states[user_id] = "category_and_desc"
        await callback.message.answer(
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
            'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
        }

    # Категория и описание ситуации
    if state == "category_and_desc":
        category, description = parse_category_and_description(text, user_data[user_id]['client_type'])
        user_data[user_id]['category'] = category
        user_data[user_id]['description'] = description
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
        await submit_application(user_id, message)
        return


async def send_refusal_notification(user_id: str):
    """Отправить админу уведомление об отказе пользователя"""
    try:
        logger.info(f"📋 Создание уведомления об отказе для {user_id}")
        phone_from_profile = await get_user_profile_phone(user_id)

        message = (
            f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
            f"{'━' * 40}\n"
            f"Пользователь отказал в согласии на обработку ПД\n"
            f"👤 Профиль: https://web.max.ru/{user_id}\n"
        )
        if phone_from_profile:
            message += f"📱 Телефон (профиль): {phone_from_profile}\n"
        message += (
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


async def submit_application(user_id: str, message: MessageCreated):
    data = user_data[user_id]
    name = data.get('name', 'Неизвестно')

    # Получаем телефон из профиля пользователя (если доступен)
    phone_from_profile = await get_user_profile_phone(user_id)
    # Используем введённый телефон как основной, профиль как доп информация
    primary_phone = data.get('phone', 'Не указан')

    try:
        await db.save_application(
            name=data['name'], phone=primary_phone, client_type=data['client_type'],
            category=data['category'], description=data['description'], source="Max",
            consent_pd=data['consent_pd'], consent_policy=data['consent_policy']
        )
        logger.info(f"✓ Заявка {name} сохранена")
    except Exception as e:
        logger.error(f"✗ Ошибка сохранения заявки: {e}")

    await message.message.answer(
        text=f"✅ Спасибо, {name}! Заявка принята.\nНаш специалист свяжется с вами в ближайшее время."
    )

    try:
        admin_message = (
            f"🔔 НОВАЯ ЗАЯВКА\n"
            f"{'━' * 30}\n"
            f"👤 Имя: {data['name']}\n"
            f"☎️ Телефон (введён): {primary_phone}\n"
        )
        if phone_from_profile:
            admin_message += f"📱 Телефон (профиль): {phone_from_profile}\n"
        admin_message += (
            f"🏷️ Тип: {data['client_type']}\n"
            f"📂 Категория: {data['category']}\n"
        )
        if data['description']:
            admin_message += f"💬 Описание: {data['description']}\n"
        admin_message += (
            f"\n✅ Согласия:\n"
            f"  • Обработка ПД: {'✅ Да' if data['consent_pd'] else '❌ Нет'}\n"
            f"  • Политика: {'✅ Да' if data['consent_policy'] else '❌ Нет'}\n"
            f"\n👤 Профиль: https://web.max.ru/{user_id}\n"
            f"📲 Источник: Max\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"{'━' * 30}"
        )
        await send_admin_message(admin_message)
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

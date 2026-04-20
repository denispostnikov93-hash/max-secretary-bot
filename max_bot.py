"""
Max бот-секретарь для приема заявок
Использует umaxbot с InlineKeyboard и FSM как Telegram бот
"""
import logging
import re
from datetime import datetime
from umaxbot import Bot, Dispatcher, types
from umaxbot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from umaxbot.fsm.context import FSMContext
from umaxbot.fsm.state import State, StatesGroup
from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)

# === STATES ===
class ApplicationForm(StatesGroup):
    waiting_consent_pd = State()
    waiting_consent_policy = State()
    waiting_client_type = State()
    waiting_category = State()
    waiting_name = State()
    waiting_phone = State()
    waiting_description_choice = State()
    waiting_description = State()

# === BOT ===
class MaxSecretaryBot:
    def __init__(self):
        self.bot = Bot(token=MAX_BOT_TOKEN)
        self.dp = Dispatcher(self.bot)
        self.setup_handlers()
        self.user_data = {}

    def setup_handlers(self):
        """Настроить обработчики"""
        @self.dp.message()
        async def cmd_start(message: Message, state: FSMContext):
            """Команда /start"""
            if message.text == "/start":
                user_id = message.sender.id
                await state.clear()
                self.user_data[user_id] = {
                    'consent_pd': False,
                    'consent_policy': False,
                    'in_consent_step': False,
                    'client_type': None,
                    'category': None,
                    'name': None,
                    'phone': None,
                    'description': None
                }

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Записаться на консультацию", callback_data="record")]
                ])

                await self.bot.send_message(
                    chat_id=user_id,
                    text="👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
                         "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
                    reply_markup=keyboard,
                    format="markdown"
                )
                logger.info(f"User {user_id} started")

        @self.dp.callback()
        async def handle_callback(cb: types.CallbackQuery, state: FSMContext):
            """Обработка callback кнопок"""
            user_id = cb.sender.id
            payload = cb.payload

            try:
                if payload == "record":
                    if user_id not in self.user_data:
                        self.user_data[user_id] = {
                            'consent_pd': False,
                            'consent_policy': False,
                            'in_consent_step': True
                        }
                    else:
                        self.user_data[user_id]['in_consent_step'] = True

                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Согласен на обработку ПД", callback_data="consent_pd")],
                        [InlineKeyboardButton(text="✅ Ознакомлен с политикой", callback_data="consent_policy")],
                        [InlineKeyboardButton(text="❌ Отказать", callback_data="refuse_consent")]
                    ])

                    await self.bot.send_message(
                        chat_id=user_id,
                        text=f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                             f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                             f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                             f"Нажмите обе кнопки ниже для подтверждения:",
                        reply_markup=keyboard,
                        format="markdown"
                    )
                    logger.info(f"User {user_id} started application process")

                elif payload == "consent_pd":
                    if user_id in self.user_data and self.user_data[user_id].get('in_consent_step'):
                        self.user_data[user_id]['consent_pd'] = True
                        logger.info(f"User {user_id} consented to data processing")
                        await self.check_consents(user_id)

                elif payload == "consent_policy":
                    if user_id in self.user_data and self.user_data[user_id].get('in_consent_step'):
                        self.user_data[user_id]['consent_policy'] = True
                        logger.info(f"User {user_id} consented to policy")
                        await self.check_consents(user_id)

                elif payload == "refuse_consent":
                    await self.consent_refusal_handler(user_id, state)

                elif payload.startswith("client_"):
                    client_type = "Физическое лицо" if payload == "client_individual" else "Юридическое лицо"
                    await self.client_type_handler(user_id, client_type, state)

                elif payload.startswith("category_"):
                    category_map = {
                        "dtp": "ДТП",
                        "family": "Семейное право",
                        "real_estate": "Недвижимость",
                        "labor": "Трудовые споры",
                        "other_individual": "Другое",
                        "business_reg": "Регистрация бизнеса",
                        "contracts": "Договоры и споры",
                        "labor_issues": "Трудовые вопросы",
                        "taxes": "Налоги и штрафы",
                        "other_business": "Другое"
                    }
                    category = category_map.get(payload.replace("category_", ""), payload)
                    self.user_data[user_id]['category'] = category
                    await state.set_state(ApplicationForm.waiting_name)
                    await self.bot.send_message(
                        chat_id=user_id,
                        text="Как вас зовут?"
                    )

                elif payload == "desc_write":
                    await state.set_state(ApplicationForm.waiting_description)
                    await self.bot.send_message(
                        chat_id=user_id,
                        text="Опишите вашу ситуацию:"
                    )

                elif payload == "desc_skip":
                    await self.submit_application(user_id, description=None, state=state)

                elif payload == "call_phone":
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📝 Записаться на консультацию", callback_data="record")]
                    ])
                    await self.bot.send_message(
                        chat_id=user_id,
                        text="✅ Спасибо! Ждем вашего звонка.\n\n"
                             "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.",
                        reply_markup=keyboard
                    )

                elif payload == "retry_consent":
                    if user_id not in self.user_data:
                        self.user_data[user_id] = {
                            'consent_pd': False,
                            'consent_policy': False,
                            'in_consent_step': True
                        }
                    else:
                        self.user_data[user_id]['consent_pd'] = False
                        self.user_data[user_id]['consent_policy'] = False
                        self.user_data[user_id]['in_consent_step'] = True

                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Согласен на обработку ПД", callback_data="consent_pd")],
                        [InlineKeyboardButton(text="✅ Ознакомлен с политикой", callback_data="consent_policy")],
                        [InlineKeyboardButton(text="❌ Отказать", callback_data="refuse_consent")]
                    ])

                    await self.bot.send_message(
                        chat_id=user_id,
                        text=f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                             f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                             f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                             f"Нажмите обе кнопки ниже для подтверждения:",
                        reply_markup=keyboard,
                        format="markdown"
                    )

            except Exception as e:
                logger.error(f"❌ Ошибка callback: {e}", exc_info=True)
                await self.bot.send_message(user_id, "❌ Ошибка. Повторите попытку.")

        @self.dp.message()
        async def handle_message(message: Message, state: FSMContext):
            """Обработка текстовых сообщений"""
            user_id = message.sender.id
            text = (message.text or "").strip()

            if not user_id or not text:
                return

            logger.info(f"User {user_id}: {text[:50]}")

            try:
                current_state = await state.get_state()

                if current_state == ApplicationForm.waiting_client_type:
                    if text in ["Физическое лицо", "Юридическое лицо"]:
                        await self.client_type_handler(user_id, text, state)

                elif current_state == ApplicationForm.waiting_category:
                    self.user_data[user_id]['category'] = text
                    await state.set_state(ApplicationForm.waiting_name)
                    await self.bot.send_message(chat_id=user_id, text="Как вас зовут?")

                elif current_state == ApplicationForm.waiting_name:
                    self.user_data[user_id]['name'] = text
                    await state.set_state(ApplicationForm.waiting_phone)
                    await self.bot.send_message(chat_id=user_id, text="Ваш номер телефона?")

                elif current_state == ApplicationForm.waiting_phone:
                    if not self.validate_phone(text):
                        await self.bot.send_message(
                            chat_id=user_id,
                            text="❌ Пожалуйста, введите корректный номер телефона.\nПримеры: +7 999 123-45-67 или 79991234567"
                        )
                        return

                    self.user_data[user_id]['phone'] = text
                    await state.set_state(ApplicationForm.waiting_description_choice)

                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✏️ Написать", callback_data="desc_write"),
                         InlineKeyboardButton(text="➡️ Пропустить", callback_data="desc_skip")]
                    ])

                    await self.bot.send_message(
                        chat_id=user_id,
                        text="Кратко опишите ситуацию (необязательно):",
                        reply_markup=keyboard
                    )

                elif current_state == ApplicationForm.waiting_description:
                    await self.submit_application(user_id, description=text, state=state)

            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)
                await self.bot.send_message(user_id, "❌ Ошибка. Повторите попытку.")

    def validate_phone(self, phone: str) -> bool:
        """Проверить корректность номера телефона"""
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        if re.match(r'^\+?7\d{9,10}$', cleaned) or re.match(r'^\+?\d{10,15}$', cleaned):
            return True
        return False

    async def check_consents(self, user_id: str):
        """Проверить оба согласия"""
        if self.user_data[user_id]['consent_pd'] and self.user_data[user_id]['consent_policy']:
            self.user_data[user_id]['in_consent_step'] = False
            logger.info(f"User {user_id} passed consent step")

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👤 Физическое лицо", callback_data="client_individual")],
                [InlineKeyboardButton(text="🏢 Юридическое лицо", callback_data="client_business")]
            ])

            await self.bot.send_message(
                chat_id=user_id,
                text="✅ Спасибо! Теперь выберите тип клиента:",
                reply_markup=keyboard
            )

    async def client_type_handler(self, user_id: str, text: str, state: FSMContext):
        """Выбор типа клиента"""
        self.user_data[user_id]['client_type'] = text
        await state.set_state(ApplicationForm.waiting_category)

        if "Физическое" in text:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚗 ДТП", callback_data="category_dtp")],
                [InlineKeyboardButton(text="👨‍👩‍👧 Семейное право", callback_data="category_family")],
                [InlineKeyboardButton(text="🏠 Недвижимость", callback_data="category_real_estate")],
                [InlineKeyboardButton(text="💼 Трудовые споры", callback_data="category_labor")],
                [InlineKeyboardButton(text="❓ Другое", callback_data="category_other_individual")]
            ])
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Регистрация бизнеса", callback_data="category_business_reg")],
                [InlineKeyboardButton(text="📝 Договоры и споры", callback_data="category_contracts")],
                [InlineKeyboardButton(text="👷 Трудовые вопросы", callback_data="category_labor_issues")],
                [InlineKeyboardButton(text="💰 Налоги и штрафы", callback_data="category_taxes")],
                [InlineKeyboardButton(text="❓ Другое", callback_data="category_other_business")]
            ])

        await self.bot.send_message(
            chat_id=user_id,
            text="Выберите категорию вопроса:",
            reply_markup=keyboard
        )

    async def consent_refusal_handler(self, user_id: str, state: FSMContext):
        """Обработка отказа от согласия"""
        await self.send_refusal_application(user_id)
        await state.clear()
        self.user_data[user_id] = {}

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="☎️ Позвонить: 8-495-999-85-89", callback_data="call_phone")],
            [InlineKeyboardButton(text="↩️ Дать согласие и оставить заявку", callback_data="retry_consent")]
        ])

        await self.bot.send_message(
            chat_id=user_id,
            text="😔 Мы уважаем ваше решение и соблюдаем закон о защите персональных данных.\n\n"
                 "Без согласия на обработку ПД мы не можем продолжить стандартный процесс консультации.\n\n"
                 "Но это не означает, что мы не можем вам помочь! 💪\n\n"
                 "Выберите один из вариантов:\n"
                 "• Позвоните нам по номеру 8-495-999-85-89 и получите бесплатную консультацию\n"
                 "• Или дайте согласие и оставьте заявку через бота",
            reply_markup=keyboard,
            format="markdown"
        )

    async def send_refusal_application(self, user_id: str):
        """Отправить заявку об отказе админу"""
        try:
            message_text = (
                f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
                f"{'━' * 30}\n"
                f"Пользователь отказал в согласии на обработку персональных данных.\n"
                f"Мы соблюдаем законодательство и не собираем данные без согласия.\n"
                f"\n👤 ID пользователя: {user_id}\n"
                f"\n⚠️ ДЕЙСТВИЕ: Позволить пользователю позвонить самостоятельно\n"
                f"на номер 8-495-999-85-89 для консультации.\n"
                f"\n📲 Источник: Max\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"{'━' * 30}"
            )
            await self.bot.send_message(MAX_ADMIN_USER_ID, message_text)
            logger.info(f"✓ Заявка об отказе отправлена в чат")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки заявки об отказе: {e}")

    async def submit_application(self, user_id: str, description=None, state: FSMContext = None):
        """Отправить заявку"""
        data = self.user_data[user_id]
        name = data['name']

        # Сохранить в БД
        await db.save_application(
            name=data['name'],
            phone=data['phone'],
            client_type=data['client_type'],
            category=data['category'],
            description=description,
            source="Max",
            consent_pd=data['consent_pd'],
            consent_policy=data['consent_policy']
        )

        # Отправить благодарность
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Записаться на консультацию", callback_data="record")]
        ])

        await self.bot.send_message(
            chat_id=user_id,
            text=f"✅ Спасибо, {name}! Заявка принята.\n"
                 f"Наш специалист свяжется с вами в ближайшее время.",
            reply_markup=keyboard
        )

        # Отправить в рабочий чат
        await self.send_to_work_chat(data, description)

        # Очистить состояние и данные
        if state:
            await state.clear()
        if user_id in self.user_data:
            del self.user_data[user_id]

    async def send_to_work_chat(self, data: dict, description: str = None):
        """Отправить заявку в рабочий чат"""
        try:
            message_text = (
                f"🔔 НОВАЯ ЗАЯВКА\n"
                f"{'━' * 30}\n"
                f"👤 Имя: {data['name']}\n"
                f"📱 Телефон: {data['phone']}\n"
                f"🏷️ Тип: {data['client_type']}\n"
                f"📂 Категория: {data['category']}\n"
            )
            if description:
                message_text += f"💬 Суть: {description}\n"

            message_text += (
                f"\n✅ Согласия:\n"
                f"  • Обработка ПД: {'✅ Да' if data['consent_pd'] else '❌ Нет'}\n"
                f"  • Политика обработки: {'✅ Да' if data['consent_policy'] else '❌ Нет'}\n"
                f"\n📲 Источник: Max\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"{'━' * 30}"
            )
            await self.bot.send_message(MAX_ADMIN_USER_ID, message_text)
            logger.info(f"✓ Заявка отправлена в чат")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки в чат: {e}")

    async def start(self):
        """Запустить бота"""
        logger.info("Max бот-секретарь запущен и слушает команды")
        await self.dp.start_polling()

max_bot = MaxSecretaryBot()

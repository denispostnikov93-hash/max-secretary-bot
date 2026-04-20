"""
Max бот-секретарь — приём заявок на консультации
Использует Long Polling (официальное API Max Messenger)
"""
import logging
import re
from datetime import datetime
from maxapi import Bot, Dispatcher, types
from maxapi.types import Update

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)


class MaxSecretaryBot:
    def __init__(self):
        self.bot = Bot(token=MAX_BOT_TOKEN)
        self.dp = Dispatcher(self.bot)
        self.admin_id = MAX_ADMIN_USER_ID

        self.user_data = {}
        self.user_states = {}

        logger.info(f"🔐 MAX_BOT_TOKEN установлен: {bool(MAX_BOT_TOKEN)}")
        logger.info(f"👤 MAX_ADMIN_USER_ID: {self.admin_id}")

        self._setup_handlers()

    def validate_phone(self, phone: str) -> bool:
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        return bool(
            re.match(r'^\+?7\d{9,10}$', cleaned) or
            re.match(r'^\+?\d{10,15}$', cleaned)
        )

    # ===== КЛАВИАТУРЫ =====

    def _get_buttons_main(self):
        return [[types.Button(
            text="📝 Записаться на консультацию",
            callback_id="record"
        )]]

    def _get_buttons_consent(self):
        return [
            [types.Button(text="✅ Согласен на обработку персональных данных", callback_id="consent_pd")],
            [types.Button(text="✅ Ознакомлен с политикой обработки данных", callback_id="consent_policy")],
            [types.Button(text="❌ Отказать в согласии", callback_id="refuse")]
        ]

    def _get_buttons_client_type(self):
        return [[
            types.Button(text="👤 Физическое лицо", callback_id="physical"),
            types.Button(text="🏢 Юридическое лицо", callback_id="legal")
        ]]

    def _get_buttons_individual_categories(self):
        return [
            [types.Button(text="🚗 ДТП", callback_id="cat_dtp")],
            [types.Button(text="👨‍👩‍👧 Семейное право", callback_id="cat_family")],
            [types.Button(text="🏠 Недвижимость", callback_id="cat_realty")],
            [types.Button(text="⚖️ Трудовые споры", callback_id="cat_work")],
            [types.Button(text="❓ Другое", callback_id="cat_other")]
        ]

    def _get_buttons_business_categories(self):
        return [
            [types.Button(text="📋 Регистрация бизнеса", callback_id="cat_reg")],
            [types.Button(text="📝 Договоры и споры", callback_id="cat_contracts")],
            [types.Button(text="👔 Трудовые вопросы", callback_id="cat_hr")],
            [types.Button(text="💰 Налоги и штрафы", callback_id="cat_tax")],
            [types.Button(text="❓ Другое", callback_id="cat_other")]
        ]

    def _get_buttons_description(self):
        return [[
            types.Button(text="✏️ Написать", callback_id="write_desc"),
            types.Button(text="➡️ Пропустить", callback_id="skip_desc")
        ]]

    def _get_buttons_refusal(self):
        return [
            [types.Button(text="☎️ Позвонить: 8-495-999-85-89", callback_id="call")],
            [types.Button(text="↩️ Дать согласие и оставить заявку", callback_id="back_consent")]
        ]

    # ===== ОБРАБОТЧИКИ =====

    def _setup_handlers(self):
        @self.dp.message_created()
        async def handle_message(update: Update):
            user_id = str(update.message.sender.user_id)
            text = update.message.body.text if update.message.body and hasattr(update.message.body, 'text') else ""

            if not text:
                return

            text = text.strip()
            logger.info(f"📨 Текст от {user_id}: {text[:50]}")

            # /start
            if text == "/start":
                self.user_data[user_id] = {
                    'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                    'client_type': None, 'category': None, 'name': None, 'phone': None
                }
                self.user_states[user_id] = None
                await self.bot.send_message(
                    chat_id=user_id,
                    text="👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
                         "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_main()}
                    )]
                )
                return

            # /my_id
            if text == "/my_id":
                await self.bot.send_message(
                    chat_id=user_id,
                    text=f"ℹ️ Ваш Max ID: `{user_id}`"
                )
                return

            # Инициализация если нет
            if user_id not in self.user_data:
                self.user_data[user_id] = {
                    'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                    'client_type': None, 'category': None, 'name': None, 'phone': None
                }

            # Ожидание имени
            if self.user_states.get(user_id) == "waiting_name":
                self.user_data[user_id]['name'] = text
                self.user_states[user_id] = "waiting_phone"
                await self.bot.send_message(
                    chat_id=user_id,
                    text="Ваш номер телефона?"
                )
                return

            # Ожидание номера телефона
            if self.user_states.get(user_id) == "waiting_phone":
                if not self.validate_phone(text):
                    await self.bot.send_message(
                        chat_id=user_id,
                        text="❌ Пожалуйста, введите корректный номер телефона.\nПримеры: +7 999 123-45-67 или 79991234567"
                    )
                    return

                self.user_data[user_id]['phone'] = text
                self.user_states[user_id] = "waiting_description_choice"
                await self.bot.send_message(
                    chat_id=user_id,
                    text="Кратко опишите ситуацию (необязательно):",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_description()}
                    )]
                )
                return

            # Ожидание описания
            if self.user_states.get(user_id) == "waiting_description":
                await self.submit_application(user_id, description=text)
                return

        @self.dp.callback_query()
        async def handle_callback(update: Update):
            user_id = str(update.callback.user.user_id)
            payload = update.callback.payload

            logger.info(f"📘 Callback от {user_id}: {payload}")

            # Инициализация если нет
            if user_id not in self.user_data:
                self.user_data[user_id] = {
                    'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                    'client_type': None, 'category': None, 'name': None, 'phone': None
                }

            # Запись на консультацию
            if payload == "record":
                self.user_data[user_id]['in_consent_step'] = True
                await self.bot.send_message(
                    chat_id=user_id,
                    text=f"📋 Чтобы продолжить, прочитайте и подтвердите:\n\n"
                         f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                         f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                         f"Нажмите обе кнопки ниже для подтверждения:",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_consent()}
                    )]
                )
                return

            # Согласие ПД
            if payload == "consent_pd":
                if self.user_data[user_id].get('in_consent_step'):
                    self.user_data[user_id]['consent_pd'] = True
                    await self._check_consents(user_id)
                return

            # Согласие политика
            if payload == "consent_policy":
                if self.user_data[user_id].get('in_consent_step'):
                    self.user_data[user_id]['consent_policy'] = True
                    await self._check_consents(user_id)
                return

            # Отказ
            if payload == "refuse":
                await self._send_refusal_notification(user_id)
                self.user_states[user_id] = None
                self.user_data[user_id] = {}
                await self.bot.send_message(
                    chat_id=user_id,
                    text="😔 Мы уважаем ваше решение и соблюдаем закон о защите персональных данных.\n\n"
                         "Без согласия на обработку ПД мы не можем продолжить стандартный процесс консультации.\n\n"
                         "Выберите один из вариантов:\n"
                         "• Позвоните нам по номеру 8-495-999-85-89 и получите бесплатную консультацию\n"
                         "• Или дайте согласие и оставьте заявку через бота",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_refusal()}
                    )]
                )
                return

            # Тип клиента
            if payload == "physical":
                self.user_data[user_id]['client_type'] = "Физическое лицо"
                self.user_states[user_id] = "waiting_category"
                await self.bot.send_message(
                    chat_id=user_id,
                    text="Выберите категорию вопроса:",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_individual_categories()}
                    )]
                )
                return

            if payload == "legal":
                self.user_data[user_id]['client_type'] = "Юридическое лицо"
                self.user_states[user_id] = "waiting_category"
                await self.bot.send_message(
                    chat_id=user_id,
                    text="Выберите категорию вопроса:",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_business_categories()}
                    )]
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
                self.user_data[user_id]['category'] = cat_map[payload]
                self.user_states[user_id] = "waiting_name"
                await self.bot.send_message(
                    chat_id=user_id,
                    text="Как вас зовут?"
                )
                return

            # Описание
            if payload == "write_desc":
                self.user_states[user_id] = "waiting_description"
                await self.bot.send_message(
                    chat_id=user_id,
                    text="Опишите вашу ситуацию:"
                )
                return

            if payload == "skip_desc":
                await self.submit_application(user_id, description=None)
                return

            if payload == "call":
                await self.bot.send_message(
                    chat_id=user_id,
                    text="✅ Спасибо! Ждем вашего звонка.\n\n"
                         "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_main()}
                    )]
                )
                return

            if payload == "back_consent":
                self.user_data[user_id] = {
                    'consent_pd': False, 'consent_policy': False, 'in_consent_step': True,
                    'client_type': None, 'category': None, 'name': None, 'phone': None
                }
                await self.bot.send_message(
                    chat_id=user_id,
                    text=f"📋 Чтобы продолжить, прочитайте и подтвердите:\n\n"
                         f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                         f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                         f"Нажмите обе кнопки ниже для подтверждения:",
                    attachments=[types.Attachment(
                        type="inline_keyboard",
                        payload={"buttons": self._get_buttons_consent()}
                    )]
                )
                return

    async def _check_consents(self, user_id: str):
        data = self.user_data[user_id]
        if data['consent_pd'] and data['consent_policy']:
            data['in_consent_step'] = False
            self.user_states[user_id] = "waiting_client_type"
            await self.bot.send_message(
                chat_id=user_id,
                text="✅ Спасибо! Теперь выберите тип клиента:",
                attachments=[types.Attachment(
                    type="inline_keyboard",
                    payload={"buttons": self._get_buttons_client_type()}
                )]
            )

    async def _send_refusal_notification(self, user_id: str):
        try:
            phone = self.user_data.get(user_id, {}).get('phone', 'Не указан')
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
            await self.bot.send_message(chat_id=str(self.admin_id), text=message)
            logger.info(f"✓ Уведомление об отказе отправлено")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки уведомления: {e}")

    async def submit_application(self, user_id: str, description=None):
        data = self.user_data[user_id]
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

        await self.bot.send_message(
            chat_id=user_id,
            text=f"✅ Спасибо, {name}! Заявка принята.\n"
                 f"Наш специалист свяжется с вами в ближайшее время.",
            attachments=[types.Attachment(
                type="inline_keyboard",
                payload={"buttons": self._get_buttons_main()}
            )]
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
            await self.bot.send_message(chat_id=str(self.admin_id), text=message)
            logger.info(f"✓ Уведомление о заявке отправлено")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки уведомления: {e}")

        self.user_states[user_id] = None
        if user_id in self.user_data:
            del self.user_data[user_id]

    async def start_polling(self):
        """Запустить long polling"""
        logger.info("🤖 Запускаю Max бота с long polling...")
        try:
            await self.dp.start_polling(self.bot)
        except KeyboardInterrupt:
            logger.info("⏹️ Бот остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка polling: {e}")
            import traceback
            logger.error(traceback.format_exc())


# Глобальный экземпляр
max_bot_instance = None


async def init_bot():
    global max_bot_instance
    max_bot_instance = MaxSecretaryBot()
    return max_bot_instance

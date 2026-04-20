"""
Max бот-секретарь для приема заявок
Использует umaxbot (aiogram-style async framework)
"""
import logging
import re
from datetime import datetime
from umaxbot import Bot, Router, types
from umaxbot.filters import Command
from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)

class MaxSecretaryBot:
    def __init__(self):
        self.bot = Bot(token=MAX_BOT_TOKEN)
        self.router = Router()
        self.setup_handlers()
        self.user_data = {}
        self.user_states = {}

    def setup_handlers(self):
        """Настроить обработчики сообщений"""
        @self.router.message()
        async def handle_message(message: types.Message):
            user_id = str(message.from_id)
            text = (message.text or "").strip()

            if not user_id or not text:
                return

            logger.info(f"User {user_id}: {text[:50]}")

            try:
                # /start команда
                if text == "/start":
                    await self.cmd_start(user_id)
                # Согласия
                elif text == "Согласен на обработку ПД":
                    await self.consent_pd_handler(user_id)
                elif text == "Ознакомлен с политикой":
                    await self.consent_policy_handler(user_id)
                elif text == "Отказать":
                    await self.consent_refusal_handler(user_id)
                # Запись на консультацию
                elif text == "Записаться на консультацию":
                    await self.btn_record(user_id)
                # Тип клиента
                elif self.user_states.get(user_id) == "waiting_client_type" and text in ["Физическое лицо", "Юридическое лицо"]:
                    await self.client_type_handler(user_id, text)
                # Категория
                elif self.user_states.get(user_id) == "waiting_category":
                    await self.category_handler(user_id, text)
                # Имя
                elif self.user_states.get(user_id) == "waiting_name":
                    await self.name_handler(user_id, text)
                # Телефон
                elif self.user_states.get(user_id) == "waiting_phone":
                    await self.phone_handler(user_id, text)
                # Описание - выбор
                elif self.user_states.get(user_id) == "waiting_description_choice" and text in ["Написать", "Пропустить"]:
                    await self.description_choice_handler(user_id, text)
                # Описание - текст
                elif self.user_states.get(user_id) == "waiting_description":
                    await self.description_handler(user_id, text)
                # Обработка отказа
                elif text == "Позвонить":
                    await self.phone_refusal_handler(user_id)
                elif text == "Дать согласие":
                    await self.return_consent_handler(user_id)
                else:
                    logger.warning(f"Unhandled message from {user_id}: '{text}' in state {self.user_states.get(user_id)}")

            except Exception as e:
                logger.error(f"❌ Ошибка: {e}", exc_info=True)
                await self.send_message(user_id, "❌ Ошибка. Повторите попытку.")

    def validate_phone(self, phone: str) -> bool:
        """Проверить корректность номера телефона"""
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        if re.match(r'^\+?7\d{9,10}$', cleaned) or re.match(r'^\+?\d{10,15}$', cleaned):
            return True
        return False

    async def cmd_start(self, user_id: str):
        """Команда /start"""
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
        self.user_states[user_id] = None

        keyboard = {
            "buttons": [
                [{"text": "Записаться на консультацию", "type": "default"}]
            ]
        }

        await self.send_message(
            user_id,
            "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
            "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
            keyboard
        )

    async def btn_record(self, user_id: str):
        """Нажата кнопка 'Записаться на консультацию'"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'consent_pd': False,
                'consent_policy': False,
                'in_consent_step': True
            }

        self.user_data[user_id]['in_consent_step'] = True
        logger.info(f"User {user_id} started application process")

        keyboard = {
            "buttons": [
                [{"text": "Согласен на обработку ПД", "type": "default"}],
                [{"text": "Ознакомлен с политикой", "type": "default"}],
                [{"text": "Отказать", "type": "default"}]
            ]
        }

        await self.send_message(
            user_id,
            f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
            f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
            f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
            f"Нажмите обе кнопки ниже для подтверждения:",
            keyboard
        )

    async def consent_pd_handler(self, user_id: str):
        """Согласие на обработку ПД"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {'consent_pd': False, 'consent_policy': False, 'in_consent_step': False}

        if self.user_data[user_id].get('in_consent_step'):
            self.user_data[user_id]['consent_pd'] = True
            logger.info(f"User {user_id} consented to data processing")
            await self.check_consents(user_id)

    async def consent_policy_handler(self, user_id: str):
        """Согласие с политикой"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {'consent_pd': False, 'consent_policy': False, 'in_consent_step': False}

        if self.user_data[user_id].get('in_consent_step'):
            self.user_data[user_id]['consent_policy'] = True
            logger.info(f"User {user_id} consented to policy")
            await self.check_consents(user_id)

    async def consent_refusal_handler(self, user_id: str):
        """Обработка отказа от согласия"""
        await self.send_refusal_application(user_id)
        self.user_states[user_id] = None
        self.user_data[user_id] = {}

        keyboard = {
            "buttons": [
                [{"text": "Позвонить", "type": "default"}],
                [{"text": "Дать согласие", "type": "default"}]
            ]
        }

        await self.send_message(
            user_id,
            "😔 Мы уважаем ваше решение и соблюдаем закон о защите персональных данных.\n\n"
            "Без согласия на обработку ПД мы не можем продолжить стандартный процесс консультации.\n\n"
            "Но это не означает, что мы не можем вам помочь! 💪\n\n"
            "Выберите один из вариантов:\n"
            "• Позвоните нам по номеру 8-495-999-85-89 и получите бесплатную консультацию\n"
            "• Или дайте согласие и оставьте заявку через бота",
            keyboard
        )

    async def phone_refusal_handler(self, user_id: str):
        """Обработка позвонить после отказа"""
        keyboard = {
            "buttons": [
                [{"text": "Записаться на консультацию", "type": "default"}]
            ]
        }

        await self.send_message(
            user_id,
            "✅ Спасибо! Ждем вашего звонка.\n\n"
            "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.",
            keyboard
        )

    async def return_consent_handler(self, user_id: str):
        """Вернуться к согласиям"""
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

        keyboard = {
            "buttons": [
                [{"text": "Согласен на обработку ПД", "type": "default"}],
                [{"text": "Ознакомлен с политикой", "type": "default"}],
                [{"text": "Отказать", "type": "default"}]
            ]
        }

        await self.send_message(
            user_id,
            f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
            f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
            f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
            f"Нажмите обе кнопки ниже для подтверждения:",
            keyboard
        )

    async def send_refusal_application(self, user_id: str):
        """Отправить заявку об отказе админу"""
        try:
            message_text = (
                f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
                f"{'━' * 30}\n"
                f"Пользователь отказал в согласии.\n"
                f"👤 ID: {user_id}\n"
                f"📲 Источник: Max\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"{'━' * 30}"
            )
            await self.bot.send_message(MAX_ADMIN_USER_ID, message_text)
            logger.info(f"✓ Заявка об отказе отправлена")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки заявки об отказе: {e}")

    async def check_consents(self, user_id: str):
        """Проверить оба согласия"""
        if self.user_data[user_id]['consent_pd'] and self.user_data[user_id]['consent_policy']:
            self.user_data[user_id]['in_consent_step'] = False
            logger.info(f"User {user_id} passed consent step")
            self.user_states[user_id] = "waiting_client_type"

            keyboard = {
                "buttons": [
                    [{"text": "Физическое лицо", "type": "default"}, {"text": "Юридическое лицо", "type": "default"}]
                ]
            }

            await self.send_message(
                user_id,
                "✅ Спасибо! Теперь выберите тип клиента:",
                keyboard
            )
        else:
            confirmed_count = sum([self.user_data[user_id]['consent_pd'], self.user_data[user_id]['consent_policy']])
            if confirmed_count == 1:
                remaining = []
                if not self.user_data[user_id]['consent_pd']:
                    remaining.append("согласие на обработку персональных данных")
                if not self.user_data[user_id]['consent_policy']:
                    remaining.append("ознакомление с политикой обработки данных")

                await self.send_message(
                    user_id,
                    f"✅ Отлично! Вы подтвердили 1 из 2 согласий.\n\n"
                    f"Осталось подтвердить:\n"
                    f"✓ {remaining[0]}"
                )

    async def client_type_handler(self, user_id: str, text: str):
        """Выбор типа клиента"""
        self.user_data[user_id]['client_type'] = text
        self.user_states[user_id] = "waiting_category"

        if "Физическое" in text:
            keyboard = {
                "buttons": [
                    [{"text": "ДТП", "type": "default"}],
                    [{"text": "Семейное право", "type": "default"}],
                    [{"text": "Недвижимость", "type": "default"}],
                    [{"text": "Трудовые споры", "type": "default"}],
                    [{"text": "Другое", "type": "default"}]
                ]
            }
        else:
            keyboard = {
                "buttons": [
                    [{"text": "Регистрация бизнеса", "type": "default"}],
                    [{"text": "Договоры и споры", "type": "default"}],
                    [{"text": "Трудовые вопросы", "type": "default"}],
                    [{"text": "Налоги и штрафы", "type": "default"}],
                    [{"text": "Другое", "type": "default"}]
                ]
            }

        await self.send_message(user_id, "Выберите категорию вопроса:", keyboard)

    async def category_handler(self, user_id: str, text: str):
        """Обработить категорию"""
        self.user_data[user_id]['category'] = text
        self.user_states[user_id] = "waiting_name"
        await self.send_message(user_id, "Как вас зовут?")

    async def name_handler(self, user_id: str, text: str):
        """Обработать имя"""
        self.user_data[user_id]['name'] = text
        self.user_states[user_id] = "waiting_phone"
        await self.send_message(user_id, "Ваш номер телефона?")

    async def phone_handler(self, user_id: str, text: str):
        """Обработать телефон"""
        if not self.validate_phone(text):
            await self.send_message(
                user_id,
                "❌ Пожалуйста, введите корректный номер телефона.\n"
                "Примеры: +7 999 123-45-67 или 79991234567"
            )
            return

        self.user_data[user_id]['phone'] = text
        self.user_states[user_id] = "waiting_description_choice"

        keyboard = {
            "buttons": [
                [{"text": "Написать", "type": "default"}, {"text": "Пропустить", "type": "default"}]
            ]
        }

        await self.send_message(
            user_id,
            "Кратко опишите ситуацию (необязательно):",
            keyboard
        )

    async def description_choice_handler(self, user_id: str, text: str):
        """Выбор: написать или пропустить описание"""
        if text == "Написать":
            self.user_states[user_id] = "waiting_description"
            await self.send_message(user_id, "Опишите вашу ситуацию:")
        elif text == "Пропустить":
            await self.submit_application(user_id, description=None)

    async def description_handler(self, user_id: str, text: str):
        """Обработать описание"""
        await self.submit_application(user_id, description=text)

    async def submit_application(self, user_id: str, description=None):
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
        keyboard = {
            "buttons": [
                [{"text": "Записаться на консультацию", "type": "default"}]
            ]
        }

        await self.send_message(
            user_id,
            f"✅ Спасибо, {name}! Заявка принята.\n"
            f"Наш специалист свяжется с вами в ближайшее время.",
            keyboard
        )

        # Отправить в рабочий чат
        await self.send_to_work_chat(data, description)

        # Очистить состояние и данные
        self.user_states[user_id] = None
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

    async def send_message(self, user_id: str, text: str, keyboard=None):
        """Отправить сообщение"""
        try:
            kwargs = {"user_id": user_id, "text": text}
            if keyboard:
                kwargs["keyboard"] = keyboard
            await self.bot.send_message(**kwargs)
            logger.info(f"✓ Сообщение отправлено {user_id}")
            return True
        except Exception as e:
            logger.error(f"✗ Ошибка отправки: {e}")
            return False

    async def start(self):
        """Запустить бота"""
        logger.info("Max бот-секретарь запущен и слушает команды")
        self.bot.dispatcher.include_router(self.router)
        await self.bot.start_polling()

max_bot = MaxSecretaryBot()

"""
Max бот-секретарь для приема заявок
"""
import logging
import re
from aiomax import Bot, Router
from aiomax.types import Message
from datetime import datetime
from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)

class MaxSecretaryBot:
    def __init__(self):
        self.bot = Bot(access_token=MAX_BOT_TOKEN)
        self.router = Router()
        self.setup_handlers()
        self.user_data = {}
        self.user_states = {}

    def setup_handlers(self):
        """Настроить обработчики"""
        @self.router.on_message()
        async def handle_message(message: Message):
            user_id = message.from_id
            text = (message.text or "").strip()

            if not user_id or not text:
                return

            logger.info(f"User {user_id}: {text[:50]}")

            try:
                # /start команда
                if text == "/start":
                    await self.cmd_start(user_id)
                # Согласия
                elif text == "✅ Согласен на обработку персональных данных":
                    await self.consent_pd_handler(user_id)
                elif text == "✅ Ознакомлен с политикой обработки данных":
                    await self.consent_policy_handler(user_id)
                elif "Отказать" in text:
                    await self.consent_refusal_handler(user_id)
                # Запись на консультацию
                elif text == "📝 Записаться на консультацию":
                    await self.btn_record(user_id)
                # Тип клиента
                elif self.user_states.get(user_id) == "waiting_client_type" and text in ["👤 Физическое лицо", "🏢 Юридическое лицо"]:
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
                elif self.user_states.get(user_id) == "waiting_description_choice" and text in ["✏️ Написать", "➡️ Пропустить"]:
                    await self.description_choice_handler(user_id, text)
                # Описание - текст
                elif self.user_states.get(user_id) == "waiting_description":
                    await self.description_handler(user_id, text)
                # Обработка отказа - звонок или согласие
                elif "Позвонить" in text:
                    await self.phone_refusal_handler(user_id)
                elif "согласие и оставить" in text:
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

        await self.send_message(
            user_id,
            "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
            "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.\n\n"
            "📝 Записаться на консультацию"
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

        await self.send_message(
            user_id,
            f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
            f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
            f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
            f"Нажмите обе кнопки ниже для подтверждения:\n"
            f"✅ Согласен на обработку персональных данных\n"
            f"✅ Ознакомлен с политикой обработки данных\n"
            f"❌ Отказать в согласии"
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

        await self.send_message(
            user_id,
            "😔 Мы уважаем ваше решение и соблюдаем закон о защите персональных данных.\n\n"
            "Без согласия на обработку ПД мы не можем продолжить стандартный процесс консультации.\n\n"
            "Но это не означает, что мы не можем вам помочь! 💪\n\n"
            "Выберите один из вариантов:\n"
            "• Позвоните нам по номеру 8-495-999-85-89 и получите бесплатную консультацию\n"
            "• Или дайте согласие и оставьте заявку через бота\n\n"
            "☎️ Позвонить: 8-495-999-85-89\n"
            "↩️ Дать согласие и оставить заявку"
        )

    async def phone_refusal_handler(self, user_id: str):
        """Обработка позвонить после отказа"""
        await self.send_message(
            user_id,
            "✅ Спасибо! Ждем вашего звонка.\n\n"
            "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.\n\n"
            "📝 Записаться на консультацию"
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

        await self.send_message(
            user_id,
            f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
            f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
            f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
            f"Нажмите обе кнопки ниже для подтверждения:\n"
            f"✅ Согласен на обработку персональных данных\n"
            f"✅ Ознакомлен с политикой обработки данных\n"
            f"❌ Отказать в согласии"
        )

    async def send_refusal_application(self, user_id: str):
        """Отправить анонимную заявку об отказе в рабочий чат"""
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
            await self.bot.send_message(user_id=MAX_ADMIN_USER_ID, text=message_text)
            logger.info(f"✓ Заявка об отказе отправлена в чат")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки заявки об отказе: {e}")

    async def check_consents(self, user_id: str):
        """Проверить оба согласия"""
        if self.user_data[user_id]['consent_pd'] and self.user_data[user_id]['consent_policy']:
            self.user_data[user_id]['in_consent_step'] = False
            logger.info(f"User {user_id} passed consent step")
            self.user_states[user_id] = "waiting_client_type"
            await self.send_message(
                user_id,
                "✅ Спасибо! Теперь выберите тип клиента:\n"
                "👤 Физическое лицо\n"
                "🏢 Юридическое лицо"
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
        self.user_data[user_id]['client_type'] = text.replace("👤 ", "").replace("🏢 ", "")
        self.user_states[user_id] = "waiting_category"

        if "Физическое" in text:
            await self.send_message(
                user_id,
                "Выберите категорию вопроса:\n"
                "🚗 ДТП\n"
                "👨‍👩‍👧 Семейное право\n"
                "🏠 Недвижимость\n"
                "💼 Трудовые споры\n"
                "❓ Другое"
            )
        else:
            await self.send_message(
                user_id,
                "Выберите категорию вопроса:\n"
                "📋 Регистрация бизнеса\n"
                "📝 Договоры и споры\n"
                "👷 Трудовые вопросы\n"
                "💰 Налоги и штрафы\n"
                "❓ Другое"
            )

    async def category_handler(self, user_id: str, text: str):
        """Обработить категорию"""
        category = text.lstrip("🚗👨‍👩‍👧🏠💼📋📝👷💰❓ ")
        self.user_data[user_id]['category'] = category

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
        await self.send_message(
            user_id,
            "Кратко опишите ситуацию (необязательно):\n"
            "✏️ Написать\n"
            "➡️ Пропустить"
        )

    async def description_choice_handler(self, user_id: str, text: str):
        """Выбор: написать или пропустить описание"""
        if text == "✏️ Написать":
            self.user_states[user_id] = "waiting_description"
            await self.send_message(user_id, "Опишите вашу ситуацию:")
        elif text == "➡️ Пропустить":
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
        await self.send_message(
            user_id,
            f"✅ Спасибо, {name}! Заявка принята.\n"
            f"Наш специалист свяжется с вами в ближайшее время.\n\n"
            f"📝 Записаться на консультацию"
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
            )

            message_text += (
                f"\n📲 Источник: Max\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"{'━' * 30}"
            )
            await self.bot.send_message(user_id=MAX_ADMIN_USER_ID, text=message_text)
            logger.info(f"✓ Заявка отправлена в чат")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки в чат: {e}")

    async def send_message(self, user_id: str, text: str):
        """Отправить сообщение"""
        try:
            await self.bot.send_message(user_id=user_id, text=text)
            logger.info(f"✓ Сообщение отправлено {user_id}")
            return True
        except Exception as e:
            logger.error(f"✗ Ошибка отправки: {e}")
            return False

    async def start(self):
        """Запустить бота"""
        logger.info("Max бот-секретарь запущен и слушает команды")
        self.bot.add_router(self.router)
        await self.bot.start_polling()

max_bot = MaxSecretaryBot()

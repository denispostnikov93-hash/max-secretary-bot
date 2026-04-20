"""
Max бот-секретарь — приём заявок на консультации
Использует Long Polling с max-bot-api-client
"""
import logging
import re
import asyncio
from datetime import datetime
from max_client import MaxClient, BotsApi, SubscriptionsApi
from max_client.models import (
    MessageCreateRequest, TextMessage, Button, AttachmentV2,
    InlineKeyboardAttachment, MessageSendResponse
)

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)


class MaxSecretaryBot:
    def __init__(self):
        self.token = MAX_BOT_TOKEN
        self.admin_id = int(MAX_ADMIN_USER_ID) if isinstance(MAX_ADMIN_USER_ID, str) else MAX_ADMIN_USER_ID

        # Инициализация клиента
        self.client = MaxClient(access_token=self.token)
        self.bots_api = BotsApi(self.client)
        self.subs_api = SubscriptionsApi(self.client)

        self.user_data = {}
        self.user_states = {}

        logger.info(f"🔐 MAX_BOT_TOKEN установлен: {bool(self.token)}")
        logger.info(f"👤 MAX_ADMIN_USER_ID: {self.admin_id}")

    def validate_phone(self, phone: str) -> bool:
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        return bool(
            re.match(r'^\+?7\d{9,10}$', cleaned) or
            re.match(r'^\+?\d{10,15}$', cleaned)
        )

    # ===== КЛАВИАТУРЫ =====

    def _get_buttons_main(self):
        return [[Button(text="📝 Записаться на консультацию", payload="record")]]

    def _get_buttons_consent(self):
        return [
            [Button(text="✅ Согласен на обработку персональных данных", payload="consent_pd")],
            [Button(text="✅ Ознакомлен с политикой обработки данных", payload="consent_policy")],
            [Button(text="❌ Отказать в согласии", payload="refuse")]
        ]

    def _get_buttons_client_type(self):
        return [[
            Button(text="👤 Физическое лицо", payload="physical"),
            Button(text="🏢 Юридическое лицо", payload="legal")
        ]]

    def _get_buttons_individual_categories(self):
        return [
            [Button(text="🚗 ДТП", payload="cat_dtp")],
            [Button(text="👨‍👩‍👧 Семейное право", payload="cat_family")],
            [Button(text="🏠 Недвижимость", payload="cat_realty")],
            [Button(text="⚖️ Трудовые споры", payload="cat_work")],
            [Button(text="❓ Другое", payload="cat_other")]
        ]

    def _get_buttons_business_categories(self):
        return [
            [Button(text="📋 Регистрация бизнеса", payload="cat_reg")],
            [Button(text="📝 Договоры и споры", payload="cat_contracts")],
            [Button(text="👔 Трудовые вопросы", payload="cat_hr")],
            [Button(text="💰 Налоги и штрафы", payload="cat_tax")],
            [Button(text="❓ Другое", payload="cat_other")]
        ]

    def _get_buttons_description(self):
        return [[
            Button(text="✏️ Написать", payload="write_desc"),
            Button(text="➡️ Пропустить", payload="skip_desc")
        ]]

    def _get_buttons_refusal(self):
        return [
            [Button(text="☎️ Позвонить: 8-495-999-85-89", payload="call")],
            [Button(text="↩️ Дать согласие и оставить заявку", payload="back_consent")]
        ]

    async def send_message(self, user_id: int, text: str, buttons=None):
        """Отправить сообщение с опциональной клавиатурой"""
        try:
            message = TextMessage(text=text)
            attachments = []

            if buttons:
                keyboard = InlineKeyboardAttachment(buttons=buttons)
                attachments.append(AttachmentV2(type="inline_keyboard", payload=keyboard))

            request = MessageCreateRequest(
                recipient={"user_id": user_id},
                text=text,
                attachments=attachments if attachments else None
            )

            await self.bots_api.send_message(request)
            logger.info(f"✓ Сообщение отправлено {user_id}")
            return True
        except Exception as e:
            logger.error(f"✗ Ошибка отправки: {e}")
            return False

    async def handle_message(self, user_id: int, text: str):
        """Обработать текстовое сообщение"""
        if not text:
            return

        text = text.strip()
        logger.info(f"📨 Текст от {user_id}: {text[:50]}")

        # /start
        if text == "/start":
            self.user_data[str(user_id)] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None
            }
            self.user_states[str(user_id)] = None
            await self.send_message(
                user_id,
                "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
                "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
                self._get_buttons_main()
            )
            return

        # /my_id
        if text == "/my_id":
            await self.send_message(user_id, f"ℹ️ Ваш Max ID: `{user_id}`")
            return

        user_id_str = str(user_id)
        if user_id_str not in self.user_data:
            self.user_data[user_id_str] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None
            }

        # Ожидание имени
        if self.user_states.get(user_id_str) == "waiting_name":
            self.user_data[user_id_str]['name'] = text
            self.user_states[user_id_str] = "waiting_phone"
            await self.send_message(user_id, "Ваш номер телефона?")
            return

        # Ожидание номера телефона
        if self.user_states.get(user_id_str) == "waiting_phone":
            if not self.validate_phone(text):
                await self.send_message(
                    user_id,
                    "❌ Пожалуйста, введите корректный номер телефона.\n"
                    "Примеры: +7 999 123-45-67 или 79991234567"
                )
                return

            self.user_data[user_id_str]['phone'] = text
            self.user_states[user_id_str] = "waiting_description_choice"
            await self.send_message(
                user_id,
                "Кратко опишите ситуацию (необязательно):",
                self._get_buttons_description()
            )
            return

        # Ожидание описания
        if self.user_states.get(user_id_str) == "waiting_description":
            await self.submit_application(user_id, description=text)
            return

    async def handle_callback(self, user_id: int, payload: str):
        """Обработить нажатие на кнопку"""
        logger.info(f"📘 Callback от {user_id}: {payload}")

        user_id_str = str(user_id)
        if user_id_str not in self.user_data:
            self.user_data[user_id_str] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None
            }

        # Запись на консультацию
        if payload == "record":
            self.user_data[user_id_str]['in_consent_step'] = True
            await self.send_message(
                user_id,
                f"📋 Чтобы продолжить, прочитайте и подтвердите:\n\n"
                f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                f"Нажмите обе кнопки ниже для подтверждения:",
                self._get_buttons_consent()
            )
            return

        # Согласие ПД
        if payload == "consent_pd":
            if self.user_data[user_id_str].get('in_consent_step'):
                self.user_data[user_id_str]['consent_pd'] = True
                await self._check_consents(user_id)
            return

        # Согласие политика
        if payload == "consent_policy":
            if self.user_data[user_id_str].get('in_consent_step'):
                self.user_data[user_id_str]['consent_policy'] = True
                await self._check_consents(user_id)
            return

        # Отказ
        if payload == "refuse":
            await self._send_refusal_notification(user_id)
            self.user_states[user_id_str] = None
            self.user_data[user_id_str] = {}
            await self.send_message(
                user_id,
                "😔 Мы уважаем ваше решение и соблюдаем закон о защите персональных данных.\n\n"
                "Без согласия на обработку ПД мы не можем продолжить стандартный процесс консультации.\n\n"
                "Выберите один из вариантов:\n"
                "• Позвоните нам по номеру 8-495-999-85-89 и получите бесплатную консультацию\n"
                "• Или дайте согласие и оставьте заявку через бота",
                self._get_buttons_refusal()
            )
            return

        # Тип клиента
        if payload == "physical":
            self.user_data[user_id_str]['client_type'] = "Физическое лицо"
            self.user_states[user_id_str] = "waiting_category"
            await self.send_message(
                user_id,
                "Выберите категорию вопроса:",
                self._get_buttons_individual_categories()
            )
            return

        if payload == "legal":
            self.user_data[user_id_str]['client_type'] = "Юридическое лицо"
            self.user_states[user_id_str] = "waiting_category"
            await self.send_message(
                user_id,
                "Выберите категорию вопроса:",
                self._get_buttons_business_categories()
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
            self.user_data[user_id_str]['category'] = cat_map[payload]
            self.user_states[user_id_str] = "waiting_name"
            await self.send_message(user_id, "Как вас зовут?")
            return

        # Описание
        if payload == "write_desc":
            self.user_states[user_id_str] = "waiting_description"
            await self.send_message(user_id, "Опишите вашу ситуацию:")
            return

        if payload == "skip_desc":
            await self.submit_application(user_id, description=None)
            return

        if payload == "call":
            await self.send_message(
                user_id,
                "✅ Спасибо! Ждем вашего звонка.\n\n"
                "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.",
                self._get_buttons_main()
            )
            return

        if payload == "back_consent":
            self.user_data[user_id_str] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': True,
                'client_type': None, 'category': None, 'name': None, 'phone': None
            }
            await self.send_message(
                user_id,
                f"📋 Чтобы продолжить, прочитайте и подтвердите:\n\n"
                f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                f"Нажмите обе кнопки ниже для подтверждения:",
                self._get_buttons_consent()
            )
            return

    async def _check_consents(self, user_id: int):
        user_id_str = str(user_id)
        data = self.user_data[user_id_str]
        if data['consent_pd'] and data['consent_policy']:
            data['in_consent_step'] = False
            self.user_states[user_id_str] = "waiting_client_type"
            await self.send_message(
                user_id,
                "✅ Спасибо! Теперь выберите тип клиента:",
                self._get_buttons_client_type()
            )

    async def _send_refusal_notification(self, user_id: int):
        try:
            user_id_str = str(user_id)
            phone = self.user_data.get(user_id_str, {}).get('phone', 'Не указан')
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
            await self.send_message(self.admin_id, message)
            logger.info(f"✓ Уведомление об отказе отправлено")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки уведомления: {e}")

    async def submit_application(self, user_id: int, description=None):
        user_id_str = str(user_id)
        data = self.user_data[user_id_str]
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

        await self.send_message(
            user_id,
            f"✅ Спасибо, {name}! Заявка принята.\n"
            f"Наш специалист свяжется с вами в ближайшее время.",
            self._get_buttons_main()
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
            await self.send_message(self.admin_id, message)
            logger.info(f"✓ Уведомление о заявке отправлено")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки уведомления: {e}")

        self.user_states[user_id_str] = None
        if user_id_str in self.user_data:
            del self.user_data[user_id_str]

    async def start_polling(self):
        """Запустить long polling"""
        logger.info("🚀 Запускаю Max бота (Long Polling)...")
        logger.info("=" * 60)

        last_update_id = 0

        try:
            while True:
                try:
                    # Получить новые обновления
                    updates = await self.subs_api.get_updates(limit=100, timeout=30, last_event_id=last_update_id)

                    if not updates:
                        await asyncio.sleep(1)
                        continue

                    logger.debug(f"📥 Получено {len(updates)} обновлений")

                    for update in updates:
                        try:
                            # Сохранить ID последнего обновления
                            if hasattr(update, 'event_id'):
                                last_update_id = update.event_id

                            # Обработать message_created
                            if hasattr(update, 'message') and update.message:
                                user_id = update.message.sender.user_id
                                text = update.message.body.text if hasattr(update.message.body, 'text') else ""
                                if text:
                                    await self.handle_message(user_id, text)

                            # Обработать message_callback (нажатие кнопки)
                            elif hasattr(update, 'callback') and update.callback:
                                user_id = update.callback.user.user_id
                                payload = update.callback.payload
                                if payload:
                                    await self.handle_callback(user_id, payload)

                        except Exception as e:
                            logger.error(f"❌ Ошибка обработки update: {e}")
                            continue

                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(f"❌ Ошибка при получении updates: {e}")
                    await asyncio.sleep(5)

        except KeyboardInterrupt:
            logger.info("⏹️ Бот остановлен")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            import traceback
            logger.error(traceback.format_exc())


max_bot_instance = None


async def init_bot():
    global max_bot_instance
    max_bot_instance = MaxSecretaryBot()
    return max_bot_instance

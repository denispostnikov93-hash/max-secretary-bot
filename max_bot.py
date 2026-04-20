"""
Max бот-секретарь - используя HTTP API Max напрямую
Полная функциональность как Telegram бот
"""
import logging
import re
import json
import asyncio
from datetime import datetime
from aiohttp import web
import aiohttp
from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)

class MaxSecretaryBot:
    def __init__(self):
        self.token = MAX_BOT_TOKEN
        self.admin_id = MAX_ADMIN_USER_ID
        self.api_url = "https://platform-api.max.ru"
        self.user_data = {}
        self.user_states = {}

    def validate_phone(self, phone: str) -> bool:
        """Проверить корректность номера телефона"""
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        if re.match(r'^\+?7\d{9,10}$', cleaned) or re.match(r'^\+?\d{10,15}$', cleaned):
            return True
        return False

    async def send_message(self, user_id: str, text: str, keyboard=None):
        """Отправить сообщение в Max"""
        try:
            payload = {
                "user_id": user_id,
                "text": text,
                "format": "markdown"
            }

            if keyboard:
                payload["attachments"] = [{
                    "type": "inline_keyboard",
                    "inline_keyboard": keyboard
                }]

            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.token}"}
                async with session.post(
                    f"{self.api_url}/messages",
                    json=payload,
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✓ Сообщение отправлено {user_id}")
                        return True
                    else:
                        logger.error(f"✗ Ошибка отправки: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"✗ Ошибка: {e}")
            return False

    async def handle_message(self, data: dict):
        """Обработать входящее сообщение"""
        try:
            user_id = data.get("from_id")
            text = data.get("text", "").strip()

            if not user_id or not text:
                return

            logger.info(f"User {user_id}: {text[:50]}")

            # /start команда
            if text == "/start":
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

                keyboard = [[{"text": "📝 Записаться на консультацию", "type": "message", "payload": "record"}]]

                await self.send_message(
                    user_id,
                    "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
                    "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
                    keyboard
                )

            # Запись на консультацию
            elif text == "Записаться на консультацию" or text == "record":
                if user_id not in self.user_data:
                    self.user_data[user_id] = {
                        'consent_pd': False,
                        'consent_policy': False,
                        'in_consent_step': True
                    }
                else:
                    self.user_data[user_id]['in_consent_step'] = True

                keyboard = [
                    [{"text": "✅ Согласен на обработку ПД", "type": "message"}],
                    [{"text": "✅ Ознакомлен с политикой", "type": "message"}],
                    [{"text": "❌ Отказать", "type": "message"}]
                ]

                await self.send_message(
                    user_id,
                    f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                    f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                    f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                    f"Нажмите обе кнопки ниже для подтверждения:",
                    keyboard
                )

            # Согласие на обработку ПД
            elif text == "Согласен на обработку ПД":
                if user_id in self.user_data and self.user_data[user_id].get('in_consent_step'):
                    self.user_data[user_id]['consent_pd'] = True
                    await self.check_consents(user_id)

            # Согласие с политикой
            elif text == "Ознакомлен с политикой":
                if user_id in self.user_data and self.user_data[user_id].get('in_consent_step'):
                    self.user_data[user_id]['consent_policy'] = True
                    await self.check_consents(user_id)

            # Отказать
            elif text == "Отказать":
                await self.send_refusal_application(user_id)
                self.user_states[user_id] = None
                self.user_data[user_id] = {}

                keyboard = [
                    [{"text": "☎️ Позвонить: 8-495-999-85-89", "type": "message"}],
                    [{"text": "↩️ Дать согласие и оставить заявку", "type": "message"}]
                ]

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

            # Тип клиента
            elif self.user_states.get(user_id) == "waiting_client_type":
                if text in ["Физическое лицо", "Юридическое лицо"]:
                    self.user_data[user_id]['client_type'] = text
                    self.user_states[user_id] = "waiting_category"

                    if "Физическое" in text:
                        keyboard = [
                            [{"text": "🚗 ДТП", "type": "message"}],
                            [{"text": "👨‍👩‍👧 Семейное право", "type": "message"}],
                            [{"text": "🏠 Недвижимость", "type": "message"}],
                            [{"text": "💼 Трудовые споры", "type": "message"}],
                            [{"text": "❓ Другое", "type": "message"}]
                        ]
                    else:
                        keyboard = [
                            [{"text": "📋 Регистрация бизнеса", "type": "message"}],
                            [{"text": "📝 Договоры и споры", "type": "message"}],
                            [{"text": "👷 Трудовые вопросы", "type": "message"}],
                            [{"text": "💰 Налоги и штрафы", "type": "message"}],
                            [{"text": "❓ Другое", "type": "message"}]
                        ]

                    await self.send_message(user_id, "Выберите категорию вопроса:", keyboard)

            # Категория
            elif self.user_states.get(user_id) == "waiting_category":
                self.user_data[user_id]['category'] = text
                self.user_states[user_id] = "waiting_name"
                await self.send_message(user_id, "Как вас зовут?")

            # Имя
            elif self.user_states.get(user_id) == "waiting_name":
                self.user_data[user_id]['name'] = text
                self.user_states[user_id] = "waiting_phone"
                await self.send_message(user_id, "Ваш номер телефона?")

            # Телефон
            elif self.user_states.get(user_id) == "waiting_phone":
                if not self.validate_phone(text):
                    await self.send_message(
                        user_id,
                        "❌ Пожалуйста, введите корректный номер телефона.\nПримеры: +7 999 123-45-67 или 79991234567"
                    )
                    return

                self.user_data[user_id]['phone'] = text
                self.user_states[user_id] = "waiting_description_choice"

                keyboard = [[
                    {"text": "✏️ Написать", "type": "message"},
                    {"text": "➡️ Пропустить", "type": "message"}
                ]]

                await self.send_message(
                    user_id,
                    "Кратко опишите ситуацию (необязательно):",
                    keyboard
                )

            # Описание - выбор
            elif self.user_states.get(user_id) == "waiting_description_choice":
                if text == "Написать":
                    self.user_states[user_id] = "waiting_description"
                    await self.send_message(user_id, "Опишите вашу ситуацию:")
                elif text == "Пропустить":
                    await self.submit_application(user_id, description=None)

            # Описание
            elif self.user_states.get(user_id) == "waiting_description":
                await self.submit_application(user_id, description=text)

            # Позвонить
            elif text == "Позвонить: 8-495-999-85-89":
                keyboard = [[{"text": "📝 Записаться на консультацию", "type": "message"}]]
                await self.send_message(
                    user_id,
                    "✅ Спасибо! Ждем вашего звонка.\n\n"
                    "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.",
                    keyboard
                )

            # Дать согласие
            elif text == "Дать согласие и оставить заявку":
                self.user_data[user_id] = {
                    'consent_pd': False,
                    'consent_policy': False,
                    'in_consent_step': True
                }

                keyboard = [
                    [{"text": "✅ Согласен на обработку ПД", "type": "message"}],
                    [{"text": "✅ Ознакомлен с политикой", "type": "message"}],
                    [{"text": "❌ Отказать", "type": "message"}]
                ]

                await self.send_message(
                    user_id,
                    f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                    f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                    f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                    f"Нажмите обе кнопки ниже для подтверждения:",
                    keyboard
                )

        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}", exc_info=True)

    async def check_consents(self, user_id: str):
        """Проверить оба согласия"""
        if self.user_data[user_id]['consent_pd'] and self.user_data[user_id]['consent_policy']:
            self.user_data[user_id]['in_consent_step'] = False
            self.user_states[user_id] = "waiting_client_type"

            keyboard = [[
                {"text": "👤 Физическое лицо", "type": "message"},
                {"text": "🏢 Юридическое лицо", "type": "message"}
            ]]

            await self.send_message(
                user_id,
                "✅ Спасибо! Теперь выберите тип клиента:",
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
            await self.send_message(self.admin_id, message_text)
            logger.info(f"✓ Заявка об отказе отправлена")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки заявки об отказе: {e}")

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
        keyboard = [[{"text": "📝 Записаться на консультацию", "type": "message"}]]

        await self.send_message(
            user_id,
            f"✅ Спасибо, {name}! Заявка принята.\n"
            f"Наш специалист свяжется с вами в ближайшее время.",
            keyboard
        )

        # Отправить в рабочий чат
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

        await self.send_message(self.admin_id, message_text)

        # Очистить состояние
        self.user_states[user_id] = None
        if user_id in self.user_data:
            del self.user_data[user_id]

max_bot = MaxSecretaryBot()

async def webhook_handler(request):
    """Обработать входящее сообщение через webhook"""
    try:
        data = await request.json()
        logger.info(f"📨 Webhook received: {data}")

        if data.get('type') == 'message':
            await max_bot.handle_message(data['data'])

        return web.json_response({'status': 'ok'})
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        return web.json_response({'status': 'error'}, status=400)

async def start_webhook():
    """Запустить webhook сервер"""
    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

    logger.info("✓ Webhook сервер запущен на порту 8080")
    return runner

async def startup():
    """Инициализация и запуск"""
    try:
        runner = await start_webhook()
        while True:
            await asyncio.sleep(3600)
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}", exc_info=True)
        raise

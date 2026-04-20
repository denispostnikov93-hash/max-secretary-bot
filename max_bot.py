"""
Max бот-секретарь — приём заявок на консультации
Webhook-based архитектура с callback-кнопками
"""
import logging
import re
import json
import asyncio
from datetime import datetime
from aiohttp import web
import aiohttp

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, WEBHOOK_URL, WEBHOOK_PORT
from config import PRIVACY_POLICY_URL, AGREEMENT_URL
from database import db

logger = logging.getLogger(__name__)


class MaxSecretaryBot:
    def __init__(self):
        self.token = MAX_BOT_TOKEN
        self.admin_id = MAX_ADMIN_USER_ID
        self.webhook_url = WEBHOOK_URL
        self.api_url = "https://platform-api.max.ru"
        self.user_data = {}
        self.user_states = {}

    def validate_phone(self, phone: str) -> bool:
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        return bool(
            re.match(r'^\+?7\d{9,10}$', cleaned) or
            re.match(r'^\+?\d{10,15}$', cleaned)
        )

    async def send_message(self, user_id: str, text: str, buttons=None):
        try:
            payload = {
                "recipient": {"user_id": user_id},
                "text": text,
                "format": "markdown"
            }
            if buttons:
                payload["attachments"] = [{
                    "type": "inline_keyboard",
                    "payload": {"buttons": buttons}
                }]

            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.token}"}
                async with session.post(
                    f"{self.api_url}/messages",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✓ Сообщение отправлено {user_id}")
                        return True
                    else:
                        text = await resp.text()
                        logger.error(f"✗ Max API ошибка {resp.status}: {text}")
                        return False
        except Exception as e:
            logger.error(f"✗ Ошибка отправки: {e}")
            return False

    async def subscribe_webhook(self):
        try:
            payload = {
                "url": self.webhook_url,
                "updates": ["message_created", "message_callback"]
            }
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.token}"}
                async with session.post(
                    f"{self.api_url}/subscriptions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status in [200, 201]:
                        logger.info(f"✅ Webhook подписка успешна: {self.webhook_url}")
                        return True
                    else:
                        logger.warning(f"⚠️ Webhook подписка: статус {resp.status}")
                        return False
        except Exception as e:
            logger.warning(f"⚠️ Ошибка подписки: {e}")
            return False

    # ===== КЛАВИАТУРЫ =====

    def _get_buttons_main(self):
        return [[{"type": "callback", "text": "📝 Записаться на консультацию", "payload": "record"}]]

    def _get_buttons_consent(self):
        return [
            [{"type": "callback", "text": "✅ Согласен на обработку персональных данных", "payload": "consent_pd"}],
            [{"type": "callback", "text": "✅ Ознакомлен с политикой обработки данных", "payload": "consent_policy"}],
            [{"type": "callback", "text": "❌ Отказать в согласии", "payload": "refuse"}]
        ]

    def _get_buttons_client_type(self):
        return [[
            {"type": "callback", "text": "👤 Физическое лицо", "payload": "physical"},
            {"type": "callback", "text": "🏢 Юридическое лицо", "payload": "legal"}
        ]]

    def _get_buttons_individual_categories(self):
        return [
            [{"type": "callback", "text": "🚗 ДТП", "payload": "cat_dtp"}],
            [{"type": "callback", "text": "👨‍👩‍👧 Семейное право", "payload": "cat_family"}],
            [{"type": "callback", "text": "🏠 Недвижимость", "payload": "cat_realty"}],
            [{"type": "callback", "text": "💼 Трудовые споры", "payload": "cat_work"}],
            [{"type": "callback", "text": "❓ Другое", "payload": "cat_other"}]
        ]

    def _get_buttons_business_categories(self):
        return [
            [{"type": "callback", "text": "📋 Регистрация бизнеса", "payload": "cat_reg"}],
            [{"type": "callback", "text": "📝 Договоры и споры", "payload": "cat_contracts"}],
            [{"type": "callback", "text": "👷 Трудовые вопросы", "payload": "cat_hr"}],
            [{"type": "callback", "text": "💰 Налоги и штрафы", "payload": "cat_tax"}],
            [{"type": "callback", "text": "❓ Другое", "payload": "cat_other"}]
        ]

    def _get_buttons_description(self):
        return [[
            {"type": "callback", "text": "✏️ Написать", "payload": "write_desc"},
            {"type": "callback", "text": "➡️ Пропустить", "payload": "skip_desc"}
        ]]

    def _get_buttons_refusal(self):
        return [
            [{"type": "callback", "text": "☎️ Позвонить: 8-495-999-85-89", "payload": "call"}],
            [{"type": "callback", "text": "↩️ Дать согласие и оставить заявку", "payload": "back_consent"}]
        ]

    # ===== ОБРАБОТЧИКИ =====

    async def handle_message(self, user_id: str, text: str):
        if not user_id or not text:
            return
        text = text.strip()
        logger.info(f"📨 Text от {user_id}: {text[:50]}")

        if text == "/start":
            self.user_data[user_id] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
            }
            self.user_states[user_id] = None
            await self.send_message(
                user_id,
                "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
                "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
                self._get_buttons_main()
            )
            return

        if text == "/my_id":
            await self.send_message(user_id, f"ℹ️ Ваш Max ID: `{user_id}`")
            return

        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
            }

        if self.user_states.get(user_id) == "waiting_name":
            self.user_data[user_id]['name'] = text
            self.user_states[user_id] = "waiting_phone"
            await self.send_message(user_id, "Ваш номер телефона?")
            return

        if self.user_states.get(user_id) == "waiting_phone":
            if not self.validate_phone(text):
                await self.send_message(user_id,
                    "❌ Пожалуйста, введите корректный номер телефона.\n"
                    "Примеры: +7 999 123-45-67 или 79991234567")
                return
            self.user_data[user_id]['phone'] = text
            self.user_states[user_id] = "waiting_description_choice"
            await self.send_message(user_id, "Кратко опишите ситуацию (необязательно):",
                self._get_buttons_description())
            return

        if self.user_states.get(user_id) == "waiting_description":
            await self.submit_application(user_id, description=text)
            return

    async def handle_callback(self, user_id: str, payload: str):
        logger.info(f"📘 Callback от {user_id}: {payload}")

        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': False,
                'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
            }

        if payload == "record":
            self.user_data[user_id]['in_consent_step'] = True
            await self.send_message(
                user_id,
                f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                f"Нажмите обе кнопки ниже для подтверждения:",
                self._get_buttons_consent()
            )
            return

        if payload == "consent_pd":
            if self.user_data[user_id].get('in_consent_step'):
                self.user_data[user_id]['consent_pd'] = True
                await self._check_consents(user_id)
            return

        if payload == "consent_policy":
            if self.user_data[user_id].get('in_consent_step'):
                self.user_data[user_id]['consent_policy'] = True
                await self._check_consents(user_id)
            return

        if payload == "refuse":
            await self._send_refusal_notification(user_id)
            self.user_states[user_id] = None
            self.user_data[user_id] = {}
            await self.send_message(
                user_id,
                "😔 Мы уважаем ваше решение и соблюдаем закон о защите персональных данных.\n\n"
                "Без согласия на обработку ПД мы не можем продолжить стандартный процесс консультации.\n\n"
                "Но это не означает, что мы не можем вам помочь! 💪\n\n"
                "Выберите один из вариантов:\n"
                "• Позвоните нам по номеру 8-495-999-85-89 и получите бесплатную консультацию\n"
                "• Или дайте согласие и оставьте заявку через бота",
                self._get_buttons_refusal()
            )
            return

        if payload == "physical":
            self.user_data[user_id]['client_type'] = "Физическое лицо"
            self.user_states[user_id] = "waiting_category"
            await self.send_message(user_id, "Выберите категорию вопроса:",
                self._get_buttons_individual_categories())
            return

        if payload == "legal":
            self.user_data[user_id]['client_type'] = "Юридическое лицо"
            self.user_states[user_id] = "waiting_category"
            await self.send_message(user_id, "Выберите категорию вопроса:",
                self._get_buttons_business_categories())
            return

        cat_map = {
            "cat_dtp": "ДТП", "cat_family": "Семейное право", "cat_realty": "Недвижимость",
            "cat_work": "Трудовые споры", "cat_other": "Другое",
            "cat_reg": "Регистрация бизнеса", "cat_contracts": "Договоры и споры",
            "cat_hr": "Трудовые вопросы", "cat_tax": "Налоги и штрафы"
        }

        if payload in cat_map:
            self.user_data[user_id]['category'] = cat_map[payload]
            self.user_states[user_id] = "waiting_name"
            await self.send_message(user_id, "Как вас зовут?")
            return

        if payload == "write_desc":
            self.user_states[user_id] = "waiting_description"
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
            self.user_data[user_id] = {
                'consent_pd': False, 'consent_policy': False, 'in_consent_step': True,
                'client_type': None, 'category': None, 'name': None, 'phone': None, 'description': None
            }
            await self.send_message(
                user_id,
                f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                f"Нажмите обе кнопки ниже для подтверждения:",
                self._get_buttons_consent()
            )
            return

    async def _check_consents(self, user_id: str):
        data = self.user_data[user_id]
        if data['consent_pd'] and data['consent_policy']:
            data['in_consent_step'] = False
            self.user_states[user_id] = "waiting_client_type"
            await self.send_message(user_id, "✅ Спасибо! Теперь выберите тип клиента:",
                self._get_buttons_client_type())

    async def get_user_phone(self, user_id: str):
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self.token}"}
                async with session.get(
                    f"{self.api_url}/users/{user_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        phone = data.get('phone') or data.get('contact', {}).get('phone')
                        return phone
                    return None
        except Exception as e:
            logger.debug(f"⚠️ Ошибка получения профиля: {e}")
            return None

    async def _send_refusal_notification(self, user_id: str):
        try:
            phone = await self.get_user_phone(user_id)
            phone_str = f"📱 Телефон: {phone}\n" if phone else ""

            message = (
                f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
                f"{'━' * 30}\n"
                f"Пользователь отказал в согласии на обработку ПД\n"
                f"👤 User ID: {user_id}\n"
                f"{phone_str}"
                f"📲 Источник: Max\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"{'━' * 30}"
            )
            await self.send_message(self.admin_id, message)
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

        self.user_states[user_id] = None
        if user_id in self.user_data:
            del self.user_data[user_id]


max_bot = MaxSecretaryBot()


# ===== WEBHOOK =====

async def webhook_handler(request):
    try:
        payload = await request.json()
        logger.debug(f"📨 Webhook: {json.dumps(payload, ensure_ascii=False)[:200]}")

        updates = payload.get('updates', [])
        if not isinstance(updates, list):
            updates = [updates]

        for update in updates:
            update_type = update.get('update_type', '')

            if update_type == 'message_created':
                message = update.get('message', {})
                sender = message.get('sender', {})
                user_id = sender.get('user_id')
                body = message.get('body', {})
                text = body.get('text', '')
                if user_id and text:
                    await max_bot.handle_message(user_id, text)

            elif update_type == 'message_callback':
                callback = update.get('callback', {})
                user = callback.get('user', {})
                user_id = user.get('user_id')
                payload_str = callback.get('payload', '')
                if user_id and payload_str:
                    await max_bot.handle_callback(user_id, payload_str)

        return web.json_response({'status': 'ok'})
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return web.json_response({'status': 'error'}, status=400)


async def startup():
    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', WEBHOOK_PORT)
    await site.start()

    logger.info(f"✓ Webhook-сервер запущен на порту {WEBHOOK_PORT}")
    logger.info(f"✓ Webhook URL: {max_bot.webhook_url}")

    logger.info("📝 Подписываю webhook на события Max API...")
    await asyncio.sleep(1)
    success = await max_bot.subscribe_webhook()

    if success:
        logger.info("🎉 Бот готов к работе!")
    else:
        logger.warning("⚠️ Webhook подписка не удалась, но бот может работать")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise

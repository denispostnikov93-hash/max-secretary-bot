"""
Max бот-секретарь - приём заявок на консультацию
Полная пересборка с исправлением webhook-парсинга и callback-кнопок

Архитектура:
- Webhook на aiohttp (порт 8080)
- Callback-кнопки с payload (надёжнее text-сравнения)
- Состояния в dict (user_states + user_data)
- Webhook: JSON с updates, парсим message_created и message_callback
- Текст и кнопки идентичны Telegram боту
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
    """Max мессенджер бот для приёма заявок на консультацию"""

    def __init__(self):
        self.token = MAX_BOT_TOKEN
        self.admin_id = MAX_ADMIN_USER_ID
        self.api_url = "https://platform-api.max.ru"
        self.user_data = {}       # Хранит данные формы
        self.user_states = {}     # Хранит текущее состояние

    # ============ УТИЛИТЫ ============

    def validate_phone(self, phone: str) -> bool:
        """Проверить корректность номера телефона (российский или международный)"""
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        return bool(
            re.match(r'^\+?7\d{9,10}$', cleaned) or
            re.match(r'^\+?\d{10,15}$', cleaned)
        )

    async def send_message(self, user_id: str, text: str, buttons=None):
        """Отправить сообщение в Max через API

        Args:
            user_id: Max ID пользователя
            text: Текст сообщения
            buttons: Список списков кнопок для inline-клавиатуры
        """
        try:
            payload = {
                "recipient": {"user_id": user_id},
                "text": text,
                "format": "markdown"
            }

            if buttons:
                payload["attachments"] = [{
                    "type": "inline_keyboard",
                    "payload": {
                        "buttons": buttons
                    }
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
            logger.error(f"✗ Ошибка отправки: {e}", exc_info=True)
            return False

    # ============ КЛАВИАТУРЫ ============

    def get_main_keyboard(self):
        """Главная клавиатура - кнопка для записи"""
        return [[{
            "type": "callback",
            "text": "📝 Записаться на консультацию",
            "payload": "record"
        }]]

    def get_consent_keyboard(self):
        """Клавиатура согласий - двухуровневое подтверждение"""
        return [
            [{"type": "callback", "text": "✅ Согласен на обработку персональных данных", "payload": "consent_pd"}],
            [{"type": "callback", "text": "✅ Ознакомлен с политикой обработки данных", "payload": "consent_policy"}],
            [{"type": "callback", "text": "❌ Отказать в согласии", "payload": "refuse"}]
        ]

    def get_client_type_keyboard(self):
        """Выбор типа клиента"""
        return [[
            {"type": "callback", "text": "👤 Физическое лицо", "payload": "physical"},
            {"type": "callback", "text": "🏢 Юридическое лицо", "payload": "legal"}
        ]]

    def get_individual_categories_keyboard(self):
        """Категории для физических лиц"""
        return [
            [{"type": "callback", "text": "🚗 ДТП", "payload": "cat_dtp"}],
            [{"type": "callback", "text": "👨‍👩‍👧 Семейное право", "payload": "cat_family"}],
            [{"type": "callback", "text": "🏠 Недвижимость", "payload": "cat_realty"}],
            [{"type": "callback", "text": "💼 Трудовые споры", "payload": "cat_work"}],
            [{"type": "callback", "text": "❓ Другое", "payload": "cat_other"}]
        ]

    def get_business_categories_keyboard(self):
        """Категории для юридических лиц"""
        return [
            [{"type": "callback", "text": "📋 Регистрация бизнеса", "payload": "cat_reg"}],
            [{"type": "callback", "text": "📝 Договоры и споры", "payload": "cat_contracts"}],
            [{"type": "callback", "text": "👷 Трудовые вопросы", "payload": "cat_hr"}],
            [{"type": "callback", "text": "💰 Налоги и штрафы", "payload": "cat_tax"}],
            [{"type": "callback", "text": "❓ Другое", "payload": "cat_other"}]
        ]

    def get_description_keyboard(self):
        """Выбор: написать описание или пропустить"""
        return [[
            {"type": "callback", "text": "✏️ Написать", "payload": "write_desc"},
            {"type": "callback", "text": "➡️ Пропустить", "payload": "skip_desc"}
        ]]

    def get_refusal_keyboard(self):
        """Клавиатура после отказа согласия"""
        return [
            [{"type": "callback", "text": "☎️ Позвонить: 8-495-999-85-89", "payload": "call"}],
            [{"type": "callback", "text": "↩️ Дать согласие и оставить заявку", "payload": "back_consent"}]
        ]

    # ============ ОБРАБОТЧИКИ СОБЫТИЙ ============

    async def handle_message(self, user_id: str, text: str):
        """Обработать текстовое сообщение"""
        if not user_id or not text:
            return

        text = text.strip()
        logger.info(f"📨 Text от {user_id}: {text[:50]}")

        # Инициализация пользователя при /start
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

            await self.send_message(
                user_id,
                "👋 Добро пожаловать в Правовой центр \"Постников групп\"!\n\n"
                "Мы поможем защитить ваши права. Для записи на консультацию нажмите кнопку.",
                self.get_main_keyboard()
            )
            return

        # Команда для узнания своего Max ID
        if text == "/my_id":
            await self.send_message(
                user_id,
                f"ℹ️ Ваш Max ID: `{user_id}`\n\n"
                f"Используйте этот ID в переменной окружения `MAX_ADMIN_USER_ID` для настройки бота."
            )
            return

        # Инициализация, если состояния нет
        if user_id not in self.user_data:
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

        # Ожидание ввода имени
        if self.user_states.get(user_id) == "waiting_name":
            self.user_data[user_id]['name'] = text
            self.user_states[user_id] = "waiting_phone"
            await self.send_message(user_id, "Ваш номер телефона?")
            return

        # Ожидание номера телефона
        if self.user_states.get(user_id) == "waiting_phone":
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
                "Кратко опишите ситуацию (необязательно):",
                self.get_description_keyboard()
            )
            return

        # Ожидание описания ситуации
        if self.user_states.get(user_id) == "waiting_description":
            await self.submit_application(user_id, description=text)
            return

    async def handle_callback(self, user_id: str, payload: str):
        """Обработать нажатие на кнопку (callback)

        Args:
            user_id: Max ID пользователя
            payload: Идентификатор нажатой кнопки
        """
        logger.info(f"📘 Callback от {user_id}: {payload}")

        # Инициализация пользователя при первом callback
        if user_id not in self.user_data:
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

        # ===== ОСНОВНОЙ ПОТОК =====

        # Нажата кнопка записи
        if payload == "record":
            self.user_data[user_id]['in_consent_step'] = True
            await self.send_message(
                user_id,
                f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                f"Нажмите обе кнопки ниже для подтверждения:",
                self.get_consent_keyboard()
            )
            return

        # Согласие на обработку персональных данных
        if payload == "consent_pd":
            if self.user_data[user_id].get('in_consent_step'):
                self.user_data[user_id]['consent_pd'] = True
                await self.check_consents(user_id)
            return

        # Согласие с политикой обработки данных
        if payload == "consent_policy":
            if self.user_data[user_id].get('in_consent_step'):
                self.user_data[user_id]['consent_policy'] = True
                await self.check_consents(user_id)
            return

        # Отказ в согласии
        if payload == "refuse":
            await self.send_refusal_notification(user_id)
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
                self.get_refusal_keyboard()
            )
            return

        # ===== ВЫБОР ТИПА КЛИЕНТА =====

        if payload == "physical":
            self.user_data[user_id]['client_type'] = "Физическое лицо"
            self.user_states[user_id] = "waiting_category"
            await self.send_message(
                user_id,
                "Выберите категорию вопроса:",
                self.get_individual_categories_keyboard()
            )
            return

        if payload == "legal":
            self.user_data[user_id]['client_type'] = "Юридическое лицо"
            self.user_states[user_id] = "waiting_category"
            await self.send_message(
                user_id,
                "Выберите категорию вопроса:",
                self.get_business_categories_keyboard()
            )
            return

        # ===== ВЫБОР КАТЕГОРИИ =====

        category_map = {
            "cat_dtp": "ДТП",
            "cat_family": "Семейное право",
            "cat_realty": "Недвижимость",
            "cat_work": "Трудовые споры",
            "cat_other": "Другое",
            "cat_reg": "Регистрация бизнеса",
            "cat_contracts": "Договоры и споры",
            "cat_hr": "Трудовые вопросы",
            "cat_tax": "Налоги и штрафы"
        }

        if payload in category_map:
            self.user_data[user_id]['category'] = category_map[payload]
            self.user_states[user_id] = "waiting_name"
            await self.send_message(user_id, "Как вас зовут?")
            return

        # ===== ОПИСАНИЕ =====

        if payload == "write_desc":
            self.user_states[user_id] = "waiting_description"
            await self.send_message(user_id, "Опишите вашу ситуацию:")
            return

        if payload == "skip_desc":
            await self.submit_application(user_id, description=None)
            return

        # ===== ОТКАЗ И ВОЗВРАТ =====

        if payload == "call":
            keyboard = self.get_main_keyboard()
            await self.send_message(
                user_id,
                "✅ Спасибо! Ждем вашего звонка.\n\n"
                "Наш специалист ответит на все ваши вопросы и поможет найти лучшее решение для вас.",
                keyboard
            )
            return

        if payload == "back_consent":
            self.user_data[user_id] = {
                'consent_pd': False,
                'consent_policy': False,
                'in_consent_step': True,
                'client_type': None,
                'category': None,
                'name': None,
                'phone': None,
                'description': None
            }
            await self.send_message(
                user_id,
                f"Перед подачей заявки ознакомьтесь с документами и подтвердите:\n\n"
                f"📄 Политика обработки данных: {PRIVACY_POLICY_URL}\n"
                f"📄 Согласие на обработку данных: {AGREEMENT_URL}\n\n"
                f"Нажмите обе кнопки ниже для подтверждения:",
                self.get_consent_keyboard()
            )
            return

    # ============ ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ============

    async def check_consents(self, user_id: str):
        """Проверить, подтверждены ли оба согласия"""
        data = self.user_data[user_id]
        if data['consent_pd'] and data['consent_policy']:
            data['in_consent_step'] = False
            self.user_states[user_id] = "waiting_client_type"
            await self.send_message(
                user_id,
                "✅ Спасибо! Теперь выберите тип клиента:",
                self.get_client_type_keyboard()
            )

    async def send_refusal_notification(self, user_id: str):
        """Отправить уведомление об отказе администратору"""
        try:
            message = (
                f"⚠️ ОТКАЗ ОТ ОБРАБОТКИ ПЕРСОНАЛЬНЫХ ДАННЫХ\n"
                f"{'━' * 30}\n"
                f"Пользователь отказал в согласии на обработку ПД\n"
                f"👤 User ID: {user_id}\n"
                f"📲 Источник: Max\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"{'━' * 30}"
            )
            await self.send_message(self.admin_id, message)
            logger.info(f"✓ Уведомление об отказе отправлено администратору")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки уведомления: {e}")

    async def submit_application(self, user_id: str, description=None):
        """Сохранить заявку в БД и отправить админу"""
        data = self.user_data[user_id]
        name = data.get('name', 'Неизвестно')

        try:
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
            logger.info(f"✓ Заявка {name} сохранена в БД")
        except Exception as e:
            logger.error(f"✗ Ошибка сохранения заявки: {e}")

        # Благодарность пользователю
        await self.send_message(
            user_id,
            f"✅ Спасибо, {name}! Заявка принята.\n"
            f"Наш специалист свяжется с вами в ближайшее время.",
            self.get_main_keyboard()
        )

        # Уведомление администратору
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
            logger.info(f"✓ Уведомление о заявке отправлено администратору")
        except Exception as e:
            logger.error(f"✗ Ошибка отправки уведомления: {e}")

        # Очистить состояние
        self.user_states[user_id] = None
        if user_id in self.user_data:
            del self.user_data[user_id]


# Глобальный экземпляр бота
max_bot = MaxSecretaryBot()


# ============ WEBHOOK ОБРАБОТЧИК ============

async def webhook_handler(request):
    """Обработать входящий webhook от Max API

    Ожидаемый формат:
    {
        "updates": [{
            "update_type": "message_created",
            "message": {
                "sender": {"user_id": "123"},
                "body": {"text": "hello"}
            }
        }, {
            "update_type": "message_callback",
            "callback": {
                "user": {"user_id": "456"},
                "payload": "button_id"
            }
        }]
    }
    """
    try:
        payload = await request.json()
        logger.debug(f"📨 Webhook payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

        updates = payload.get('updates', [])
        if not isinstance(updates, list):
            updates = [updates]

        for update in updates:
            try:
                update_type = update.get('update_type', '')

                # Обработка текстового сообщения
                if update_type == 'message_created':
                    message = update.get('message', {})
                    sender = message.get('sender', {})
                    user_id = sender.get('user_id')
                    body = message.get('body', {})
                    text = body.get('text', '')

                    if user_id and text:
                        await max_bot.handle_message(user_id, text)

                # Обработка нажатия на кнопку (callback)
                elif update_type == 'message_callback':
                    callback = update.get('callback', {})
                    user = callback.get('user', {})
                    user_id = user.get('user_id')
                    payload_str = callback.get('payload', '')

                    if user_id and payload_str:
                        await max_bot.handle_callback(user_id, payload_str)

            except Exception as e:
                logger.error(f"❌ Ошибка обработки update: {e}", exc_info=True)

        return web.json_response({'status': 'ok'})

    except Exception as e:
        logger.error(f"❌ Ошибка webhook handler: {e}", exc_info=True)
        return web.json_response({'status': 'error'}, status=400)


# ============ ЗАПУСК WEBHOOK СЕРВЕРА ============

async def startup():
    """Инициализация и запуск webhook-сервера на порту 8080"""
    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

    logger.info("✓ Webhook-сервер запущен на порту 8080")
    logger.info(f"✓ Webhook URL: http://0.0.0.0:8080/webhook")
    logger.info(f"✓ Max API: {max_bot.api_url}")

    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("⏹️  Webhook-сервер остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}", exc_info=True)
        raise

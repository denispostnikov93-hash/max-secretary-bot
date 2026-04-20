"""
Тесты для Max бота-секретаря
Проверяет: инициализацию, валидацию, состояния, webhook обработку
"""
import asyncio
import json
import os

os.environ['MAX_BOT_TOKEN'] = 'test_token'
os.environ['MAX_ADMIN_USER_ID'] = '240134783'
os.environ['MAX_ADMIN_PHONE'] = '+79859998589'

from max_bot import max_bot, webhook_handler
from aiohttp import web


class MockRequest:
    """Mock объект для тестирования webhook"""
    def __init__(self, data):
        self.data = data

    async def json(self):
        return self.data


async def test_bot_initialization():
    """Тест инициализации бота"""
    print("\n=== ТЕСТ 1: Инициализация бота ===")

    assert max_bot.token == 'test_token', "Token не установлен"
    assert max_bot.admin_id == '240134783', "Admin ID не установлен"
    assert max_bot.api_url == "https://platform-api.max.ru", "API URL неверный"
    assert isinstance(max_bot.user_data, dict), "user_data должен быть dict"
    assert isinstance(max_bot.user_states, dict), "user_states должен быть dict"
    print("✓ Бот инициализирован правильно")


async def test_phone_validation():
    """Тест валидации телефонов"""
    print("\n=== ТЕСТ 2: Валидация телефонов ===")

    # Валидные номера
    valid_phones = [
        '+79859998589',
        '+7 985 999 85 89',
        '79859998589',
        '+7-985-999-85-89',
        '+1234567890',
        '+12025551234'
    ]

    for phone in valid_phones:
        assert max_bot.validate_phone(phone), f"Телефон {phone} должен быть валиден"
    print(f"✓ {len(valid_phones)} валидных номеров телефонов проверены")

    # Невалидные номера
    invalid_phones = [
        'abc123',
        '123',
        '+7 99 1234',  # Слишком короткий
    ]

    for phone in invalid_phones:
        assert not max_bot.validate_phone(phone), f"Телефон {phone} должен быть невалиден"
    print(f"✓ {len(invalid_phones)} невалидных номеров отклонены")


async def test_user_state_management():
    """Тест управления состояниями пользователя"""
    print("\n=== ТЕСТ 3: Управление состояниями ===")

    user_id = 'test_user_123'

    # Проверить начальное состояние
    assert user_id not in max_bot.user_states, "User state должен быть пустым в начале"
    assert user_id not in max_bot.user_data, "User data должен быть пустым в начале"

    # Симулировать /start
    await max_bot.handle_message(user_id, '/start')

    assert user_id in max_bot.user_states, "User не был добавлен в user_states"
    assert user_id in max_bot.user_data, "User data не был создан"
    assert max_bot.user_data[user_id]['consent_pd'] == False, "Начальное согласие должно быть False"
    assert max_bot.user_data[user_id]['in_consent_step'] == False, "in_consent_step должен быть False при /start"

    print("✓ Состояния пользователя управляются правильно")


async def test_webhook_message():
    """Тест обработки webhook с обычным сообщением"""
    print("\n=== ТЕСТ 4: Webhook обработка сообщения ===")

    message_data = {
        "updates": [{
            "update_type": "message_created",
            "message": {
                "sender": {"user_id": "webhook_test_user"},
                "body": {"text": "/start"}
            }
        }]
    }

    request = MockRequest(message_data)
    response = await webhook_handler(request)
    response_data = json.loads(response.body)

    assert response_data['status'] == 'ok', f"Expected status 'ok', got {response_data['status']}"
    assert response.status == 200, f"Expected status 200, got {response.status}"
    print("✓ Webhook сообщение обработано успешно")


async def test_webhook_callback():
    """Тест обработки webhook с callback (нажатие на кнопку)"""
    print("\n=== ТЕСТ 5: Webhook обработка callback ===")

    callback_data = {
        "updates": [{
            "update_type": "message_callback",
            "callback": {
                "user": {"user_id": "callback_test_user"},
                "payload": "record"
            }
        }]
    }

    request = MockRequest(callback_data)
    response = await webhook_handler(request)
    response_data = json.loads(response.body)

    assert response_data['status'] == 'ok', f"Expected status 'ok', got {response_data['status']}"
    assert response.status == 200, f"Expected status 200, got {response.status}"
    assert 'callback_test_user' in max_bot.user_data, "User должен быть инициализирован"
    print("✓ Webhook callback обработан успешно")


async def test_user_data_structure():
    """Тест структуры данных пользователя"""
    print("\n=== ТЕСТ 6: Структура данных пользователя ===")

    user_id = 'struct_test_user'
    await max_bot.handle_message(user_id, '/start')

    data = max_bot.user_data[user_id]

    # Проверить все необходимые поля
    required_fields = [
        'consent_pd', 'consent_policy', 'in_consent_step',
        'client_type', 'category', 'name', 'phone', 'description'
    ]

    for field in required_fields:
        assert field in data, f"Поле {field} отсутствует в user_data"

    print(f"✓ Все {len(required_fields)} необходимых полей присутствуют")


async def test_keyboards():
    """Тест доступности методов клавиатур"""
    print("\n=== ТЕСТ 7: Доступность клавиатур ===")

    keyboards = [
        ('main_keyboard', max_bot.get_main_keyboard()),
        ('consent_keyboard', max_bot.get_consent_keyboard()),
        ('client_type_keyboard', max_bot.get_client_type_keyboard()),
        ('individual_categories_keyboard', max_bot.get_individual_categories_keyboard()),
        ('business_categories_keyboard', max_bot.get_business_categories_keyboard()),
        ('description_keyboard', max_bot.get_description_keyboard()),
        ('refusal_keyboard', max_bot.get_refusal_keyboard()),
    ]

    for name, keyboard in keyboards:
        assert isinstance(keyboard, list), f"{name} должен быть list"
        assert len(keyboard) > 0, f"{name} должен содержать кнопки"
        print(f"  ✓ {name}: {len(keyboard)} рядов кнопок")

    print(f"✓ Все {len(keyboards)} клавиатур доступны")


async def run_tests():
    """Запустить все тесты"""
    print("=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ MAX БОТА-СЕКРЕТАРЯ")
    print("=" * 60)

    tests = [
        test_bot_initialization,
        test_phone_validation,
        test_keyboards,
        test_user_state_management,
        test_user_data_structure,
        test_webhook_message,
        test_webhook_callback,
    ]

    failed = 0
    for test in tests:
        try:
            await test()
        except AssertionError as e:
            print(f"❌ ОШИБКА: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ НЕОЖИДАННАЯ ОШИБКА: {e}", exc_info=True)
            failed += 1

    print("\n" + "=" * 60)
    if failed == 0:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    else:
        print(f"❌ {failed} ТЕСТОВ НЕ ПРОШЛИ")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    exit(0 if success else 1)

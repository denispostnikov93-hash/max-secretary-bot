"""
Тест webhook обработчика и логики бота
"""
import asyncio
import json
import os

os.environ['MAX_BOT_TOKEN'] = 'test_token'
os.environ['MAX_ADMIN_USER_ID'] = '240134783'

from max_bot import max_bot, webhook_handler
from aiohttp import web

class MockRequest:
    """Mock объект для тестирования"""
    def __init__(self, data):
        self.data = data

    async def json(self):
        return self.data

async def test_webhook_message():
    """Тест обработки входящего сообщения"""
    print("\n=== ТЕСТ 1: Обработка /start команды ===")

    message_data = {
        'type': 'message',
        'data': {
            'from_id': '123456789',
            'text': '/start'
        }
    }

    request = MockRequest(message_data)
    response = await webhook_handler(request)
    response_data = json.loads(response.body)

    assert response_data['status'] == 'ok', f"Expected status 'ok', got {response_data['status']}"
    assert response.status == 200, f"Expected status 200, got {response.status}"
    print("✓ /start команда обработана успешно")

async def test_bot_initialization():
    """Тест инициализации бота"""
    print("\n=== ТЕСТ 2: Инициализация бота ===")

    assert max_bot.token == 'test_token', "Token не установлен"
    assert max_bot.admin_id == '240134783', "Admin ID не установлен"
    assert max_bot.api_url == "https://platform-api.max.ru", "API URL неверный"
    print("✓ Бот инициализирован правильно")

async def test_phone_validation():
    """Тест валидации телефонов"""
    print("\n=== ТЕСТ 3: Валидация телефонов ===")

    valid_phones = [
        '+79859998589',
        '+7 985 999 85 89',
        '79859998589',
        '+7-985-999-85-89'
    ]

    for phone in valid_phones:
        assert max_bot.validate_phone(phone), f"Телефон {phone} не прошел валидацию"

    print(f"✓ {len(valid_phones)} валидных номеров телефонов проверены")

async def test_user_state_management():
    """Тест управления состояниями пользователя"""
    print("\n=== ТЕСТ 4: Управление состояниями ===")

    user_id = 'test_user_123'

    # Проверить начальное состояние
    assert user_id not in max_bot.user_states, "User state должен быть пустым"

    # Симулировать /start
    await max_bot.handle_message({'from_id': user_id, 'text': '/start'})

    assert user_id in max_bot.user_states, "User не был добавлен"
    assert user_id in max_bot.user_data, "User data не был создан"

    print("✓ Состояния пользователя управляются правильно")

async def run_tests():
    """Запустить все тесты"""
    print("=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ MAX БОТА")
    print("=" * 60)

    try:
        await test_bot_initialization()
        await test_phone_validation()
        await test_user_state_management()
        await test_webhook_message()

        print("\n" + "=" * 60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}", exc_info=True)
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(run_tests())
    exit(0 if success else 1)

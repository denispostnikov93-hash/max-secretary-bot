"""
Max бот-секретарь
"""
import asyncio
import logging
from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID
from database import db
from max_bot import startup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_config():
    """Проверить конфигурацию"""
    if not MAX_BOT_TOKEN:
        logger.error("❌ MAX_BOT_TOKEN не установлен!")
        return False
    if not MAX_ADMIN_USER_ID:
        logger.error("❌ MAX_ADMIN_USER_ID не установлен!")
        return False
    return True

async def main():
    logger.info("=" * 60)
    logger.info("🤖 MAX БОТ-СЕКРЕТАРЬ")
    logger.info("=" * 60)

    if not validate_config():
        logger.error("❌ Конфигурация неполная. Проверь переменные окружения.")
        return

    try:
        logger.info("📦 Инициализирую БД...")
        await db.init()
        logger.info("✓ БД готова")

        logger.info("📱 Запускаю Max бота...")
        logger.info("=" * 60)

        await startup()

    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())

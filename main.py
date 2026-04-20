"""
Max бот-секретарь
"""
import asyncio
import logging
from database import db
from max_bot import max_bot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("=" * 60)
    logger.info("🤖 MAX БОТ-СЕКРЕТАРЬ")
    logger.info("=" * 60)

    try:
        logger.info("📦 Инициализирую БД...")
        await db.init()
        logger.info("✓ БД готова")

        logger.info("📱 Запускаю Max бота...")
        logger.info("✓ Бот подключен к Max")
        logger.info("=" * 60)

        await max_bot.start()

    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())

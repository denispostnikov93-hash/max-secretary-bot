"""
Max бот-секретарь
"""
import sys
print("[START] main.py initializing", file=sys.stderr)

import asyncio
import logging
import os

print(f"[ENV] All MAX_ variables:", file=sys.stderr)
for k, v in os.environ.items():
    if k.startswith('MAX'):
        print(f"  {k}={v[:30] if len(v) > 30 else v}", file=sys.stderr)

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID
print(f"[IMPORT] MAX_BOT_TOKEN from config: {repr(MAX_BOT_TOKEN[:20] if MAX_BOT_TOKEN else MAX_BOT_TOKEN)}", file=sys.stderr)
from database import db
from max_bot import start_polling

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

        await start_polling()

    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())

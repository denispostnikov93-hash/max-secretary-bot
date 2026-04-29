"""
Max бот-секретарь - Webhook версия
Запускает FastAPI приложение вместо long polling
"""
import sys
import logging
import os
import uvicorn

# Инициализация логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from config import MAX_BOT_TOKEN, MAX_ADMIN_USER_ID, WEBHOOK_PORT

logger.info(f"[CONFIG] MAX_BOT_TOKEN установлен: {bool(MAX_BOT_TOKEN)}")
logger.info(f"[CONFIG] MAX_ADMIN_USER_ID: {MAX_ADMIN_USER_ID}")
logger.info(f"[CONFIG] WEBHOOK_PORT: {WEBHOOK_PORT}")


def validate_config():
    """Проверить конфигурацию"""
    if not MAX_BOT_TOKEN:
        logger.error("❌ MAX_BOT_TOKEN не установлен!")
        return False
    if not MAX_ADMIN_USER_ID:
        logger.error("❌ MAX_ADMIN_USER_ID не установлен!")
        return False
    return True


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🤖 MAX БОТ-СЕКРЕТАРЬ (Webhook версия)")
    logger.info("=" * 60)

    if not validate_config():
        logger.error("❌ Конфигурация неполная. Проверь переменные окружения.")
        sys.exit(1)

    try:
        logger.info("🚀 Запускаю FastAPI приложение...")
        logger.info(f"📝 Webhook port: {WEBHOOK_PORT}")
        logger.info("=" * 60)

        # Запускаем FastAPI приложение через uvicorn
        uvicorn.run(
            "webhook_app:app",
            host="0.0.0.0",
            port=WEBHOOK_PORT,
            log_level="info",
            reload=False
        )

    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

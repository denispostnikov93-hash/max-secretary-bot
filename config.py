"""
Конфиг для Max бота-секретаря
"""
import os

# Load from .env only if it exists (for local development)
try:
    from dotenv import load_dotenv
    if os.path.exists('.env'):
        load_dotenv(override=False)
except ImportError:
    pass

# ===== MAX =====
# Используем os.environ для явного доступа к переменным Railway
MAX_BOT_TOKEN = os.environ.get('MAX_BOT_TOKEN') or os.getenv('MAX_BOT_TOKEN', '')
MAX_ADMIN_USER_ID = os.environ.get('MAX_ADMIN_USER_ID') or os.getenv('MAX_ADMIN_USER_ID', '240134783')
MAX_ADMIN_PHONE = os.environ.get('MAX_ADMIN_PHONE') or os.getenv('MAX_ADMIN_PHONE', '+79859998589')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL') or os.getenv('WEBHOOK_URL', 'http://localhost:8080/webhook')
WEBHOOK_PORT = int(os.environ.get('WEBHOOK_PORT') or os.getenv('WEBHOOK_PORT', '8080'))

# ===== DATABASE =====
DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.getenv('DATABASE_PATH', 'applications.db')

# ===== LINKS =====
PRIVACY_POLICY_URL = "https://postnikov.group/privacy-policy"
AGREEMENT_URL = "https://postnikov.group/agreement"

# ===== DEBUG =====
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

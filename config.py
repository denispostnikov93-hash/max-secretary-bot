"""
Конфиг для Max бота-секретаря
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ===== MAX =====
MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN')
if not MAX_BOT_TOKEN:
    raise ValueError("❌ MAX_BOT_TOKEN не установлен в переменных окружения!")

MAX_ADMIN_USER_ID = os.getenv('MAX_ADMIN_USER_ID')
if not MAX_ADMIN_USER_ID:
    raise ValueError("❌ MAX_ADMIN_USER_ID не установлен в переменных окружения!")

# ===== DATABASE =====
DATABASE_PATH = os.getenv('DATABASE_PATH', 'applications.db')

# ===== LINKS =====
PRIVACY_POLICY_URL = "https://postnikov.group/privacy-policy"
AGREEMENT_URL = "https://postnikov.group/agreement"

# ===== DEBUG =====
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

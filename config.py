"""
Конфиг для Max бота-секретаря
"""
import os
import sys

# Load from .env only if it exists (for local development)
try:
    from dotenv import load_dotenv
    if os.path.exists('.env'):
        load_dotenv(override=False)
except ImportError:
    pass

# Debug: print all environment variables that start with MAX
print("[DEBUG CONFIG] Environment variables:", file=sys.stderr)
for key in sorted(os.environ.keys()):
    if key.startswith('MAX') or key.startswith('DATABASE'):
        print(f"  {key}={os.environ[key][:20] if len(os.environ[key]) > 20 else os.environ[key]}", file=sys.stderr)

# ===== MAX =====
# Используем os.environ для явного доступа к переменным Railway
MAX_BOT_TOKEN = os.environ.get('MAX_BOT_TOKEN') or os.getenv('MAX_BOT_TOKEN', '')
MAX_ADMIN_USER_ID = os.environ.get('MAX_ADMIN_USER_ID') or os.getenv('MAX_ADMIN_USER_ID', '240134783')
MAX_ADMIN_PHONE = os.environ.get('MAX_ADMIN_PHONE') or os.getenv('MAX_ADMIN_PHONE', '+79859998589')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL') or os.getenv('WEBHOOK_URL', 'http://localhost:8080/webhook')
WEBHOOK_PORT = int(os.environ.get('WEBHOOK_PORT') or os.getenv('WEBHOOK_PORT', '8080'))

print(f"[DEBUG CONFIG] MAX_BOT_TOKEN set: {bool(MAX_BOT_TOKEN)}", file=sys.stderr)

# ===== DATABASE =====
DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.getenv('DATABASE_PATH', 'applications.db')

# ===== LINKS =====
PRIVACY_POLICY_URL = "https://postnikov.group/privacy-policy"
AGREEMENT_URL = "https://postnikov.group/agreement"

# ===== DEBUG =====
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

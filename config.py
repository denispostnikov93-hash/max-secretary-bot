"""
Конфиг для Max бота-секретаря
"""
import os
import sys

print("[CONFIG LOAD] Starting config.py", file=sys.stderr)

# Debug: print all environment variables
print("[ENV DUMP] All environment variables starting with MAX, DATABASE, RAILWAY:", file=sys.stderr)
for key in sorted(os.environ.keys()):
    if any(prefix in key for prefix in ['MAX', 'DATABASE', 'RAILWAY', 'PORT', 'TOKEN']):
        val = os.environ[key]
        print(f"  {key}={val[:40] if len(val) > 40 else val}", file=sys.stderr)

# Load from .env only if it exists (for local development)
print("[CONFIG] Checking for .env file...", file=sys.stderr)
try:
    from dotenv import load_dotenv
    if os.path.exists('.env'):
        print("[CONFIG] .env found, loading...", file=sys.stderr)
        load_dotenv(override=False)
    else:
        print("[CONFIG] .env NOT found", file=sys.stderr)
except ImportError:
    print("[CONFIG] python-dotenv not available", file=sys.stderr)
    pass

# ===== MAX =====
print("[CONFIG] Reading MAX_BOT_TOKEN...", file=sys.stderr)
env_token = os.environ.get('MAX_BOT_TOKEN')
getenv_token = os.getenv('MAX_BOT_TOKEN', '')
print(f"[CONFIG]   os.environ.get()={repr(env_token)}", file=sys.stderr)
print(f"[CONFIG]   os.getenv()={repr(getenv_token)}", file=sys.stderr)

MAX_BOT_TOKEN = env_token or getenv_token
print(f"[CONFIG]   Final MAX_BOT_TOKEN={repr(MAX_BOT_TOKEN[:30] if MAX_BOT_TOKEN else MAX_BOT_TOKEN)}", file=sys.stderr)

MAX_ADMIN_USER_ID = os.environ.get('MAX_ADMIN_USER_ID') or os.getenv('MAX_ADMIN_USER_ID', '240134783')
MAX_ADMIN_PHONE = os.environ.get('MAX_ADMIN_PHONE') or os.getenv('MAX_ADMIN_PHONE', '+79859998589')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL') or os.getenv('WEBHOOK_URL', 'https://max-bot-production.railway.app/webhook')
WEBHOOK_PORT = int(os.environ.get('WEBHOOK_PORT') or os.getenv('PORT', '8080'))
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET') or os.getenv('WEBHOOK_SECRET', 'max-bot-secret-key-12345')

print(f"[CONFIG DONE] MAX_BOT_TOKEN length={len(MAX_BOT_TOKEN)}", file=sys.stderr)

# ===== DATABASE =====
DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.getenv('DATABASE_PATH', 'applications.db')

# ===== LINKS =====
PRIVACY_POLICY_URL = "https://postnikov.group/privacy-policy"
AGREEMENT_URL = "https://postnikov.group/agreement"

# ===== DEBUG =====
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

"""
Application configuration for Smart Waste Segregator.
All secrets/runtime settings come from environment variables. Values may be placed
in a `backend/.env` file (see `backend/.env.example`); real environment variables
always win. Nothing sensitive is hardcoded here.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _BACKEND_DIR = Path(__file__).resolve().parent
    load_dotenv(_BACKEND_DIR / '.env')  # optional; ignore if python-dotenv is absent
except ImportError:
    pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


_ENV = os.environ.get('ENV', '').strip().lower()
_debug_explicit = 'DEBUG' in os.environ
_debug = os.environ.get('DEBUG', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
_DEV_SECRET_KEY = 'smart-waste-dev-key-2026'


class Config:
    # Flask session signing key. When running in production (ENV=production or an
    # explicit DEBUG=false) an empty/missing SECRET_KEY is fatal: the app refuses
    # to start instead of silently signing sessions with a volatile key that
    # resets on every restart. Plain dev mode falls back to a fixed dev-only key.
    _secret = os.environ.get('SECRET_KEY', '').strip()
    if not _secret:
        if _ENV == 'production' or (_debug_explicit and not _debug):
            raise RuntimeError(
                "SECRET_KEY must be set in backend/.env (or the environment) when "
                "running in production (ENV=production or DEBUG=false)."
            )
        _secret = _DEV_SECRET_KEY
    SECRET_KEY = _secret
    ENV = _ENV

    DB_URL = os.environ.get('DB_URL', os.path.join(os.path.dirname(__file__), 'waste.db'))

    # Comma-separated origins allowed to call the API with credentials.
    CORS_ORIGIN = os.environ.get('CORS_ORIGIN', 'http://localhost:5000')

    DEVICE_TOKEN = os.environ.get('DEVICE_TOKEN', '')
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

    # JUNO AI support bot: Google Gemini key (kept server-side only). When
    # empty, JUNO answers from the built-in FAQ and falls back to an escalation
    # message instead of calling the API.
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    # Optional explicit model id (e.g. 'gemini-2.5-flash'); when empty the bot
    # probes a small preferred list at runtime.
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', '')

    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', '5000'))
    DEBUG = os.environ.get('DEBUG', 'false').strip().lower() in ('1', 'true', 'yes', 'on')


DB_PATH = Config.DB_URL
BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups')
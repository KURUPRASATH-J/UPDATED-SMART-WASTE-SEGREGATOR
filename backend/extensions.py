"""
Shared extensions and helpers: SocketIO, DB access, auth decorators, Telegram.
"""
import json
import sqlite3
import threading
from functools import wraps

import urllib.request
from flask import jsonify, session
from flask_socketio import SocketIO

from config import Config

socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet')


def get_db():
    conn = sqlite3.connect(Config.DB_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not authenticated'}), 401
        import models  # lazy import avoids circular dependency
        user = models.get_user_by_id(session['user_id'])
        if not user or user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        # An admin sitting on a seeded/default password is refused on EVERY admin
        # endpoint, not just at login -- so bypassing the login form's UI still
        # gets nowhere until the password is changed.
        if user.get('must_change_password'):
            return jsonify({
                'error': 'Password change required',
                'mustChangePassword': True
            }), 403
        return f(*args, **kwargs)
    return decorated


def send_telegram(message):
    """Send a message via Telegram bot (non-blocking)."""
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        return

    def _send():
        try:
            url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = json.dumps({
                'chat_id': Config.TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }).encode()
            req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()
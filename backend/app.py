"""
Smart Waste Segregator - Flask Backend v4.0
Restructured: blueprint package (auth/bins/gamification/analytics/admin)
"""
import os
import sys
from datetime import datetime

from flask import Flask, jsonify, request, redirect, render_template, session, send_from_directory
from flask_cors import CORS
from flask_socketio import emit
from jinja2 import TemplateNotFound

# Make this directory importable regardless of the cwd used to launch the app
sys.path.insert(0, os.path.dirname(__file__))

from config import BASE_DIR, Config
from extensions import socketio
import models

from auth.routes import auth_bp, settings_bp, profile_bp
from bins.routes import bins_bp
from gamification.routes import gamification_bp
from analytics.routes import analytics_bp
from admin.routes import admin_bp, telegram_bp
from support.routes import support_bp

from pages_registry import NAV

# ============ App Setup ============
app = Flask(__name__, static_folder=None)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

if app.secret_key == 'smart-waste-dev-key-2026':
    print("[WARNING] Using development SECRET_KEY - set SECRET_KEY in backend/.env for production.")

if Config.CORS_ORIGIN and Config.CORS_ORIGIN != '*':
    CORS(app, supports_credentials=True, origins=[o.strip() for o in Config.CORS_ORIGIN.split(',')])
else:
    CORS(app, supports_credentials=True)

socketio.init_app(app)

# ============ CSRF guard (origin allow-list) ============
# Minimal same-origin protection for every state-changing /api/* call. Browsers
# always attach an Origin header to cross-site POSTs, so any Origin that is not on
# the CORS allow-list is rejected. Requests without an Origin header (ESP32 device,
# curl, native clients, same-tab navigation) are left untouched. This is a cheap,
# dependency-free defence-in-depth layer on top of the SameSite session cookie.
@app.before_request
def csrf_origin_guard():
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None
    if not request.path.startswith('/api/'):
        return None
    origin = request.headers.get('Origin')
    if not origin or not Config.CORS_ORIGIN or Config.CORS_ORIGIN == '*':
        return None
    # Any genuinely same-origin request is fine (works on any LAN IP/port).
    host = request.headers.get('Host')
    if host:
        from urllib.parse import urlparse
        try:
            if urlparse(origin).netloc == host:
                return None
        except ValueError:
            pass
    allowed = [o.strip() for o in Config.CORS_ORIGIN.split(',')]
    if origin not in allowed:
        return jsonify({'error': 'Cross-origin request blocked'}), 403
    return None

# ============ Blueprints ============
app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(bins_bp)
app.register_blueprint(gamification_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(telegram_bp)
app.register_blueprint(support_bp)

FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')


# ============ Navigation context (single source: pages_registry.NAV) ============
@app.context_processor
def inject_navigation():
    role = None
    if session.get('user_id'):
        user = models.get_user_by_id(session['user_id'])
        if user:
            role = user.get('role')
    return {
        'nav_items': [p for p in NAV if not p['required_role'] or p['required_role'] == role],
        'nav_role': role,
    }


# ============ Static File Serving ============
@app.route('/')
@app.route('/index.html')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/dashboard.html')
def serve_dashboard():
    return render_template('dashboard.html')

# Admin portal — distinct landing page for role=admin only. Regular (logged-in)
# users get bounced to the standard dashboard; anonymous visitors to the login.
_ADMIN_ONLY_PAGES = frozenset({'users.html', 'maintenance.html'})


def _current_user():
    if 'user_id' not in session:
        return None
    return models.get_user_by_id(session['user_id'])


@app.route('/admin.html')
def serve_admin_dashboard():
    user = _current_user()
    if user is None:
        return redirect('/')
    if user.get('role') not in ('admin',):
        return redirect('/dashboard.html')
    # Still on a seeded/default password: send them back to the login page,
    # which shows the forced change-password dialog.
    if user.get('must_change_password'):
        return redirect('/?change_password=required')
    return render_template('admin_dashboard.html')


@app.route('/register.html')
def serve_register():
    return send_from_directory(FRONTEND_DIR, 'register.html')

@app.route('/pages/<path:filename>')
def serve_pages(filename):
    if filename in _ADMIN_ONLY_PAGES:
        user = _current_user()
        if user is None:
            return redirect('/')
        if user.get('role') != 'admin':
            return redirect('/dashboard.html')
    try:
        return render_template('pages/' + filename)
    except TemplateNotFound:
        return send_from_directory(os.path.join(FRONTEND_DIR, 'pages'), filename)

@app.route('/frontend/<path:filename>')
def serve_frontend(filename):
    return send_from_directory(FRONTEND_DIR, filename)

# Legacy aliases -> shared assets (backwards compatibility)
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'shared', 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'shared', 'js'), filename)

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'assets'), filename)

# User-uploaded profile pictures (backend/uploads/avatars/<user_id>.<ext>)
UPLOADS_AVATAR_DIR = os.path.join(os.path.dirname(__file__), 'uploads', 'avatars')

@app.route('/uploads/avatars/<path:filename>')
def serve_uploaded_avatar(filename):
    return send_from_directory(UPLOADS_AVATAR_DIR, filename)

# Legacy page URLs -> canonical template URLs (pages moved into templates/)
@app.route('/frontend/dashboard.html')
def legacy_dashboard_page():
    return redirect('/dashboard.html', code=301)

@app.route('/frontend/pages/<path:filename>')
def legacy_page(filename):
    return redirect('/pages/' + filename, code=301)

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory(FRONTEND_DIR, 'manifest.json')

@app.route('/favicon.ico')
def serve_favicon():
    # Browsers request /favicon.ico automatically; return the generated ico.
    return send_from_directory(os.path.join(FRONTEND_DIR, 'assets', 'images'), 'favicon.ico')

@app.route('/service-worker.js')
def serve_sw():
    return send_from_directory(FRONTEND_DIR, 'service-worker.js')

@app.errorhandler(404)
def handle_not_found(e):
    try:
        return render_template('pages/404.html'), 404
    except Exception:
        return send_from_directory(os.path.join(FRONTEND_DIR, 'pages'), '404.html'), 404


# ============ WebSocket Events ============
@socketio.on('connect')
def handle_connect():
    bins = models.get_bins()
    device = models.get_device_state()
    predictions = models.get_predictions()
    emit('bin_update', {
        'wetBin': bins.get('wetBin', {}), 'dryBin': bins.get('dryBin', {}),
        'predictions': predictions, 'timestamp': datetime.now().isoformat()
    })
    emit('presence_update', {
        'detected': device.get('presence_detected', 'false') == 'true',
        'distance': float(device.get('presence_distance', 0))
    })
    emit('lid_update', {'status': device.get('lid_status', 'closed')})
    print("Client connected")


@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")


# ============ Run Server ============
if __name__ == '__main__':
    print("\n" + "=" * 55)
    print("  Smart Waste Segregator - Flask Backend v4.0")
    print("=" * 55)
    print(f"  Frontend: http://localhost:5000")
    print(f"  API:      http://localhost:5000/api/")
    print(f"  Database: {models.DB_PATH}")
    if Config.TELEGRAM_BOT_TOKEN:
        print(f"  Telegram: Enabled")
    print("=" * 55 + "\n")

    socketio.run(app, host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
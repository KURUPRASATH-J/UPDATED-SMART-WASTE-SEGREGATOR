from flask import Blueprint, jsonify, request, session
import json
import os
import re

import models
from extensions import login_required
from gamification.badges import evaluate_user
from config import BASE_DIR
from auth import security

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Generic, deliberately uninformative text for a portal/role mismatch. It must
# not reveal whether the account exists or whether it is an admin, otherwise the
# error becomes an account-enumeration oracle.
PORTAL_MISMATCH_MSG = "These credentials can't be used on this portal"


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    full_name = data.get('fullName', '').strip()
    if not username or not email or not password:
        return jsonify({'error': 'Username, email, and password are required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    # create_user() never reads a role from the payload, so a `role` field sent by
    # the client is ignored entirely. Registration therefore can only ever produce
    # a regular user account -- there is no path here to self-elevate to admin.
    user_id = models.create_user(username, email, password, full_name)
    if user_id is None:
        return jsonify({'error': 'Username or email already exists'}), 409
    models.add_activity('user', f'New user registered: {username}')
    return jsonify({'message': 'User created successfully', 'userId': user_id}), 201


@auth_bp.route('/admin-challenge', methods=['GET'])
def admin_challenge():
    """Mint a one-shot math challenge for the admin portal.

    Only the id and the rendered question are returned -- the expected answer
    stays in the server-side store until it is consumed.
    """
    ip = request.remote_addr or 'unknown'
    try:
        challenge_id, question = security.issue_challenge(ip)
    except RuntimeError as exc:
        return jsonify({'error': 'Too many challenge requests. Please wait a moment.'}), 429
    return jsonify({'challenge_id': challenge_id, 'question': question})


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # Which portal the client claims to be using. Missing/unknown -> "user",
    # which is the safer default: it cannot grant admin access.
    portal = str(data.get('portal') or 'user').strip().lower()
    if portal not in ('user', 'admin'):
        portal = 'user'

    username = data.get('username', '').strip()
    password = data.get('password', '')
    ip = request.remote_addr or 'unknown'

    # ---- Admin-only gates, applied BEFORE any credential work -------------
    if portal == 'admin':
        blocked, message, retry_after = security.admin_guard(ip, username)
        if blocked:
            return jsonify({'error': message, 'retryAfter': retry_after}), 429
        # The challenge is verified before the password is ever touched, and it
        # is consumed either way so it cannot be replayed.
        ok, _reason = security.consume_challenge(data.get('challenge_id'),
                                                 data.get('challenge_answer'))
        if not ok:
            security.admin_record_failure(ip, username)
            return jsonify({'error': 'Challenge failed'}), 400

    user = models.authenticate_user(username, password)
    if user is None:
        if portal == 'admin':
            security.admin_record_failure(ip, username)
        return jsonify({'error': 'Invalid username or password'}), 401

    # ---- Server-side portal enforcement (only after the password is valid) --
    is_admin = user.get('role') == 'admin'
    if is_admin != (portal == 'admin'):
        models.add_activity(
            'security',
            f'Portal mismatch: {username} attempted the {portal} portal',
            # the activity.data column is TEXT, so serialise the audit detail
            data=json.dumps({'username': username, 'ip': ip, 'portal': portal,
                             'attempted_role': 'admin' if is_admin else 'user'}))
        if portal == 'admin':
            security.admin_record_failure(ip, username)
        # No session is created. Same response text regardless of direction.
        return jsonify({'error': PORTAL_MISMATCH_MSG}), 403

    if portal == 'admin':
        security.admin_clear_failures(ip, username)

    session['user_id'] = user['id']
    models.update_last_login(user['id'])
    models.record_user_event(user['id'], 'login')
    evaluate_user(user['id'])
    models.add_activity('login', f'{user["username"]} logged in')

    # A seeded account still on its default password gets a session (so the
    # change-password call can be authenticated) but is NOT admitted to the
    # admin portal, and admin_required blocks every /api/admin/* call until the
    # password is changed.
    if user.get('must_change_password'):
        return jsonify({
            'error': 'Password change required',
            'mustChangePassword': True,
            'message': 'Set a new password before opening the admin portal.'
        }), 403

    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user['id'], 'username': user['username'], 'email': user['email'],
            'fullName': user['full_name'], 'role': user['role'],
            'ecoScore': user.get('eco_score', 0), 'streakDays': user.get('streak_days', 0),
            'avatarUrl': user.get('avatar_url', '') or ''
        }
    })


@auth_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Set a new password. Requires the current password, and is the only way
    out of the forced-change state for a seeded admin account."""
    data = request.get_json() or {}
    current = data.get('current_password', '')
    new = data.get('new_password', '')
    confirm = data.get('confirm_password')
    if confirm is not None and confirm != new:
        return jsonify({'error': 'New passwords do not match'}), 400

    user = models.verify_password(session['user_id'], current)
    if user is None:
        return jsonify({'error': 'Current password is incorrect'}), 401

    ok, message = security.validate_password(new, user.get('username'), user.get('email'))
    if not ok:
        return jsonify({'error': message}), 400

    models.set_password(user['id'], new)
    models.add_activity('security', f'{user["username"]} changed their password',
                        data=json.dumps({'username': user['username'],
                                         'ip': request.remote_addr or 'unknown'}))
    return jsonify({'status': 'ok', 'message': 'Password updated'})


@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': 'Logged out'})


@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    if 'user_id' not in session:
        return jsonify({'authenticated': False}), 401
    user = models.get_user_by_id(session['user_id'])
    if not user:
        session.pop('user_id', None)
        return jsonify({'authenticated': False}), 401
    return jsonify({
        'authenticated': True,
        'mustChangePassword': bool(user.get('must_change_password')),
        'user': {
            'id': user['id'], 'username': user['username'], 'email': user['email'],
            'fullName': user['full_name'], 'role': user['role'],
            'ecoScore': user.get('eco_score', 0), 'streakDays': user.get('streak_days', 0),
            'totalWasteKg': user.get('total_waste_kg', 0),
            'avatarUrl': user.get('avatar_url', '') or ''
        }
    })


settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    return jsonify(models.get_settings(session['user_id']))


@settings_bp.route('/api/settings', methods=['POST'])
@login_required
def save_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    models.save_settings(session['user_id'], data)
    return jsonify({'status': 'ok', 'message': 'Settings saved'})


# ============ Profile: avatar upload / preset selection ============
profile_bp = Blueprint('profile', __name__, url_prefix='/api/profile')

MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB
_AVATAR_EXT = frozenset({'jpg', 'jpeg', 'png', 'webp'})
_AVATAR_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'avatars')
_AVATAR_PRESET_DIR = os.path.join(BASE_DIR, 'frontend', 'assets', 'images', 'avatars')
_PRESET_NAME_RE = re.compile(r'^avatar-[a-z0-9_-]+\.svg$', re.IGNORECASE)


def _validate_image_magic(data):
    """Cheap magic-byte sniff to reject mislabeled files."""
    if data.startswith(b'\xff\xd8\xff'):      return 'jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return 'png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return 'webp'
    return None


@profile_bp.route('/avatar', methods=['POST'])
@login_required
def set_avatar():
    user_id = session['user_id']
    file_part = request.files.get('avatar')
    preset = (request.form.get('preset') or '').strip()

    if file_part:
        original = file_part.filename or ''
        ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
        if ext not in _AVATAR_EXT:
            return jsonify({'error': 'Only JPG, PNG, or WebP images are allowed'}), 400
        data = file_part.read()
        if len(data) > MAX_AVATAR_BYTES:
            return jsonify({'error': 'Image must be 2 MB or smaller'}), 413
        sniffed = _validate_image_magic(data)
        if sniffed != ext:
            return jsonify({'error': 'File content does not match its extension'}), 400

        os.makedirs(_AVATAR_UPLOAD_DIR, exist_ok=True)
        # Remove any older avatar files belonging to this user (stale extensions).
        for old in os.listdir(_AVATAR_UPLOAD_DIR):
            if old.startswith(f'{user_id}.'):
                try:
                    os.remove(os.path.join(_AVATAR_UPLOAD_DIR, old))
                except OSError:
                    pass
        filename = f'{user_id}.{ext}'
        file_part.seek(0)
        with open(os.path.join(_AVATAR_UPLOAD_DIR, filename), 'wb') as fh:
            fh.write(data)
        avatar_url = f'/uploads/avatars/{filename}'

    elif preset:
        name = os.path.basename(preset)
        if not _PRESET_NAME_RE.match(name):
            return jsonify({'error': 'Unknown avatar preset'}), 400
        if not os.path.exists(os.path.join(_AVATAR_PRESET_DIR, name)):
            return jsonify({'error': 'Avatar preset not found'}), 404
        avatar_url = f'/assets/images/avatars/{name}'

    else:
        return jsonify({'error': 'No image or preset provided'}), 400

    models.set_avatar_url(user_id, avatar_url)
    return jsonify({'status': 'ok', 'message': 'Avatar updated', 'avatarUrl': avatar_url})
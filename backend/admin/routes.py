import os

import urllib.request
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, session

import models
from config import BACKUP_DIR, Config
from extensions import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    return jsonify(models.get_admin_stats())


@admin_bp.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_users():
    return jsonify(models.get_all_users())


_ACTIVE_USER_ROLES = {'user', 'resident', 'cleaner', 'supervisor', 'admin'}


@admin_bp.route('/api/admin/users/<int:user_id>/role', methods=['POST'])
@admin_required
def admin_set_user_role(user_id):
    data = request.get_json() or {}
    role = (data.get('role') or '').strip().lower()
    if role not in _ACTIVE_USER_ROLES:
        return jsonify({'error': 'Invalid role'}), 400
    user = models.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    models.set_user_role(user_id, role)
    return jsonify({'status': 'ok', 'id': user_id, 'role': role})


@admin_bp.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        return jsonify({'error': 'Cannot delete your own account'}), 400
    user = models.get_user_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    models.delete_user(user_id)
    return jsonify({'status': 'ok', 'id': user_id})


@admin_bp.route('/api/admin/backup', methods=['POST'])
@admin_required
def admin_backup():
    try:
        path = models.backup_database()
        return jsonify({'status': 'ok', 'path': path})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/admin/backups', methods=['GET'])
@admin_required
def admin_backups():
    return jsonify(models.get_backups())


@admin_bp.route('/api/admin/clear-test-data', methods=['POST'])
@admin_required
def admin_clear_test_data():
    """Delete simulated/test data (readings/collections/anomalies labelled
    source='test' plus [TEST] activity rows). A full DB backup is written before
    deleting so the operation is always reversible."""
    try:
        res = models.clear_test_data()
        return jsonify({'status': 'ok', 'backup': res['backup'], 'deleted': res['deleted']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/admin/backup/download/<filename>')
@admin_required
def download_backup(filename):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return send_file(os.path.join(BACKUP_DIR, filename), as_attachment=True)


@admin_bp.route('/api/admin/export', methods=['GET'])
@admin_required
def export_data():
    fmt = request.args.get('format', 'json')
    stats = models.get_stats()
    readings = models.get_readings(hours=720, limit=10000)
    activity = models.get_activity(1000)
    data = {'stats': stats, 'readings': readings, 'activity': activity, 'exported_at': datetime.now().isoformat()}
    return jsonify(data)


@admin_bp.route('/api/admin/ml/retrain', methods=['POST'])
@admin_required
def ml_retrain():
    """Retrain the fill/ttf and anomaly models from accumulated readings.
    Heavy operation - run occasionally (nightly/weekly), not per request."""
    try:
        from ml.retrain_models import retrain_all
        details = retrain_all()
        return jsonify({'status': 'ok', 'details': details})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/admin/ml/status', methods=['GET'])
@admin_required
def ml_status():
    """Model artifacts currently in use: present? sample counts? trained at?"""
    try:
        from ml import anomaly_detector, fill_predictor
        bins_model = {}
        for bt in ('wetBin', 'dryBin'):
            bins_model[bt] = {
                'fill': fill_predictor.status(bt),
                'anomaly': anomaly_detector.status(bt),
            }
        return jsonify({'status': 'ok', 'models': bins_model})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


telegram_bp = Blueprint('telegram', __name__)


@telegram_bp.route('/api/telegram/test', methods=['POST'])
def test_telegram():
    data = request.get_json() or {}
    token = data.get('token', Config.TELEGRAM_BOT_TOKEN)
    chat_id = data.get('chatId', Config.TELEGRAM_CHAT_ID)
    if not token or not chat_id:
        return jsonify({'error': 'Token and chatId required'}), 400
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = ("{\"chat_id\":\"%s\",\"text\":\"Smart Waste Segregator connected!\",\"parse_mode\":\"HTML\"}" % chat_id).encode()
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
        return jsonify({'status': 'ok', 'message': 'Test message sent!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
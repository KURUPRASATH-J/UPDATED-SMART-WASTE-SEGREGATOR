from datetime import datetime

from flask import Blueprint, jsonify, request, session

import models
from config import Config
from extensions import admin_required, login_required, send_telegram, socketio
from gamification.badges import evaluate_user

bins_bp = Blueprint('bins', __name__, url_prefix='/api')


def _device_authorized():
    """IoT device gate. Open when DEVICE_TOKEN is unset (backward compatible);
    when configured, requires the token on every device call."""
    token = Config.DEVICE_TOKEN or ''
    if not token:
        return True
    return request.headers.get('X-Device-Token') == token


@bins_bp.route('/sensor-data', methods=['POST'])
def receive_sensor_data():
    if not _device_authorized():
        return jsonify({'error': 'Unauthorized device'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    # Provenance label: real posts come from the ESP32 ('device'); the dashboard
    # "Simulate a reading" action sends source='test' so it never influences bin
    # state, device health, predictions or eco points.
    source = (data.get('source') or 'device').strip().lower()
    if source not in ('device', 'test'):
        source = 'device'
    result = {}
    user_id = session.get('user_id')
    # Liveness heartbeat for the dashboard "Device Health" card (the ESP32 posts
    # a reading every 5 s, so the 30 s online window in models.get_device_health
    # uses this as the authoritative last-seen timestamp). Test posts must NOT
    # flip the device to online.
    if source == 'device':
        models.update_device_state('last_seen', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    if 'wetLevel' in data:
        wet_level = max(0, min(100, int(data['wetLevel'])))
        r = models.update_bin('wetBin', wet_level, float(data.get('wetDistance', 0)),
                              float(data.get('wetWeight', 0)), int(data.get('wetGas', 0)),
                              user_id=user_id, source=source)
        result['wetBin'] = r
    if 'dryLevel' in data:
        dry_level = max(0, min(100, int(data['dryLevel'])))
        r = models.update_bin('dryBin', dry_level, float(data.get('dryDistance', 0)),
                              float(data.get('dryWeight', 0)), int(data.get('dryGas', 0)),
                              user_id=user_id, source=source)
        result['dryBin'] = r
    if source == 'test':
        socketio.emit('test_reading', {
            'wetBin': result.get('wetBin'), 'dryBin': result.get('dryBin'),
            'timestamp': datetime.now().isoformat()
        })
        return jsonify({'status': 'ok', 'test': True, 'result': result})
    bins = models.get_bins()
    predictions = models.get_predictions()
    socketio.emit('bin_update', {
        'wetBin': bins.get('wetBin', {}), 'dryBin': bins.get('dryBin', {}),
        'predictions': predictions, 'timestamp': datetime.now().isoformat()
    })
    if user_id:
        evaluate_user(user_id)
    for bt, bd in bins.items():
        if bd.get('level', 0) >= 85:
            send_telegram(f"⚠️ {bt} is at {bd['level']}%! Please empty soon.")
    return jsonify({'status': 'ok', 'result': result})


@bins_bp.route('/presence', methods=['POST'])
def receive_presence():
    if not _device_authorized():
        return jsonify({'error': 'Unauthorized device'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    detected = data.get('detected', False)
    distance = data.get('distance', 0)
    models.update_device_state('presence_detected', str(detected).lower())
    models.update_device_state('presence_distance', str(distance))
    if detected:
        models.add_activity('presence', f'Person detected at {distance:.1f} cm')
    socketio.emit('presence_update', {
        'detected': detected, 'distance': distance, 'timestamp': datetime.now().isoformat()
    })
    return jsonify({'status': 'ok'})


@bins_bp.route('/lid', methods=['POST'])
def receive_lid():
    if not _device_authorized():
        return jsonify({'error': 'Unauthorized device'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    status = data.get('status', 'closed')
    models.update_device_state('lid_status', status)
    models.add_activity('lid', f'Lid {status}')
    socketio.emit('lid_update', {'status': status, 'timestamp': datetime.now().isoformat()})
    return jsonify({'status': 'ok'})


@bins_bp.route('/bins', methods=['GET'])
def get_bins():
    bins = models.get_bins()
    device = models.get_device_state()
    predictions = models.get_predictions()
    return jsonify({'bins': bins, 'device': device, 'predictions': predictions})


@bins_bp.route('/bins/<bin_type>', methods=['GET'])
def get_bin(bin_type):
    b = models.get_bin(bin_type)
    if not b:
        return jsonify({'error': 'Bin not found'}), 404
    return jsonify(b)


@bins_bp.route('/bins/<bin_type>/collect', methods=['POST'])
@login_required
def collect_bin_route(bin_type):
    """Dashboard Quick Action: mark a bin as collected. Resets the level, logs
    the collection to the acting user, awards eco points, and broadcasts
    bin_update so all open dashboards reflect it live."""
    if bin_type not in ('wetBin', 'dryBin'):
        return jsonify({'error': 'Unknown bin'}), 404
    result = models.collect_bin(bin_type, session.get('user_id'))
    if result is None:
        return jsonify({'error': 'Bin not found'}), 404
    bins = models.get_bins()
    predictions = models.get_predictions()
    socketio.emit('bin_update', {
        'wetBin': bins.get('wetBin', {}), 'dryBin': bins.get('dryBin', {}),
        'predictions': predictions, 'timestamp': datetime.now().isoformat()
    })
    evaluate_user(session.get('user_id'))
    return jsonify({'status': 'ok', 'result': result})


@bins_bp.route('/bins/reset', methods=['POST'])
def reset_bins():
    models.reset_bins()
    socketio.emit('bin_update', {
        'wetBin': {'id': 'wetBin', 'level': 0, 'status': 'empty'},
        'dryBin': {'id': 'dryBin', 'level': 0, 'status': 'empty'},
        'timestamp': datetime.now().isoformat()
    })
    socketio.emit('confetti', {})  # Trigger confetti on clients
    return jsonify({'status': 'ok', 'message': 'Bins reset'})


# ============ Locations (map + locations admin page) ============

@bins_bp.route('/locations', methods=['GET'])
def get_locations():
    return jsonify(models.get_locations())


@bins_bp.route('/locations', methods=['POST'])
@login_required
def create_location():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Location name is required'}), 400
    try:
        lat = float(data['lat']) if data.get('lat') not in (None, '') else None
        lng = float(data['lng']) if data.get('lng') not in (None, '') else None
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid coordinates'}), 400
    loc = models.create_location(
        name,
        address=(data.get('address') or '').strip(),
        icon=(data.get('icon') or '🏢'),
        bins=int(data.get('bins') or 2),
        lat=lat, lng=lng)
    models.add_activity('location', f'📍 Location added: {name}', notify=True)
    return jsonify(loc), 201


@bins_bp.route('/locations/<int:location_id>', methods=['PUT'])
@login_required
def update_location(location_id):
    if not models.get_location(location_id):
        return jsonify({'error': 'Location not found'}), 404
    data = request.get_json() or {}
    for key in ('lat', 'lng', 'bins'):
        if data.get(key) not in (None, ''):
            try:
                data[key] = float(data[key]) if key != 'bins' else int(data[key])
            except (TypeError, ValueError):
                return jsonify({'error': f'Invalid value for {key}'}), 400
    loc = models.update_location(
        location_id,
        name=(data.get('name') or '').strip() or None,
        address=(data.get('address') or '').strip() or None,
        icon=(data.get('icon') or None),
        bins=data.get('bins'),
        lat=data.get('lat'), lng=data.get('lng'))
    models.add_activity('location', f'📍 Location updated: {loc["name"]}')
    return jsonify(loc)


@bins_bp.route('/locations/<int:location_id>', methods=['DELETE'])
@login_required
def delete_location(location_id):
    if not models.get_location(location_id):
        return jsonify({'error': 'Location not found'}), 404
    models.delete_location(location_id)
    models.add_activity('location', '📍 Location deleted')
    return jsonify({'status': 'ok', 'id': location_id})


# ============ Maintenance ============

_ISSUE_TYPES = ('sensor', 'overflow', 'blocked', 'power', 'damage', 'other')


@bins_bp.route('/maintenance', methods=['GET'])
@admin_required
def get_maintenance():
    return jsonify({
        'logs': models.get_maintenance_logs(),
        'stats': models.get_maintenance_stats(),
    })


@bins_bp.route('/maintenance', methods=['POST'])
@admin_required
def report_maintenance():
    data = request.get_json() or {}
    bin_id = (data.get('binId') or '').strip()
    issue_type = (data.get('issueType') or '').strip().lower()
    description = (data.get('description') or '').strip()
    if bin_id not in ('wetBin', 'dryBin') and bin_id:
        return jsonify({'error': 'Unknown bin'}), 400
    if issue_type not in _ISSUE_TYPES:
        return jsonify({'error': 'Invalid issue type'}), 400
    if not description:
        return jsonify({'error': 'Description is required'}), 400
    log = models.create_maintenance_log(bin_id, issue_type, description)
    label = 'Wet' if bin_id == 'wetBin' else ('Dry' if bin_id == 'dryBin' else 'System')
    models.add_activity('maintenance',
        f'🔧 {label} bin maintenance issue reported: {issue_type}', notify=True)
    return jsonify(log), 201


@bins_bp.route('/maintenance/<int:log_id>/resolve', methods=['POST'])
@admin_required
def resolve_maintenance(log_id):
    log = models.get_maintenance_log(log_id)
    if not log:
        return jsonify({'error': 'Issue not found'}), 404
    models.resolve_maintenance_log(log_id)
    models.add_activity('maintenance',
        f'✅ Maintenance issue #{log_id} resolved', notify=True)
    return jsonify({'status': 'ok', 'id': log_id})
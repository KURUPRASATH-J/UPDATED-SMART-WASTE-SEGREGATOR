from flask import Blueprint, jsonify, request, session

import models

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api')


@analytics_bp.route('/dashboard/summary', methods=['GET'])
def dashboard_summary():
    """Dashboard load payload: stats + predictions + gamification + hourly trend
    plus the dashboard widget data (anomalies, today impact, weekly comparison,
    device health, goal nudge, collection schedule) in one call."""
    hours = request.args.get('hours', 24, type=int)
    user_id = session.get('user_id')
    gamification = models.get_user_gamification(user_id) if user_id else {
        'ecoScore': 0, 'streakDays': 0, 'totalWasteKg': 0, 'badges': [], 'allBadges': [], 'challenges': []
    }
    return jsonify({
        'stats': models.get_stats(),
        'predictions': models.get_predictions(),
        'gamification': gamification,
        'hourly': models.get_hourly_averages(None, hours),
        'unread': models.get_unread_activity_count(),
        'anomalies': models.get_anomalies(3),
        'today': models.get_today_impact(),
        'weekly': models.get_weekly_comparison(14),
        'health': models.get_device_health(),
        'goal': models.get_goal_nudge(user_id),
        'schedule': models.get_schedule_summary(user_id),
    })


@analytics_bp.route('/readings', methods=['GET'])
def get_readings():
    bin_type = request.args.get('bin', None)
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 200, type=int)
    include_test = request.args.get('include_test', '0') == '1'
    return jsonify(models.get_readings(bin_type, hours, limit, include_test))


@analytics_bp.route('/readings/hourly', methods=['GET'])
def get_hourly():
    bin_type = request.args.get('bin', None)
    hours = request.args.get('hours', 24, type=int)
    include_test = request.args.get('include_test', '0') == '1'
    return jsonify(models.get_hourly_averages(bin_type, hours, include_test))


@analytics_bp.route('/stats', methods=['GET'])
def get_stats():
    include_test = request.args.get('include_test', '0') == '1'
    return jsonify(models.get_stats(include_test))


@analytics_bp.route('/impact', methods=['GET'])
def get_impact():
    return jsonify(models.get_impact())


@analytics_bp.route('/activity', methods=['GET'])
def get_activity():
    limit = request.args.get('limit', 50, type=int)
    return jsonify(models.get_activity(limit))


@analytics_bp.route('/notifications', methods=['GET'])
def get_notifications():
    limit = request.args.get('limit', 30, type=int)
    return jsonify(models.get_activity(limit))


@analytics_bp.route('/notifications/unread-count', methods=['GET'])
def get_unread_count():
    return jsonify({'count': models.get_unread_activity_count()})


@analytics_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    models.mark_activity_read(notification_id)
    return jsonify({'status': 'ok', 'id': notification_id})


@analytics_bp.route('/notifications/read-all', methods=['POST'])
def mark_notifications_read_all():
    models.mark_all_activity_read()
    return jsonify({'status': 'ok'})


@analytics_bp.route('/notifications/<int:notification_id>', methods=['DELETE'])
def delete_notification(notification_id):
    models.delete_activity_row(notification_id)
    return jsonify({'status': 'ok', 'id': notification_id})


@analytics_bp.route('/notifications/clear-all', methods=['DELETE'])
def clear_notifications():
    models.clear_activity()
    return jsonify({'status': 'ok'})


@analytics_bp.route('/predictions', methods=['GET'])
def get_predictions():
    return jsonify(models.get_predictions())


@analytics_bp.route('/anomalies', methods=['GET'])
def get_anomalies():
    limit = request.args.get('limit', 20, type=int)
    return jsonify(models.get_anomalies(limit))
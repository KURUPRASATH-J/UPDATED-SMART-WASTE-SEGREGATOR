from flask import Blueprint, jsonify, request, session

import models
from extensions import login_required

gamification_bp = Blueprint('gamification', __name__, url_prefix='/api/gamification')


@gamification_bp.route('', methods=['GET'])
def get_gamification():
    user_id = session.get('user_id')
    if not user_id:
        # Honest zero-state for logged-out visitors (no fabricated gamification)
        return jsonify({'ecoScore': 0, 'streakDays': 0, 'totalWasteKg': 0, 'badges': [], 'allBadges': [], 'challenges': []})
    return jsonify(models.get_user_gamification(user_id))


@gamification_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    limit = request.args.get('limit', 20, type=int)
    period = request.args.get('period', 'all')
    return jsonify(models.get_leaderboard(limit, period))


@gamification_bp.route('/award', methods=['POST'])
def award_points():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.get_json()
    points = data.get('points', 0) if data else 0
    models.award_eco_points(session['user_id'], points)
    return jsonify({'status': 'ok'})


@gamification_bp.route('/analytics-view', methods=['POST'])
@login_required
def analytics_view():
    """Record an analytics page view (feeds the data_nerd badge checker)."""
    models.record_user_event(session['user_id'], 'analytics_view')
    return jsonify({'status': 'ok'})
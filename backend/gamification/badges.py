"""
Badge auto-evaluation engine and challenge progress wiring.

Each entry in BADGE_CHECKERS maps a seeded badge id to a checker function of the
form (user_id, conn) -> bool. `evaluate_user` runs all checkers after a relevant
event (reading, collection, login) and emits a Socket.IO `badge_unlocked` event
for every newly earned badge. Active challenges also get their progress/state
upserted into user_challenges.
"""
import sqlite3
from datetime import datetime, timedelta
from functools import partial

from extensions import get_db, socketio


def _checker_zero_overflow(user_id, conn):
    """No bin has reached 90% in the last 7 days."""
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM readings WHERE level >= 90 AND timestamp >= datetime('now', '-7 days')"
    ).fetchone()
    return row['c'] == 0


def _checker_collector(user_id, conn, threshold):
    """The acting user has triggered at least `threshold` confirmed collections."""
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM collections WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row['c'] >= threshold


def _checker_night_owl(user_id, conn):
    """User activity (a collection or a logged event) happened after midnight (before 06:00)."""
    collection = conn.execute(
        "SELECT COUNT(*) AS c FROM collections WHERE user_id = ? AND CAST(strftime('%H', collected_at) AS INTEGER) < 6",
        (user_id,),
    ).fetchone()
    events = conn.execute(
        "SELECT COUNT(*) AS c FROM user_events WHERE user_id = ? AND CAST(strftime('%H', created_at) AS INTEGER) < 6",
        (user_id,),
    ).fetchone()
    return (collection['c'] or 0) + (events['c'] or 0) > 0


def _checker_data_nerd(user_id, conn):
    """The user viewed analytics at least 10 times."""
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM user_events WHERE user_id = ? AND event_type = 'analytics_view'",
        (user_id,),
    ).fetchone()
    return row['c'] >= 10


BADGE_CHECKERS = {
    'zero_overflow': _checker_zero_overflow,
    'collector_10': partial(_checker_collector, threshold=10),
    'collector_50': partial(_checker_collector, threshold=50),
    'night_owl': _checker_night_owl,
    'data_nerd': _checker_data_nerd,
}


def _has_badge(conn, user_id, badge_id):
    row = conn.execute(
        "SELECT 1 FROM user_badges WHERE user_id = ? AND badge_id = ?", (user_id, badge_id)
    ).fetchone()
    return row is not None


def _insert_badge(conn, user_id, badge_id):
    try:
        conn.execute("INSERT INTO user_badges (user_id, badge_id) VALUES (?, ?)", (user_id, badge_id))
        return True
    except sqlite3.IntegrityError:
        return False


def evaluate_badges(user_id, conn):
    """Run all badge checkers for a user; award + emit anything newly earned."""
    unlocked = []
    for badge_id, checker in BADGE_CHECKERS.items():
        if _has_badge(conn, user_id, badge_id):
            continue
        try:
            earned = checker(user_id, conn)
        except Exception:
            earned = False
        if not earned:
            continue
        if _insert_badge(conn, user_id, badge_id):
            meta = conn.execute(
                "SELECT id, name, description, icon FROM badges WHERE id = ?", (badge_id,)
            ).fetchone()
            badge = dict(meta) if meta else {'id': badge_id}
            unlocked.append(badge)
            socketio.emit('badge_unlocked', {
                'userId': user_id,
                'badgeId': badge_id,
                'name': badge.get('name', badge_id),
                'description': badge.get('description', ''),
                'icon': badge.get('icon', ''),
                'timestamp': datetime.now().isoformat(),
            })
            from models import add_activity_db
            add_activity_db(conn, 'badge', f'Badge unlocked: {badge.get("name", badge_id)}', notify=True)
    return unlocked


def _clean_overflow_days(conn, days=7):
    """Days in the last `days` that were observed AND never exceeded 90% fill."""
    clean = 0
    for offset in range(days):
        day = (datetime.now() - timedelta(days=offset)).strftime('%Y-%m-%d')
        total = conn.execute(
            "SELECT COUNT(*) AS c, MAX(level) AS mx FROM readings WHERE date(timestamp) = ?", (day,)
        ).fetchone()
        if total['c'] and total['mx'] is not None and total['mx'] < 90:
            clean += 1
    return clean


def update_challenge_progress(user_id, conn):
    """Recompute progress/completed for every active challenge of this user."""
    rows = conn.execute(
        "SELECT id, title, metric, target_value FROM challenges WHERE active = 1"
    ).fetchall()
    if not rows:
        return []
    user = conn.execute(
        "SELECT eco_score, streak_days FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    results = []
    for ch in rows:
        metric = ch['metric']
        target = float(ch['target_value'] or 0)
        progress = 0.0
        if metric == 'eco_score_month':
            progress = min(float(user['eco_score']), target) if user else 0.0
        elif metric == 'login_streak':
            progress = min(float(user['streak_days']), target) if user else 0.0
        elif metric == 'avg_dry_below':
            avg = conn.execute(
                "SELECT AVG(level) AS a FROM readings WHERE bin_type = 'dryBin' AND timestamp >= datetime('now', '-7 days')"
            ).fetchone()['a']
            if avg is not None and float(avg) < target:
                progress = target
        elif metric == 'no_overflow_days':
            progress = min(float(_clean_overflow_days(conn, int(target))), target)
        completed = 1 if progress >= target else 0
        conn.execute(
            "INSERT OR REPLACE INTO user_challenges (user_id, challenge_id, progress, completed) VALUES (?,?,?,?)",
            (user_id, ch['id'], progress, completed),
        )
        results.append({
            'challengeId': ch['id'],
            'title': ch['title'],
            'metric': metric,
            'targetValue': target,
            'progress': progress,
            'completed': completed,
        })
    return results


def evaluate_user(user_id):
    """Top-level: award badges + update challenge progress after an event."""
    if not user_id:
        return {'badges': [], 'challenges': []}
    conn = get_db()
    try:
        unlocked = evaluate_badges(user_id, conn)
        challenges = update_challenge_progress(user_id, conn)
        conn.commit()
        return {'badges': unlocked, 'challenges': challenges}
    finally:
        conn.close()
"""
Database models for Smart Waste Segregator v3.0
Enhanced with: Gamification, Predictions, Anomaly Detection, Admin, Backup
"""
import sqlite3
import os
import json
import re
import shutil
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from config import DB_PATH
from extensions import get_db, socketio

try:
    from ml import fill_predictor as _ml_fill_predictor
    from ml import anomaly_detector as _ml_anomaly_detector
except ImportError:  # ml package unavailable -> keep classic formulas/alerts
    _ml_fill_predictor = None
    _ml_anomaly_detector = None


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT DEFAULT '',
            avatar_color TEXT DEFAULT '#00d4ff',
            role TEXT DEFAULT 'user',
            must_change_password INTEGER DEFAULT 0,
            eco_score INTEGER DEFAULT 0,
            streak_days INTEGER DEFAULT 0,
            streak_last_date TEXT,
            total_waste_kg REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS bins (
            id TEXT PRIMARY KEY,
            level INTEGER DEFAULT 0,
            distance REAL DEFAULT 0.0,
            status TEXT DEFAULT 'empty',
            fill_rate REAL DEFAULT 0.0,
            time_to_full_min INTEGER DEFAULT 0,
            weight_kg REAL DEFAULT 0.0,
            gas_level INTEGER DEFAULT 0,
            location_name TEXT DEFAULT 'Main',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_type TEXT NOT NULL,
            level INTEGER NOT NULL,
            distance REAL,
            weight_kg REAL DEFAULT 0.0,
            gas_level INTEGER DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL DEFAULT 'device'
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            data TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS device_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            user_id INTEGER,
            key TEXT,
            value TEXT,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_type TEXT NOT NULL,
            level_before INTEGER,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL DEFAULT 'device'
        );
        -- Gamification: Badges
        CREATE TABLE IF NOT EXISTS badges (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT '🏅',
            category TEXT DEFAULT 'general',
            requirement TEXT
        );
        CREATE TABLE IF NOT EXISTS user_badges (
            user_id INTEGER,
            badge_id TEXT,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, badge_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (badge_id) REFERENCES badges(id)
        );
        -- Gamification: Challenges
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT '🎯',
            target_value REAL,
            metric TEXT,
            start_date TEXT,
            end_date TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS user_challenges (
            user_id INTEGER,
            challenge_id INTEGER,
            progress REAL DEFAULT 0,
            completed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, challenge_id)
        );
        -- Gamification: User events (badge/challenge metrics)
        CREATE TABLE IF NOT EXISTS user_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        -- Predictions
        CREATE TABLE IF NOT EXISTS predictions (
            bin_type TEXT PRIMARY KEY,
            fill_rate_per_hour REAL DEFAULT 0,
            time_to_full_hours REAL DEFAULT 0,
            predicted_full_at TEXT,
            confidence REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        -- Anomalies
        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_type TEXT,
            anomaly_type TEXT,
            message TEXT,
            level_before INTEGER,
            level_after INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL DEFAULT 'device'
        );
        -- Bin locations (map + locations admin page)
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT DEFAULT '',
            icon TEXT DEFAULT '🏢',
            bins INTEGER DEFAULT 2,
            lat REAL,
            lng REAL,
            wet_level INTEGER DEFAULT 0,
            dry_level INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        -- Maintenance work log (admin page)
        CREATE TABLE IF NOT EXISTS maintenance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id TEXT,
            issue_type TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        );
        -- Support chat (per-user conversation history, persisted in the DB)
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT NOT NULL CHECK (role IN ('user','bot')),
            source TEXT DEFAULT 'faq',
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

    # Migration: attribute collections to the acting user (old DBs lack the column)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(collections)").fetchall()]
    if 'user_id' not in cols:
        conn.execute("ALTER TABLE collections ADD COLUMN user_id INTEGER")

    # Migration: profile picture URL (old DBs lack the column)
    user_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if 'avatar_url' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''")

    # Migration: forced password change for accounts seeded with a known default
    # (currently the bootstrap admin). 0 = normal account, 1 = must set a new
    # password before any admin page or /api/admin/* call will work.
    if 'must_change_password' not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0")

    # Migration: persisted read/unread flag on activity rows (old DBs lack the column)
    act_cols = [r[1] for r in conn.execute("PRAGMA table_info(activity)").fetchall()]
    if 'read' not in act_cols:
        conn.execute("ALTER TABLE activity ADD COLUMN read INTEGER DEFAULT 0")

    # Migration: provenance label on readings/collections/anomalies. Test data
    # (simulated posts, QA harness) carries source='test' so the dashboard can
    # exclude it; legacy rows default to 'device'.
    for _t in ('readings', 'collections', 'anomalies'):
        _t_cols = [r[1] for r in conn.execute(f"PRAGMA table_info({_t})").fetchall()]
        if 'source' not in _t_cols:
            conn.execute(f"ALTER TABLE {_t} ADD COLUMN source TEXT NOT NULL DEFAULT 'device'")

    # Migration: server-persisted settings (theme + advanced toggles were
    # previously browser-localStorage only). The settings table is a key/value
    # store, so no ALTER is required; this backfills the new keys with shared
    # defaults for existing users so GET /api/settings exposes them immediately.
    _set_cols = {r[1] for r in conn.execute("PRAGMA table_info(settings)").fetchall()}
    if {'user_id', 'key', 'value'} <= _set_cols:
        for _uid_row in conn.execute("SELECT id FROM users").fetchall():
            for _k, _v in DEFAULT_SETTINGS.items():
                conn.execute("INSERT OR IGNORE INTO settings (user_id, key, value) VALUES (?,?,?)",
                    (_uid_row['id'], _k, _v))

    cursor.execute("INSERT OR IGNORE INTO bins (id, level, status) VALUES ('wetBin', 0, 'empty')")
    cursor.execute("INSERT OR IGNORE INTO bins (id, level, status) VALUES ('dryBin', 0, 'empty')")
    cursor.execute("INSERT OR IGNORE INTO device_state (key, value) VALUES ('presence_detected', 'false')")
    cursor.execute("INSERT OR IGNORE INTO device_state (key, value) VALUES ('presence_distance', '0')")
    cursor.execute("INSERT OR IGNORE INTO device_state (key, value) VALUES ('lid_status', 'closed')")

    # Seed default badges
    default_badges = [
        ('first_login', 'First Steps', 'Logged in for the first time', '🚀', 'general', 'login_count>=1'),
        ('first_week', 'One Week Strong', 'Used the system for 7 days', '📅', 'streak', 'streak>=7'),
        ('two_weeks', 'Fortnight Hero', '14-day streak', '🔥', 'streak', 'streak>=14'),
        ('month_streak', 'Monthly Champion', '30-day streak', '👑', 'streak', 'streak>=30'),
        ('eco_starter', 'Eco Starter', 'Reach 100 eco score', '🌱', 'score', 'eco_score>=100'),
        ('eco_warrior', 'Eco Warrior', 'Reach 500 eco score', '🌍', 'score', 'eco_score>=500'),
        ('eco_legend', 'Eco Legend', 'Reach 1000 eco score', '🏆', 'score', 'eco_score>=1000'),
        ('zero_overflow', 'Zero Overflow', 'No bin overflow for a week', '🛡️', 'achievement', 'no_overflow_7d'),
        ('collector_10', '10 Collections', 'Bins emptied 10 times', '♻️', 'collection', 'collections>=10'),
        ('collector_50', '50 Collections', 'Bins emptied 50 times', '🥇', 'collection', 'collections>=50'),
        ('night_owl', 'Night Owl', 'Used system after midnight', '🦉', 'special', 'night_use'),
        ('data_nerd', 'Data Nerd', 'Viewed analytics 10 times', '📊', 'special', 'analytics_views>=10'),
    ]
    for b in default_badges:
        cursor.execute("INSERT OR IGNORE INTO badges (id,name,description,icon,category,requirement) VALUES (?,?,?,?,?,?)", b)

    # Seed default challenges
    default_challenges = [
        ('Reduce Dry Waste', 'Keep dry bin below 50% average this week', '♻️', 50, 'avg_dry_below', None, None),
        ('Zero Overflow Week', 'No bin reaches 90% for 7 days', '🛡️', 7, 'no_overflow_days', None, None),
        ('Eco Score 100', 'Earn 100 eco points this month', '🌟', 100, 'eco_score_month', None, None),
        ('Daily Check-in', 'Log in 5 days in a row', '📅', 5, 'login_streak', None, None),
    ]
    for c in default_challenges:
        conn.execute("""INSERT OR IGNORE INTO challenges (title,description,icon,target_value,metric,start_date,end_date)
            SELECT ?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM challenges WHERE title=?)""",
            (*c, c[0]))

    # Migration: built-in admin account. Credentials come from ADMIN_USERNAME /
    # ADMIN_PASSWORD so no default secret lives in the source. The fallback
    # values below are dev-only and are flagged loudly at startup.
    #
    # The seeded account always gets must_change_password=1, so a leaked default
    # password cannot be used to reach the admin portal without first choosing a
    # strong one. Re-runs re-affirm the role and the flag, and never overwrite a
    # password the operator has already changed.
    admin_username = os.environ.get('ADMIN_USERNAME', '').strip() or 'admin'
    admin_password = os.environ.get('ADMIN_PASSWORD', '')
    if not admin_password:
        admin_password = 'admin123'
        print("[WARNING] ADMIN_PASSWORD is not set - seeding the built-in admin with the "
              "weak development default. Set ADMIN_PASSWORD in backend/.env before "
              "sharing this app.")

    admin_row = conn.execute(
        "SELECT id, role FROM users WHERE username = ?", (admin_username,)).fetchone()
    if admin_row is None:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, full_name, role, must_change_password) "
            "VALUES (?,?,?,?,?,1)",
            (admin_username, f'{admin_username}@local.example',
             generate_password_hash(admin_password), 'System Administrator', 'admin'))
        adm_id = conn.execute("SELECT id FROM users WHERE username = ?",
                              (admin_username,)).fetchone()['id']
        for _k, _v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (user_id, key, value) VALUES (?,?,?)", (adm_id, _k, _v))
    else:
        # Idempotent re-run: re-affirm the role, and only force a password change
        # while the stored hash is still the known weak default. Once the
        # operator picks their own password this stops flagging the account, so
        # the flag does not come back on every restart.
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (admin_row['id'],))
        _row = conn.execute("SELECT password_hash FROM users WHERE id = ?",
                            (admin_row['id'],)).fetchone()
        if _row and check_password_hash(_row['password_hash'], 'admin123'):
            conn.execute("UPDATE users SET must_change_password = 1 WHERE id = ?",
                         (admin_row['id'],))

    conn.commit()
    conn.close()
    print("Database initialized at:", DB_PATH)


# ============ User Operations ============

def create_user(username, email, password, full_name=''):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, email, password_hash, full_name) VALUES (?, ?, ?, ?)",
            (username, email, generate_password_hash(password), full_name))
        uid = cursor.lastrowid
        # Award first login badge
        conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?, 'first_login')", (uid,))
        conn.commit()
        return uid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def authenticate_user(username, password):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, username)).fetchone()
    conn.close()
    if user and check_password_hash(user['password_hash'], password):
        return dict(user)
    return None


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def verify_password(user_id, password):
    """Check a plaintext password against a stored user. Returns the user dict
    on success, None otherwise. Used by the change-password flow so the caller
    must prove knowledge of the current password."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password_hash'], password or ''):
        return dict(user)
    return None


def set_password(user_id, new_password):
    """Replace a user's password and clear the forced-change flag."""
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                 (generate_password_hash(new_password), user_id))
    conn.commit()
    conn.close()


def get_user_by_username(username):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?",
                        (username, username)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_all_users():
    conn = get_db()
    users = conn.execute("SELECT id,username,email,full_name,role,eco_score,streak_days,created_at,last_login,avatar_url FROM users ORDER BY eco_score DESC").fetchall()
    conn.close()
    return [dict(u) for u in users]


def set_user_role(user_id, role):
    conn = get_db()
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    conn.close()


def set_avatar_url(user_id, avatar_url):
    """Persist the user's avatar URL (uploaded file or built-in preset)."""
    conn = get_db()
    conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    """Delete a user and every row that references them (FKs are ON)."""
    conn = get_db()
    for table in ('user_badges', 'user_challenges', 'user_events', 'settings'):
        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM collections WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def update_last_login(user_id):
    conn = get_db()
    now = datetime.now()
    user = conn.execute("SELECT streak_days, streak_last_date FROM users WHERE id = ?", (user_id,)).fetchone()
    streak = user['streak_days'] if user else 0
    last_date = user['streak_last_date'] if user else None
    today = now.strftime('%Y-%m-%d')
    if last_date == today:
        pass  # Already logged in today
    elif last_date == (now - timedelta(days=1)).strftime('%Y-%m-%d'):
        streak += 1  # Consecutive day
    else:
        streak = 1  # Reset streak
    conn.execute("UPDATE users SET last_login=?, streak_days=?, streak_last_date=? WHERE id=?",
                 (now, streak, today, user_id))
    # Check streak badges
    if streak >= 7:
        conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'first_week')", (user_id,))
    if streak >= 14:
        conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'two_weeks')", (user_id,))
    if streak >= 30:
        conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'month_streak')", (user_id,))
    conn.commit()
    conn.close()


# ============ Bin Operations ============

def update_bin(bin_type, level, distance=None, weight_kg=0, gas_level=0, user_id=None, source='device'):
    conn = get_db()
    now = datetime.now()

    # Test/simulated readings are recorded so the user can see the pipeline
    # work, but never touch bin state, predictions, anomalies or last_seen —
    # those must reflect the real device only.
    if source == 'test':
        label = 'Wet' if bin_type == 'wetBin' else 'Dry'
        conn.execute("INSERT INTO readings (bin_type,level,distance,weight_kg,gas_level,timestamp,source) VALUES (?,?,?,?,?,?,?)",
            (bin_type, level, distance or 0.0, weight_kg, gas_level, now, 'test'))
        add_activity_db(conn, 'level_update', f'[TEST] {label} bin: {level}% (simulated reading)', read=1)
        conn.commit()
        conn.close()
        return {'status': 'test', 'source': 'test'}

    status = 'full' if level >= 80 else ('half-full' if level >= 50 else 'empty')

    old = conn.execute("SELECT level, updated_at FROM bins WHERE id = ?", (bin_type,)).fetchone()
    old_level = old['level'] if old else 0
    old_time_str = old['updated_at'] if old else None

    # Calculate fill rate (%/hour)
    fill_rate = 0.0
    if old_time_str and old_level != level:
        try:
            old_time = datetime.strptime(str(old_time_str)[:19], '%Y-%m-%d %H:%M:%S')
            dt_hours = max((now - old_time).total_seconds() / 3600, 0.001)
            fill_rate = (level - old_level) / dt_hours
        except:
            pass

    # Time to full prediction - ML regression when a trained model exists for
    # this bin, otherwise the classic linear projection (valid until enough
    # readings have accumulated; see backend/ml/model_registry.py).
    ttf_min = 0
    if level < 100:
        model_ttf = None
        if _ml_fill_predictor is not None:
            try:
                model_ttf = _ml_fill_predictor.predict_ttf_min(
                    bin_type, level, now.hour, now.weekday(), fill_rate)
            except Exception:
                model_ttf = None
        if model_ttf is not None:
            ttf_min = model_ttf
        elif fill_rate > 0:
            ttf_min = int(((100 - level) / fill_rate) * 60)

    conn.execute("""INSERT OR REPLACE INTO bins (id,level,distance,status,fill_rate,time_to_full_min,weight_kg,gas_level,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (bin_type, level, distance or 0.0, status, round(fill_rate, 2), ttf_min, weight_kg, gas_level, now))

    conn.execute("INSERT INTO readings (bin_type,level,distance,weight_kg,gas_level,timestamp,source) VALUES (?,?,?,?,?,?,?)",
        (bin_type, level, distance or 0.0, weight_kg, gas_level, now, 'device'))

    # Update prediction
    conn.execute("""INSERT OR REPLACE INTO predictions (bin_type,fill_rate_per_hour,time_to_full_hours,predicted_full_at,confidence,updated_at)
        VALUES (?,?,?,?,?,?)""",
        (bin_type, round(fill_rate, 3), round(ttf_min / 60, 2) if ttf_min > 0 else 0,
         (now + timedelta(minutes=ttf_min)).isoformat() if ttf_min > 0 else None,
         min(0.95, max(0.3, 0.5 + fill_rate * 0.1)), now))

    # Anomaly detection - IsolationForest (level, fill_rate, hour) per bin when
    # a model exists, otherwise the legacy fixed >30 threshold.
    level_diff = abs(level - old_level)
    anomalous = None
    if _ml_anomaly_detector is not None:
        try:
            anomalous = _ml_anomaly_detector.is_anomalous(bin_type, level, fill_rate, now.hour)
        except Exception:
            anomalous = None
    if anomalous is None:
        anomalous = level_diff > 30 and old_level > 0
    if anomalous and level != old_level:
        anomaly_type = 'sudden_drop' if level < old_level else 'sudden_spike'
        msg = f'{"Sudden drop" if level < old_level else "Sudden spike"} in {bin_type}: {old_level}% → {level}%'
        conn.execute("INSERT INTO anomalies (bin_type,anomaly_type,message,level_before,level_after) VALUES (?,?,?,?,?)",
            (bin_type, anomaly_type, msg, old_level, level))
        add_activity_db(conn, 'anomaly', f'⚠️ {msg}', notify=True)

    # Collection detection
    collection_detected = False
    if old_level > 30 and level < 10:
        conn.execute("INSERT INTO collections (bin_type,level_before,user_id,collected_at,source) VALUES (?,?,?,?,?)",
            (bin_type, old_level, user_id, now, 'device'))
        add_activity_db(conn, 'collection',
            f'{"Wet" if bin_type == "wetBin" else "Dry"} bin collected (was {old_level}%)',
            notify=True)
        collection_detected = True
        # Award eco score to the acting user (from the authenticated session/request)
        if user_id:
            conn.execute("UPDATE users SET eco_score = eco_score + 10, total_waste_kg = total_waste_kg + ? WHERE id = ?",
                (weight_kg or old_level * 0.05, user_id))

    # Alert if crossing 80% (notifies when crossing into the 85%+ danger zone)
    if level >= 80 and old_level < 80:
        label = 'Wet' if bin_type == 'wetBin' else 'Dry'
        if level >= 85:
            add_activity_db(conn, 'alert',
                f'{label} bin at {level}% — please empty soon', notify=True)
        else:
            add_activity_db(conn, 'alert',
                f'{label} bin almost full ({level}%)')

    # Level update activity
    add_activity_db(conn, 'level_update',
        f'{"Wet" if bin_type == "wetBin" else "Dry"} bin: {level}% (dist: {distance or 0:.1f}cm)')

    # Check eco score badges (for the acting user only)
    if user_id:
        row = conn.execute("SELECT eco_score FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            score = row['eco_score']
            if score >= 100:
                conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'eco_starter')", (user_id,))
            if score >= 500:
                conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'eco_warrior')", (user_id,))
            if score >= 1000:
                conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'eco_legend')", (user_id,))

    conn.commit()
    conn.close()
    return {'status': status, 'collection': collection_detected, 'fill_rate': fill_rate, 'ttf_min': ttf_min}


def get_bins():
    conn = get_db()
    bins = {b['id']: dict(b) for b in conn.execute("SELECT * FROM bins").fetchall()}
    for bid in bins:
        c = conn.execute(
            "SELECT COUNT(*) as c FROM readings WHERE bin_type=? AND (source='device' OR source IS NULL)",
            (bid,)).fetchone()['c']
        bins[bid]['hasData'] = c > 0
    conn.close()
    return bins


def get_bin(bin_type):
    conn = get_db()
    b = conn.execute("SELECT * FROM bins WHERE id = ?", (bin_type,)).fetchone()
    conn.close()
    return dict(b) if b else None


def reset_bins():
    conn = get_db()
    now = datetime.now()
    conn.execute("UPDATE bins SET level=0, distance=0, status='empty', fill_rate=0, time_to_full_min=0, updated_at=?", (now,))
    add_activity_db(conn, 'reset', 'All bins reset to 0%', notify=True)
    conn.commit()
    conn.close()


def collect_bin(bin_type, user_id=None):
    """Manually mark one bin as collected (dashboard Quick Action).

    Resets the bin to empty, logs a collection attributed to the acting user,
    awards +10 eco points (plus waste-credit), emits an activity event, and
    returns the previous fill level so clients can show what changed."""
    conn = get_db()
    now = datetime.now()
    old = conn.execute("SELECT level FROM bins WHERE id = ?", (bin_type,)).fetchone()
    if not old:
        conn.close()
        return None
    old_level = old['level'] or 0
    conn.execute("UPDATE bins SET level=0, distance=0, status='empty', fill_rate=0, "
                 "time_to_full_min=0, updated_at=? WHERE id=?", (now, bin_type))
    if user_id:
        conn.execute("INSERT INTO collections (bin_type, level_before, user_id, collected_at, source) VALUES (?,?,?,?,?)",
                     (bin_type, old_level, user_id, now, 'device'))
        conn.execute("UPDATE users SET eco_score = eco_score + 10, "
                     "total_waste_kg = total_waste_kg + ? WHERE id=?",
                     (round(max(old_level * 0.05, 0.1), 2), user_id))
        row = conn.execute("SELECT eco_score FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            score = row['eco_score']
            if score >= 100:
                conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'eco_starter')", (user_id,))
            if score >= 500:
                conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'eco_warrior')", (user_id,))
            if score >= 1000:
                conn.execute("INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?,'eco_legend')", (user_id,))
    else:
        conn.execute("INSERT INTO collections (bin_type, level_before, collected_at, source) VALUES (?,?,?,?)",
                     (bin_type, old_level, now, 'device'))
    label = 'Wet' if bin_type == 'wetBin' else 'Dry'
    add_activity_db(conn, 'collection',
                    f'{label} bin collected (was {old_level}%)', notify=True)
    conn.commit()
    conn.close()
    return {'bin': bin_type, 'levelBefore': old_level, 'pointsAwarded': 10 if user_id else 0}


# ============ Locations ============

def get_locations():
    conn = get_db()
    rows = conn.execute("SELECT * FROM locations ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_location(location_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_location(name, address='', icon='🏢', bins=2, lat=None, lng=None):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO locations (name, address, icon, bins, lat, lng) VALUES (?,?,?,?,?,?)",
        (name, address, icon, bins, lat, lng))
    conn.commit()
    location_id = cur.lastrowid
    conn.close()
    return get_location(location_id)


def update_location(location_id, **fields):
    allowed = ('name', 'address', 'icon', 'bins', 'lat', 'lng', 'wet_level', 'dry_level')
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not sets:
        return get_location(location_id)
    cols = ', '.join(f"{k} = ?" for k in sets)
    conn = get_db()
    conn.execute(f"UPDATE locations SET {cols} WHERE id = ?", (*sets.values(), location_id))
    conn.commit()
    conn.close()
    return get_location(location_id)


def delete_location(location_id):
    conn = get_db()
    conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
    conn.commit()
    conn.close()


# ============ Maintenance ============

def get_maintenance_logs():
    conn = get_db()
    rows = conn.execute("SELECT * FROM maintenance_log ORDER BY reported_at DESC, id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_maintenance_log(bin_id, issue_type, description=''):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO maintenance_log (bin_id, issue_type, description) VALUES (?,?,?)",
        (bin_id, issue_type, description))
    conn.commit()
    log_id = cur.lastrowid
    conn.close()
    return get_maintenance_log(log_id)


def get_maintenance_log(log_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM maintenance_log WHERE id = ?", (log_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def resolve_maintenance_log(log_id):
    conn = get_db()
    cur = conn.execute(
        "UPDATE maintenance_log SET status = 'resolved', resolved_at = ? WHERE id = ? AND status != 'resolved'",
        (datetime.now(), log_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_maintenance_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM maintenance_log").fetchone()['c']
    open_count = conn.execute("SELECT COUNT(*) as c FROM maintenance_log WHERE status = 'open'").fetchone()['c']
    resolved = conn.execute("SELECT COUNT(*) as c FROM maintenance_log WHERE status = 'resolved'").fetchone()['c']
    conn.close()
    return {
        'total': total,
        'open': open_count,
        'inProgress': max(0, total - open_count - resolved),
        'resolved': resolved,
    }


# ============ Reading History ============

def get_readings(bin_type=None, hours=24, limit=100, include_test=False):
    conn = get_db()
    query = "SELECT * FROM readings WHERE timestamp >= datetime('now', ?)"
    params = [f'-{hours} hours']
    if not include_test:
        query += " AND (source='device' OR source IS NULL)"
    if bin_type:
        query += " AND bin_type = ?"
        params.append(bin_type)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_hourly_averages(bin_type=None, hours=24, include_test=False):
    conn = get_db()
    query = """SELECT bin_type, strftime('%Y-%m-%d %H:00', timestamp) as hour,
               ROUND(AVG(level), 1) as avg_level, COUNT(*) as readings_count
               FROM readings WHERE timestamp >= datetime('now', ?)"""
    params = [f'-{hours} hours']
    if not include_test:
        query += " AND (source='device' OR source IS NULL)"
    if bin_type:
        query += " AND bin_type = ?"
        params.append(bin_type)
    query += " GROUP BY bin_type, hour ORDER BY hour"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_weekly_comparison(days=14):
    """Daily average fill per bin over the last `days` days plus the whole-week
    comparison (this week vs the previous week) for the dashboard card.

    Returns contiguous daily series (None on days without readings) so the
    sparkline stays time-aligned, plus thisWeek/lastWeek means and the week-over-
    week change % per bin. `hasEnoughData` is False until >=2 distinct days have
    readings (drives the "Not enough data yet" empty state)."""
    conn = get_db()
    rows = conn.execute(
        """SELECT bin_type, date(timestamp) AS day,
                  ROUND(AVG(level), 1) AS avg_level
           FROM readings WHERE timestamp >= datetime('now', ?)
           AND (source='device' OR source IS NULL)
           GROUP BY bin_type, day ORDER BY day""", (f'-{days} days',)).fetchall()
    conn.close()
    daily = {'wetBin': {}, 'dryBin': {}}
    days_with_data = set()
    for r in rows:
        daily.setdefault(r['bin_type'], {})[r['day']] = r['avg_level']
        days_with_data.add(r['day'])
    labels = []
    for i in range(days - 1, -1, -1):
        labels.append(((datetime.now().date() - timedelta(days=i)).isoformat()))
    series = {
        'wet': [daily['wetBin'].get(d) for d in labels],
        'dry': [daily['dryBin'].get(d) for d in labels],
    }

    def _avg(vals):
        present = [v for v in vals if v is not None]
        return round(sum(present) / len(present), 2) if present else None

    def _delta(this, last):
        if this is None or last is None or last == 0:
            return None
        return round((this - last) / last * 100, 1)

    wet_this, wet_last = _avg(series['wet'][-7:]), _avg(series['wet'][-14:-7])
    dry_this, dry_last = _avg(series['dry'][-7:]), _avg(series['dry'][-14:-7])
    return {
        'labels': labels,
        'series': series,
        'thisWeek': {'wet': wet_this, 'dry': dry_this},
        'lastWeek': {'wet': wet_last, 'dry': dry_last},
        'changePct': {'wet': _delta(wet_this, wet_last), 'dry': _delta(dry_this, dry_last)},
        'hasEnoughData': len(days_with_data) >= 2,
    }


# ============ Activity Log ============

def add_activity_db(conn, event_type, message, data=None, notify=False, read=0):
    conn.execute("INSERT INTO activity (event_type, message, data, read) VALUES (?, ?, ?, ?)",
        (event_type, message, data, read))
    if notify:
        try:
            row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
            socketio.emit('notification_new', {
                'id': row['id'],
                'event_type': event_type,
                'message': message,
                'data': data,
                'timestamp': datetime.now().isoformat(),
                'read': 0,
            })
        except Exception:
            pass


def add_activity(event_type, message, data=None, notify=False):
    conn = get_db()
    add_activity_db(conn, event_type, message, data, notify=notify)
    conn.commit()
    conn.close()


def get_activity(limit=50):
    conn = get_db()
    rows = conn.execute("SELECT * FROM activity ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unread_activity_count():
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) AS c FROM activity WHERE read = 0").fetchone()
    conn.close()
    return row['c']


def mark_activity_read(notification_id):
    conn = get_db()
    conn.execute("UPDATE activity SET read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()


def mark_all_activity_read():
    conn = get_db()
    conn.execute("UPDATE activity SET read = 1")
    conn.commit()
    conn.close()


def delete_activity_row(notification_id):
    conn = get_db()
    conn.execute("DELETE FROM activity WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()


def clear_activity():
    conn = get_db()
    conn.execute("DELETE FROM activity")
    conn.commit()
    conn.close()


# ============ Device State ============

def update_device_state(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO device_state (key, value, updated_at) VALUES (?, ?, ?)",
        (key, str(value), datetime.now()))
    conn.commit()
    conn.close()


def get_device_state():
    conn = get_db()
    rows = conn.execute("SELECT * FROM device_state").fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}


def get_device_health(online_threshold_sec=30):
    """System/device health for the dashboard strip.

    Online windows use the most recent real device post (the ESP32 sends a
    reading every 5 s, so 30 s without one means the device likely went quiet).
    Only device-source posts update last_seen — simulated/test posts do not, so
    they can never flip the device to "online". battery/signal are intentionally
    None: the current firmware does not send them, and the UI hides those rows
    rather than faking values."""
    conn = get_db()
    dev = {r['key']: r['value'] for r in conn.execute("SELECT * FROM device_state").fetchall()}
    conn.close()
    last_seen = dev.get('last_seen') or ''
    online = False
    if last_seen:
        try:
            last_dt = datetime.strptime(str(last_seen)[:19], '%Y-%m-%d %H:%M:%S')
            online = (datetime.now() - last_dt).total_seconds() < online_threshold_sec
        except ValueError:
            online = False
    lid = (dev.get('lid_status') or 'closed').lower()
    return {
        'online': online,
        'lastSeen': last_seen or None,
        'onlineThresholdSec': online_threshold_sec,
        'lidStatus': lid,
        'presenceDetected': dev.get('presence_detected') == 'true',
        # Firmware doesn't send battery/signal yet — the UI hides these.
        'battery': None,
        'signal': None,
    }


# ============ Statistics ============

def get_stats(include_test=False):
    conn = get_db()
    bins = {b['id']: dict(b) for b in conn.execute("SELECT * FROM bins").fetchall()}
    for bid in bins:
        c = conn.execute(
            "SELECT COUNT(*) as c FROM readings WHERE bin_type=? AND (source='device' OR source IS NULL)",
            (bid,)).fetchone()['c']
        bins[bid]['hasData'] = c > 0

    src = '' if include_test else " AND (source='device' OR source IS NULL)"
    total_collections = conn.execute(
        "SELECT COUNT(*) as c FROM collections WHERE (source='device' OR source IS NULL)").fetchone()['c']
    today_readings = conn.execute(
        "SELECT COUNT(*) as c FROM readings WHERE timestamp >= date('now')" + src).fetchone()['c']
    total_readings = conn.execute(
        "SELECT COUNT(*) as c FROM readings WHERE 1=1" + src).fetchone()['c']
    test_readings = conn.execute(
        "SELECT COUNT(*) as c FROM readings WHERE source='test'").fetchone()['c']

    def _avg24(bt):
        row = conn.execute(
            "SELECT ROUND(AVG(level),1) as avg FROM readings WHERE bin_type=? "
            "AND timestamp >= datetime('now','-24 hours')" + src, (bt,)).fetchone()
        return row['avg']

    avg_wet = _avg24('wetBin')
    avg_dry = _avg24('dryBin')
    anomaly_count = conn.execute(
        "SELECT COUNT(*) as c FROM anomalies WHERE timestamp >= datetime('now', '-7 days') "
        "AND (source='device' OR source IS NULL)").fetchone()['c']
    device = get_device_state()
    # Peak hour (device readings only)
    peak = conn.execute(
        "SELECT strftime('%H',timestamp) as h, COUNT(*) as c FROM readings WHERE 1=1" + src +
        " GROUP BY h ORDER BY c DESC LIMIT 1").fetchone()
    peak_hour = f"{peak['h']}:00" if peak else '--'
    last_row = conn.execute(
        "SELECT MAX(timestamp) as t FROM readings WHERE 1=1" + src).fetchone()
    device_last_reading = last_row['t'] if last_row and last_row['t'] else None
    conn.close()
    return {
        'bins': bins, 'device': device,
        'totalCollections': total_collections, 'todayReadings': today_readings,
        'totalReadings': total_readings, 'testTotalReadings': test_readings,
        'avgWet24h': avg_wet, 'avgDry24h': avg_dry,
        'hasAvgWet24h': avg_wet is not None, 'hasAvgDry24h': avg_dry is not None,
        'deviceReady': total_readings > 0, 'deviceLastReading': device_last_reading,
        'co2Saved': round(total_collections * 0.5, 1),
        'ecoScore': total_collections * 10,
        'anomalyCount': anomaly_count, 'peakHour': peak_hour,
        'waterSaved': total_collections * 25,
        'treesSaved': round(total_collections * 0.05, 1)
    }


# ============ Predictions ============

def get_predictions():
    conn = get_db()
    rows = conn.execute("SELECT * FROM predictions").fetchall()
    conn.close()
    return {r['bin_type']: dict(r) for r in rows}


# ============ Environmental Impact ============

# Impact conversion constants (reused from get_stats()): every collection
# saves ~0.5 kg CO2, ~25 L water, keeps ~0.05 trees standing, and the bin has
# been emptied instead of hauled (0.25 kWh per collection + a tiny per-reading
# sensor overhead).
_CARBON_GOAL_KG = 100          # monthly target shown on the impact page
_WATER_GOAL_L = 1000           # monthly target shown on the impact page


def get_impact():
    """Server-computed impact summary + goal progress for the impact page."""
    conn = get_db()
    total_collections = conn.execute("SELECT COUNT(*) as c FROM collections WHERE (source='device' OR source IS NULL)").fetchone()['c']
    total_readings = conn.execute("SELECT COUNT(*) as c FROM readings WHERE (source='device' OR source IS NULL)").fetchone()['c']
    avg_wet = conn.execute(
        "SELECT ROUND(AVG(level),1) as a FROM readings WHERE bin_type='wetBin' AND timestamp >= datetime('now','-24 hours') AND (source='device' OR source IS NULL)"
    ).fetchone()['a']
    avg_dry = conn.execute(
        "SELECT ROUND(AVG(level),1) as a FROM readings WHERE bin_type='dryBin' AND timestamp >= datetime('now','-24 hours') AND (source='device' OR source IS NULL)"
    ).fetchone()['a']
    conn.close()

    trees_saved = round(total_collections * 0.05, 1)
    co2_reduced = round(total_collections * 0.5, 1)
    water_saved = total_collections * 25
    energy_saved = round(total_collections * 0.25 + total_readings * 0.01, 1)

    carbon_percent = max(0, min(100, int(co2_reduced * 100 / _CARBON_GOAL_KG)))
    water_percent = max(0, min(100, int(water_saved * 100 / _WATER_GOAL_L)))
    diversion_percent = None
    if avg_wet is not None and avg_dry is not None and (avg_wet + avg_dry) > 0:
        diversion_percent = max(0, min(100, round(100 - (avg_wet + avg_dry) / 2)))

    return {
        'treesSaved': trees_saved,
        'co2Reduced': co2_reduced,
        'waterSaved': water_saved,
        'energySaved': energy_saved,
        'totalCollections': total_collections,
        'readingsCount': total_readings,
        'carbonGoal': _CARBON_GOAL_KG,
        'carbonProgress': carbon_percent,
        'waterGoal': _WATER_GOAL_L,
        'waterProgress': water_percent,
        'diversionProgress': diversion_percent,
        'drivingKm': round(co2_reduced / 0.2, 1),        # ~200 g CO2/km driven
        'homeDays': round(energy_saved / 30, 1),          # ~30 kWh/day typical home
        'showerHours': round(water_saved / 100, 1),       # ~100 L per shower-hour
        'phoneCharges': round(energy_saved * 1000 / 8),   # ~8 Wh per phone charge
    }


def get_today_impact():
    """Today-only environment snapshot for the dashboard card. Lifetime figures
    live on the Impact page (get_impact()); per-collection conversion constants
    match get_stats() exactly so both stay consistent. Counts real (device +
    manual) collections only — simulated/test data is excluded."""
    conn = get_db()
    today_collections = conn.execute(
        "SELECT COUNT(*) AS c FROM collections WHERE collected_at >= date('now') "
        "AND (source='device' OR source IS NULL)").fetchone()['c']
    conn.close()
    return {
        'collections': today_collections,
        'co2Saved': round(today_collections * 0.5, 1),
        'waterSaved': today_collections * 25,
        'treesSaved': round(today_collections * 0.05, 2),
    }


def get_anomalies(limit=20):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM anomalies WHERE (source='device' OR source IS NULL) ORDER BY timestamp DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============ Gamification ============

def get_user_gamification(user_id):
    conn = get_db()
    user = conn.execute("SELECT eco_score, streak_days, total_waste_kg FROM users WHERE id=?", (user_id,)).fetchone()
    badges = conn.execute("""SELECT b.*, ub.earned_at FROM user_badges ub
        JOIN badges b ON ub.badge_id = b.id WHERE ub.user_id = ? ORDER BY ub.earned_at DESC""", (user_id,)).fetchall()
    all_badges = conn.execute("SELECT * FROM badges").fetchall()
    challenges = conn.execute("""SELECT c.*, COALESCE(uc.progress,0) as progress, COALESCE(uc.completed,0) as completed
        FROM challenges c LEFT JOIN user_challenges uc ON c.id=uc.challenge_id AND uc.user_id=?
        WHERE c.active=1""", (user_id,)).fetchall()
    conn.close()
    return {
        'ecoScore': user['eco_score'] if user else 0,
        'streakDays': user['streak_days'] if user else 0,
        'totalWasteKg': user['total_waste_kg'] if user else 0,
        'badges': [dict(b) for b in badges],
        'allBadges': [dict(b) for b in all_badges],
        'challenges': [dict(c) for c in challenges]
    }


def get_goal_nudge(user_id):
    """One-line motivational hint for the dashboard: how close the user is to
    their nearest unearned badge or in-progress challenge. Returns
    {'hasGoal', 'allEarned', 'text', 'icon', ...}."""
    if not user_id:
        return {'hasGoal': False, 'allEarned': False, 'text': None, 'icon': None}
    conn = get_db()
    user = conn.execute("SELECT eco_score, streak_days FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return {'hasGoal': False, 'allEarned': False, 'text': None, 'icon': None}
    score = user['eco_score'] or 0
    streak = user['streak_days'] or 0
    earned = {r['badge_id'] for r in conn.execute(
        "SELECT badge_id FROM user_badges WHERE user_id = ?", (user_id,)).fetchall()}
    collections = conn.execute(
        "SELECT COUNT(*) c FROM collections WHERE user_id = ?", (user_id,)).fetchone()['c'] or 0
    views = conn.execute(
        "SELECT COUNT(*) c FROM user_events WHERE user_id = ? AND event_type='analytics_view'",
        (user_id,)).fetchone()['c'] or 0
    overflow_days = conn.execute(
        "SELECT COUNT(DISTINCT date(timestamp)) c FROM readings WHERE timestamp >= datetime('now','-7 days') "
        "AND level >= 90 AND (source='device' OR source IS NULL)"
    ).fetchone()['c'] or 0
    clean_days = max(0, 7 - overflow_days)
    items = []
    for b in conn.execute("SELECT * FROM badges").fetchall():
        if b['id'] in earned:
            continue
        prog, target, unit = None, None, ''
        try:
            if b['id'] in ('collector_10', 'collector_50'):
                target = int((b['requirement'] or '').split('>=')[1]); prog = collections; unit = 'collection'
            elif b['id'] in ('eco_starter', 'eco_warrior', 'eco_legend'):
                target = int((b['requirement'] or '').split('>=')[1]); prog = score; unit = 'eco point'
            elif b['id'] in ('first_week', 'two_weeks', 'month_streak'):
                target = int((b['requirement'] or '').split('>=')[1]); prog = streak; unit = 'consecutive day'
            elif b['id'] == 'data_nerd':
                target = 10; prog = views; unit = 'analytics view'
            elif b['id'] == 'zero_overflow':
                target = 7; prog = clean_days; unit = 'clean day'
            else:
                continue
        except (ValueError, IndexError):
            continue
        if prog is None or target is None:
            continue
        items.append({'kind': 'badge', 'name': b['name'], 'icon': b['icon'],
                      'remaining': max(0, target - prog), 'unit': unit})
    for c in conn.execute(
        """SELECT c.title, c.icon, c.target_value,
                  COALESCE(uc.progress,0) progress, COALESCE(uc.completed,0) completed
           FROM challenges c LEFT JOIN user_challenges uc ON c.id=uc.challenge_id AND uc.user_id=?
           WHERE c.active=1""", (user_id,)).fetchall():
        if c['completed']:
            continue
        items.append({'kind': 'challenge', 'name': c['title'], 'icon': c['icon'],
                      'remaining': max(0, int(c['target_value'] - c['progress']))})
    conn.close()
    if not items:
        return {'hasGoal': False, 'allEarned': True, 'text': None, 'icon': None}
    items.sort(key=lambda i: i['remaining'])
    top = items[0]
    if top['kind'] == 'badge':
        unit_s = top['unit'] + ('s' if top['remaining'] != 1 else '')
        text = f"You're {top['remaining']} {unit_s} away from the {top['name']} badge"
    else:
        text = f'Complete "{top["name"]}" — {top["remaining"]} to go'
    return {'hasGoal': True, 'allEarned': False, 'text': text, 'icon': top['icon'],
            'remaining': top['remaining'], 'kind': top['kind'], 'name': top['name']}


def get_leaderboard(limit=20, period='all'):
    """Top users ranked by eco_score ('all') or by recent activity
    ('weekly'/'monthly' = user_events in the last 7/30 days). Each row also
    carries the badge count + earned badge icons for the leaderboard page."""
    conn = get_db()
    if period == 'weekly':
        order = "ORDER BY (SELECT COUNT(*) FROM user_events ue WHERE ue.user_id = users.id AND ue.created_at >= datetime('now','-7 days')) DESC"
    elif period == 'monthly':
        order = "ORDER BY (SELECT COUNT(*) FROM user_events ue WHERE ue.user_id = users.id AND ue.created_at >= datetime('now','-30 days')) DESC"
    else:
        order = "ORDER BY eco_score DESC"
    rows = conn.execute(f"""SELECT id, username, full_name, eco_score, streak_days, total_waste_kg, avatar_color, avatar_url,
        (SELECT COUNT(*) FROM user_badges ub WHERE ub.user_id = users.id) AS badges
        FROM users {order} LIMIT ?""", (limit,)).fetchall()
    badge_rows = conn.execute(
        "SELECT ub.user_id, b.icon FROM user_badges ub JOIN badges b ON ub.badge_id = b.id "
        "ORDER BY ub.earned_at DESC").fetchall()
    conn.close()
    icons_by_user = {}
    for br in badge_rows:
        icons_by_user.setdefault(br['user_id'], []).append(br['icon'])
    result = []
    for r in rows:
        row = dict(r)
        row['badgeIcons'] = icons_by_user.get(row['id'], [])
        result.append(row)
    return result


def award_eco_points(user_id, points):
    conn = get_db()
    conn.execute("UPDATE users SET eco_score = eco_score + ? WHERE id = ?", (points, user_id))
    conn.commit()
    conn.close()


def record_user_event(user_id, event_type):
    conn = get_db()
    conn.execute("INSERT INTO user_events (user_id, event_type) VALUES (?, ?)", (user_id, event_type))
    conn.commit()
    conn.close()


# ============ Settings ============

# Per-user default settings. Keys mirror the settings.html form ids and the
# key/value `settings` table stores them as strings ('true'/'false' for
# booleans, numbers as strings). Theme + the advanced toggles used to live only
# in the browser; they are now persisted server-side per user so they follow
# the account across devices.
DEFAULT_SETTINGS = {
    'language': 'en',
    'timezone': 'IST',
    'dateFormat': 'DD/MM/YYYY',
    'pushNotifications': 'true',
    'emailNotifications': 'true',
    'soundAlerts': 'true',
    'notificationFrequency': 'instant',
    'notificationEmail': '',
    'theme': 'dark',
    'autoTheme': 'false',
    'animations': 'true',
    'wetThreshold': '80',
    'dryThreshold': '80',
    'criticalThreshold': '90',
    'alertCooldown': '30',
    'syncInterval': '5',
    'debugMode': 'false',
    'offlineMode': 'false',
    'apiEndpoint': '',
    'pickupWeekday': '',
    'pickupTime': '09:00',
}


def save_settings(user_id, settings_dict):
    conn = get_db()
    for key, value in settings_dict.items():
        conn.execute("INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)",
            (user_id, key, str(value)))
    conn.commit()
    conn.close()


def get_settings(user_id):
    """Per-user settings with the shared defaults filled in, so a user who has
    never saved a value still receives a complete, well-formed payload."""
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()
    settings = dict(DEFAULT_SETTINGS)
    settings.update({r['key']: r['value'] for r in rows})
    return settings


# Weekday index (0=Monday) -> display name, and the per-user time zone shorthand
# used by settings.html -> tz name used by get_schedule_summary().
_WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
_TZ_ZONE_MAP = {'IST': 'Asia/Kolkata', 'EST': 'America/New_York',
                'PST': 'America/Los_Angeles', 'GMT': 'Europe/London'}


def get_schedule_summary(user_id):
    """Collection schedule for the dashboard card: next pickup weekday, time and
    days-away, resolved in the user's saved time zone. Returns {'set': False}
    until the user chooses a pickup weekday on Settings."""
    if not user_id:
        return {'set': False}
    s = get_settings(user_id)
    try:
        weekday = int((s.get('pickupWeekday') or '').strip())
    except (TypeError, ValueError):
        return {'set': False}
    if not (0 <= weekday <= 6):
        return {'set': False}
    try:
        hh, mm = 9, 0
        t = (s.get('pickupTime') or '09:00').strip().split(':')
        hh = int(t[0]) % 24
        mm = int(t[1]) if len(t) > 1 else 0
    except (ValueError, IndexError):
        hh, mm = 9, 0
    tz = None
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(_TZ_ZONE_MAP.get((s.get('timezone') or '').strip(), 'UTC'))
    except Exception:
        tz = None
    now = datetime.now(tz) if tz else datetime.now()
    days_ahead = (weekday - now.weekday()) % 7
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(days=days_ahead)
    if nxt <= now:
        nxt += timedelta(days=7)
    return {
        'set': True,
        'weekday': _WEEKDAY_NAMES[weekday],
        'time': f'{hh:02d}:{mm:02d}',
        'daysAway': (nxt.date() - now.date()).days,
        'nextDate': nxt.strftime('%Y-%m-%d'),
        'timezone': (s.get('timezone') or '').strip() or 'UTC',
    }


# ============ Admin ============

def get_admin_stats():
    conn = get_db()
    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    total_readings = conn.execute("SELECT COUNT(*) as c FROM readings").fetchone()['c']
    device_readings = conn.execute(
        "SELECT COUNT(*) as c FROM readings WHERE (source='device' OR source IS NULL)").fetchone()['c']
    test_readings = conn.execute("SELECT COUNT(*) as c FROM readings WHERE source='test'").fetchone()['c']
    total_activity = conn.execute("SELECT COUNT(*) as c FROM activity").fetchone()['c']
    total_anomalies = conn.execute("SELECT COUNT(*) as c FROM anomalies").fetchone()['c']
    uptime_first = conn.execute("SELECT MIN(timestamp) as t FROM readings").fetchone()['t']
    conn.close()
    return {
        'dbSizeBytes': db_size, 'dbSizeMB': round(db_size / 1048576, 2),
        'totalUsers': total_users, 'totalReadings': total_readings,
        'deviceReadings': device_readings, 'testReadings': test_readings,
        'totalActivity': total_activity, 'totalAnomalies': total_anomalies,
        'firstReading': uptime_first
    }


def backup_database():
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = os.path.join(backup_dir, f'waste_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    shutil.copy2(DB_PATH, backup_file)
    return backup_file


def get_backups():
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    if not os.path.exists(backup_dir):
        return []
    files = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        if f.endswith('.db'):
            fp = os.path.join(backup_dir, f)
            files.append({'name': f, 'size': os.path.getsize(fp), 'path': fp})
    return files


# ============ Test-data hygiene ============


def label_all_as_test():
    """One-time provenance fix for development DBs: everything currently in
    the tables predates the source column and is verification/simulated data,
    so favourite-label it 'test' rather than silently deleting it. Always call
    backup_database() first."""
    conn = get_db()
    counts = {}
    for table in ('readings', 'collections', 'anomalies'):
        cur = conn.execute(
            f"UPDATE {table} SET source='test' WHERE source='device' OR source IS NULL")
        counts[table] = cur.rowcount
    conn.commit()
    conn.close()
    return counts


def clear_test_data():
    """Admin-only removal of simulated/test data. A full DB backup is written
    first so the operation is always reversible; returns the backup path and
    per-table deletion counts."""
    backup = backup_database()
    conn = get_db()
    counts = {}

    # Reverse the +10 eco points awarded for each test collection so users do
    # not keep score earned purely from simulated data.
    eco_reversed = {}
    for row in conn.execute(
            "SELECT user_id, COUNT(*) c FROM collections WHERE source='test' "
            "AND user_id IS NOT NULL GROUP BY user_id").fetchall():
        eco_reversed[row['user_id']] = row['c'] * 10
    for uid, pts in eco_reversed.items():
        conn.execute(
            "UPDATE users SET eco_score = MAX(eco_score - ?, 0) WHERE id = ?", (pts, uid))

    for table in ('readings', 'collections', 'anomalies'):
        r = conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE source='test'").fetchone()
        counts[table] = r['c']
        conn.execute(f"DELETE FROM {table} WHERE source='test'")
    r = conn.execute("SELECT COUNT(*) c FROM activity WHERE message LIKE '[TEST]%'").fetchone()
    counts['activity'] = r['c']
    conn.execute("DELETE FROM activity WHERE message LIKE '[TEST]%'")
    # If no real device reading remains for a bin, revert its state to empty so
    # the UI never shows level/anomaly residue left behind by test posts, and
    # drop its stale prediction row (an "N/A" prediction is better than a fake
    # 0%/0h one).
    remaining_device_readings = 0
    for bt in ('wetBin', 'dryBin'):
        c = conn.execute(
            "SELECT COUNT(*) c FROM readings WHERE bin_type=? AND (source='device' OR source IS NULL)",
            (bt,)).fetchone()['c']
        remaining_device_readings += c
        if c == 0:
            conn.execute(
                "UPDATE bins SET level=0,distance=0,status='empty',fill_rate=0,time_to_full_min=0,updated_at=? "
                "WHERE id=?", (datetime.now(), bt))
            conn.execute("DELETE FROM predictions WHERE bin_type = ?", (bt,))
    # A fresh install has no heartbeat yet — forget the old device last_seen so
    # the health card reads "never/offline" instead of a stale QA timestamp.
    if remaining_device_readings == 0:
        conn.execute("DELETE FROM device_state WHERE key = 'last_seen'")
        conn.execute("INSERT OR IGNORE INTO device_state (key, value) VALUES ('last_seen', '')")
    # Rebuild each user's total_waste_kg from the remaining (real) collections.
    # Waste credit only ever accrues through collection events, and the
    # collections table stores no per-collection weight, so this uses the
    # ~0.05 kg per %-level convention that update_bin/collect_bin apply when the
    # device sends no weight. Users whose collections were all test reset to 0.
    for row in conn.execute("SELECT id FROM users").fetchall():
        uid = row['id']
        kg = conn.execute(
            "SELECT ROUND(SUM(CASE WHEN level_before IS NOT NULL "
            "THEN level_before * 0.05 ELSE 0.0 END), 2) kg "
            "FROM collections WHERE user_id = ? AND (source='device' OR source IS NULL)",
            (uid,)).fetchone()['kg']
        conn.execute("UPDATE users SET total_waste_kg = ? WHERE id = ?", (kg or 0.0, uid))
    conn.commit()
    conn.close()
    counts['ecoScoreReversed'] = eco_reversed
    return {'backup': backup, 'deleted': counts}


# ============ Support / Chat ============

_FAQS = None


def _load_faqs():
    """Lazily load the FAQ dataset from backend/support_faq.json.

    Each entry: {'id', 'question', 'answer', 'keywords': [...]}. Used by the
    rule-based engine before any AI fallback is considered."""
    global _FAQS
    if _FAQS is None:
        faq_path = os.path.join(os.path.dirname(__file__), 'support_faq.json')
        try:
            with open(faq_path, encoding='utf-8') as f:
                _FAQS = json.load(f)
        except Exception:
            _FAQS = []
    return _FAQS


def lookup_faq(message):
    """Keyword-match a user message against the FAQ dataset.

    Returns {'question', 'answer'} for the best match, or None. Whole-word
    tokens win; a score of 1+ selects a FAQ, ties broken by keyword count then
    list order. Only empty/whitespace inputs skip matching so one- or two-token
    greetings like "hi"/"yo" hit the greeting entry instead of the AI."""
    text = message or ''
    if not text.strip():
        return None
    tokens = re.findall(r'[a-z0-9]+', text.lower())
    token_set = set(tokens)
    best, best_score, best_hits = None, 0, 0
    for faq in _load_faqs():
        hits = 0
        for kw in (k.lower() for k in faq.get('keywords', [])):
            kw_tokens = kw.split()
            if any(kw == t or (len(kw_tokens) > 1 and kw_tokens[-1] == t) for t in tokens):
                hits += 1
        if hits > best_score or (hits == best_score and hits > 0 and hits > best_hits):
            best, best_score, best_hits = faq, hits, hits
    if best and best_score >= 1:
        return {'question': best['question'], 'answer': best['answer']}
    return None


def save_chat_message(user_id, role, content, source='faq'):
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_messages (user_id, role, source, content) VALUES (?, ?, ?, ?)",
        (user_id, role, source, content))
    conn.commit()
    conn.close()


def get_chat_messages(user_id, limit=50):
    """Most recent chat exchange for a user, oldest first (for client restore)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT role, source, content, created_at FROM chat_messages "
        "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))


# Initialize DB on import
init_db()

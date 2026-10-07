"""
Per-bin anomaly detection with sklearn.ensemble.IsolationForest.

Replaces the fixed "level change > 30" threshold. The forest is trained on
(level, fill_rate, hour_of_day) tuples drawn from the bin's own readings
history. A sudden spike shows up as an extreme point (unusually high level
*and* high instantaneous fill rate) that the forest isolates; routine daily
variation stays in the dense region and is not flagged.

Data-volume requirements (see model_registry)
---------------------------------------------
- Trained only when a bin has >= MIN_ANOMALY_SAMPLES (100) readings. Isolation-
  Forest below that sample count cannot estimate the normal region reliably, so
  models.update_bin keeps the legacy >30 rule until then.
- At ~100+ readings the forest is already able to bound the typical
  (level, rate, hour) box; ~500+ readings (2-3 weeks hourly) make it clearly
  more robust than the fixed threshold.
"""
import os
from datetime import datetime

import numpy as np

from ml import model_registry


def _ts(raw):
    raw = str(raw or '') or ''
    if not raw:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    return None


def build_features(readings_desc):
    """(level, instantaneous fill_rate, hour_of_day) per ascending reading."""
    readings = list(reversed(readings_desc))
    rows, prev, prev_t = [], None, None
    for r in readings:
        level = float(r['level'])
        t = _ts(r.get('timestamp'))
        if prev is None:
            rate = 0.0
        else:
            dt_h = max((t - prev_t).total_seconds() / 3600.0, 0.001) if (t and prev_t) else 1.0
            rate = (level - prev) / dt_h
        rows.append([level, round(rate, 4), float(t.hour if t else 0)])
        prev, prev_t = level, t
    return rows


def train(bin_type, readings_desc):
    """
    Train and persist the IsolationForest detector for one bin. Returns a
    summary dict, or None when there is not enough data / sklearn is missing.
    """
    if len(readings_desc) < model_registry.MIN_ANOMALY_SAMPLES:
        return None
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return None

    rows = build_features(readings_desc)
    if len(rows) < model_registry.MIN_ANOMALY_SAMPLES:
        return None

    # contamination=0.05: flag roughly the top 5% isolation tail. Below ~0.03
    # the forest is saturated by collection resets (big negative rates) and
    # misses genuine upward spikes; 0.05 keeps catches both directions.
    forest = IsolationForest(contamination=0.05, n_estimators=200, random_state=42)
    forest.fit(np.asarray(rows, dtype=float))

    model_registry.ensure_models_dir()
    import joblib
    payload = {
        'version': model_registry.ARTIFACT_VERSION,
        'kind': 'anomaly',
        'bin_type': bin_type,
        'features': list(model_registry.ANOMALY_FEATURES),
        'model': forest,
        'n_samples': len(rows),
        'trained_at': datetime.now().isoformat(timespec='seconds'),
    }
    path = model_registry.anomaly_model_path(bin_type)
    joblib.dump(payload, path)
    return {
        'model': 'anomaly_detector',
        'bin_type': bin_type,
        'path': path,
        'n_samples': len(rows),
        'readings': len(readings_desc),
        'reliable': len(rows) >= model_registry.RELIABLE_SAMPLES,
        'trained_at': payload['trained_at'],
    }


def is_anomalous(bin_type, level, fill_rate, hour_of_day):
    """
    Anomaly flag for a live observation, or None when no model exists for this
    bin (caller falls back to the legacy >30 threshold).
    """
    payload = _load(model_registry.anomaly_model_path(bin_type))
    if not payload or payload.get('features') != model_registry.ANOMALY_FEATURES:
        return None
    try:
        X = [[float(level), float(fill_rate), float(hour_of_day)]]
        return int(payload['model'].predict(X)[0]) == -1
    except Exception:
        return None


def status(bin_type):
    payload = _load(model_registry.anomaly_model_path(bin_type))
    if not payload:
        return None
    return {
        'kind': payload.get('kind'),
        'bin_type': bin_type,
        'features': payload.get('features'),
        'n_samples': payload.get('n_samples'),
        'trained_at': payload.get('trained_at'),
        'path': model_registry.anomaly_model_path(bin_type),
    }


def _load(path):
    _CACHE = getattr(_load, '_cache', None)
    if _CACHE is None:
        _CACHE = _load._cache = {}
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    entry = _CACHE.get(path)
    if entry is not None and entry[0] == mtime:
        return entry[1]
    try:
        import joblib
        payload = joblib.load(path)
    except Exception:
        _CACHE.pop(path, None)
        return None
    _CACHE[path] = (mtime, payload)
    return payload
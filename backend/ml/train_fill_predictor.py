"""
Train per-bin time-to-full regression models from the project's own readings
history, using the existing models.get_readings() accessor. Pure scikit-learn
LinearRegression on a small hand-built feature set (level, time-of-day, day of
week, recent fill rate) - no external APIs, no statsmodels dependency.

Target construction
-------------------
Readings are split into fill-cycles: a cycle is a run of readings that only
rises, ending when the level collapses by >30% (a collection / reset). Only
cycles that peaked at >=90% are used to label data, because "minutes until
full" is only observable when a bin actually filled up. For every intermediate
point of such a cycle the target is the observed minutes from that point to the
cycle's first peak measurement. The regression then learns what (level, time of
day, recent slope) implies for remaining time-to-full, which makes it robust to
noisy two-point deltas that the legacy `(100-level)/fit` formula overreacts to.

Data-volume requirements (see model_registry)
---------------------------------------------
- Built only if the bin has >= MIN_TRAIN_READINGS readings and >=
  MIN_LABELLED_SAMPLES supervised samples; otherwise no artifact is written and
  models.update_bin keeps using the classic linear projection.
- It becomes genuinely more reliable than the simple formula somewhere around
  RELIABLE_SAMPLES readings (roughly 1-2 weeks of hourly snapshots), where the
  regression has seen enough full fill-cycles / empties to model the pattern.
"""
import os
from datetime import datetime

import numpy as np

from ml import model_registry


def _ts(reading):
    raw = str(reading.get('timestamp', '')) or ''
    if not raw:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    return None


def _fill_cycles(readings):
    """Split ascending readings into fill-cycles on big level collapses."""
    cycles = []
    current = []
    for i, r in enumerate(readings):
        if i > 0 and readings[i - 1]['level'] - r['level'] > 30:
            if current:
                cycles.append(current)
            current = []
        current.append(r)
    if current:
        cycles.append(current)
    return cycles


def _rolling_rate(cycle, idx):
    """Slope (%/hour) of the last <=5 points of the cycle up to index idx."""
    window = cycle[max(0, idx - 4):idx + 1]
    if len(window) < 2:
        return 0.0
    base = _ts(window[0])
    if base is None:
        return 0.0
    xs, ys = [], []
    for w in window:
        t = _ts(w)
        if t is None:
            continue
        xs.append((t - base).total_seconds() / 3600.0)
        ys.append(float(w['level']))
    if len(xs) < 2 or (max(xs) - min(xs)) < 1e-6:
        return 0.0
    try:
        return float(np.polyfit(xs, ys, 1)[0])
    except Exception:
        return 0.0


def _features(cycle, idx):
    r = cycle[idx]
    t = _ts(r)
    return [
        float(r['level']),
        float(t.hour if t else 0),
        float(t.weekday() if t else 0),
        round(_rolling_rate(cycle, idx), 4),
    ]


def train(bin_type, readings_desc):
    """
    Train and persist the time-to-full model for one bin.

    readings_desc: rows exactly as returned by models.get_readings() (DESC
    order, dicts with at least 'level' and 'timestamp'). Returns a summary dict
    or None when there is not enough data / sklearn is unavailable.
    """
    if len(readings_desc) < model_registry.MIN_TRAIN_READINGS:
        return None
    try:
        from sklearn.linear_model import LinearRegression
    except ImportError:
        return None

    readings = list(reversed(readings_desc))
    X, y = [], []
    used_cycles = 0
    for cycle in _fill_cycles(readings):
        if len(cycle) < 2:
            continue
        peak = max(r['level'] for r in cycle)
        if peak < 90:
            continue
        t_peak = None
        for r in cycle:
            if r['level'] == peak:
                t_peak = _ts(r)
                if t_peak is not None:
                    break
        if t_peak is None:
            continue
        used_cycles += 1
        for idx in range(1, len(cycle)):
            if cycle[idx]['level'] >= peak:
                continue
            t_i = _ts(cycle[idx])
            if t_i is None:
                continue
            X.append(_features(cycle, idx))
            y.append(max((t_peak - t_i).total_seconds() / 60.0, 1.0))

    if len(X) < model_registry.MIN_LABELLED_SAMPLES:
        return None

    model = LinearRegression()
    model.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=float))

    model_registry.ensure_models_dir()
    import joblib
    payload = {
        'version': model_registry.ARTIFACT_VERSION,
        'kind': 'fill',
        'bin_type': bin_type,
        'features': list(model_registry.FILL_FEATURES),
        'model': model,
        'n_samples': len(X),
        'n_cycles': used_cycles,
        'trained_at': datetime.now().isoformat(timespec='seconds'),
    }
    path = model_registry.fill_model_path(bin_type)
    joblib.dump(payload, path)
    return {
        'model': 'fill_predictor',
        'bin_type': bin_type,
        'path': path,
        'n_samples': len(X),
        'n_cycles': used_cycles,
        'readings': len(readings),
        'reliable': len(X) >= model_registry.RELIABLE_SAMPLES,
        'trained_at': payload['trained_at'],
    }
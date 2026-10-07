"""
Runtime scoring for the per-bin time-to-full regression models.

models.update_bin calls predict_ttf_min(); anything that can go wrong (no
artifact, sklearn missing, corrupt file, malformed features) returns None and
the caller silently falls back to the classic linear projection.
"""
import os

from ml import model_registry

# key -> (file mtime, payload). Avoids re-loading joblib on every sensor push.
_CACHE = {}


def _load(path):
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


def predict_ttf_min(bin_type, level, hour_of_day, day_of_week, recent_fill_rate):
    """
    Predicted minutes until the bin is full, or None when no usable model
    exists (caller then falls back to the legacy linear formula).
    """
    payload = _load(model_registry.fill_model_path(bin_type))
    if not payload or payload.get('features') != model_registry.FILL_FEATURES:
        return None
    try:
        X = [[float(level), float(hour_of_day), float(day_of_week), float(recent_fill_rate)]]
        ttf = float(payload['model'].predict(X)[0])
    except Exception:
        return None
    # Clip to a sane band: 2 minutes .. 7 days.
    return int(min(max(ttf, 2.0), 7 * 24 * 60))


def status(bin_type):
    """Metadata of the saved artifact for this bin, or None when not trained."""
    payload = _load(model_registry.fill_model_path(bin_type))
    if not payload:
        return None
    return {
        'kind': payload.get('kind'),
        'bin_type': bin_type,
        'features': payload.get('features'),
        'n_samples': payload.get('n_samples'),
        'n_cycles': payload.get('n_cycles'),
        'trained_at': payload.get('trained_at'),
        'path': model_registry.fill_model_path(bin_type),
    }
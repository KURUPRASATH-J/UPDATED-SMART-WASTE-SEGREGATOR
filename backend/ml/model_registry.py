"""
Minimum-fit checks + shared artifact helpers for the ML models.

Thresholds documented here control when a model is *saved* (and therefore used
at request time) vs. when models.update_bin falls back to the classic linear
formulas. See the docstrings in train_fill_predictor / anomaly_detector for the
data-volume reasoning.
"""
import os

# Directory where joblib artifacts are stored.
MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')

# ---------------------------------------------------------------------------
# Data-volume thresholds (project-wide single source of truth)
# ---------------------------------------------------------------------------
# Time-to-full regression: parity with the task's suggested floor ("under 20
# readings -> fall back"). 4 features -> a LinearRegression is identifiable with
# ~10+ labelled samples, so 20 works as a hard floor, but this yields only a
# rough estimate. With ~300+ readings (1-2 weeks of hourly level snapshots) the
# regression reliably beats the instantaneous two-point delta.
MIN_TRAIN_READINGS = 20     # raw readings available for a bin
MIN_LABELLED_SAMPLES = 20   # supervised samples with a real time-to-full target

# Anomaly detection: IsolationForest needs enough points to estimate the data's
# distribution. Below ~100 samples per bin its contamination estimates are
# unstable and the fixed >30 threshold is the safer choice.
MIN_ANOMALY_SAMPLES = 100

# Advisory log level once a model can really be trusted (1-2 weeks of data).
RELIABLE_SAMPLES = 300

# Fill features order used by both training and inference - KEEP IN SYNC.
FILL_FEATURES = ['level', 'hour_of_day', 'day_of_week', 'recent_fill_rate']

# Anomaly features order - KEEP IN SYNC.
ANOMALY_FEATURES = ['level', 'fill_rate', 'hour_of_day']

ARTIFACT_VERSION = 1


def fill_model_path(bin_type):
    return os.path.join(MODELS_DIR, f'fill_{bin_type}_v{ARTIFACT_VERSION}.joblib')


def anomaly_model_path(bin_type):
    return os.path.join(MODELS_DIR, f'anomaly_{bin_type}_v{ARTIFACT_VERSION}.joblib')


def ensure_models_dir():
    os.makedirs(MODELS_DIR, exist_ok=True)
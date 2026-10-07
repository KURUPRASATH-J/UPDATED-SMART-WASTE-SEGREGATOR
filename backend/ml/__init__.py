"""
Machine-learning helpers for Smart Waste Segregator.

Trained entirely on the project's own `readings` history (no external APIs or
services). Artifacts are persisted with joblib under `backend/ml/models/`.

Modules:
  train_fill_predictor  - trains the per-bin time-to-full regression models
  fill_predictor        - runtime scoring used by models.update_bin
  anomaly_detector      - trains + scores per-bin IsolationForest detectors
  retrain_models        - one-shot retrain of every model (CLI / admin endpoint)
"""
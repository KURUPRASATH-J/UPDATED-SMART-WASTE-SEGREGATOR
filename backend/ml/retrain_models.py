"""
Retrain every ML model from the accumulated `readings` history.

Retrain only occasionally (nightly / weekly), never on every request: training
scans the whole readings table, so calling it per sensor push would be wasted
work. Wire it to any scheduler, e.g. on Linux:

    # crontab -e
    0 2 * * * cd /path/to/smart-waste-segregator/backend && python ml/retrain_models.py

On Windows, point Task Scheduler at the same command. The admin UI can also
trigger it live via POST /api/admin/ml/retrain.

Behaviour: for each bin it pulls historical readings through the existing
models.get_readings() accessor and trains both the fill predictor and the
anomaly detector. Bins without enough data are skipped (no artifact written),
so update_bin keeps the classic formulas until data accumulates.
"""
from datetime import datetime

from ml import anomaly_detector, train_fill_predictor
from ml import model_registry

BIN_TYPES = ('wetBin', 'dryBin')
TRAIN_WINDOW_HOURS = 24 * 180   # ~6 months of history
TRAIN_LIMIT = 200000


def retrain_all(history_hours=TRAIN_WINDOW_HOURS, limit=TRAIN_LIMIT):
    import models  # imported lazily so this module stays import-safe at boot

    results = {}
    for bin_type in BIN_TYPES:
        readings = models.get_readings(bin_type, hours=history_hours, limit=limit)
        entry = {'readings': len(readings)}
        try:
            entry['fill'] = train_fill_predictor.train(bin_type, readings)
        except Exception as exc:
            entry['fill'] = {'error': str(exc)}
        try:
            entry['anomaly'] = anomaly_detector.train(bin_type, readings)
        except Exception as exc:
            entry['anomaly'] = {'error': str(exc)}
        results[bin_type] = entry
    results['_meta'] = {
        'refit_window_hours': history_hours,
        'min_fill_samples': model_registry.MIN_LABELLED_SAMPLES,
        'min_anomaly_samples': model_registry.MIN_ANOMALY_SAMPLES,
        'reliable_samples': model_registry.RELIABLE_SAMPLES,
        'run_at': datetime.now().isoformat(timespec='seconds'),
    }
    return results


if __name__ == '__main__':
    import json
    report = retrain_all()
    print(json.dumps(report, indent=2, default=str))
"""
Calibration methods for probabilistic forecasts.

Provides tools to improve reliability of probability predictions,
ensuring predicted probabilities match observed frequencies.

Also includes conformal prediction for distribution-free prediction intervals
and comprehensive calibration metrics.
"""

from models_src.calibration.isotonic import IsotonicCalibrator
from models_src.calibration.conformal import ConformalPredictor
from models_src.calibration.metrics import (
    expected_calibration_error,
    compute_reliability_curve,
    compute_sharpness,
    compute_calibration_metrics,
    evaluate_prediction_intervals,
)

__all__ = [
    "IsotonicCalibrator",
    "ConformalPredictor",
    "expected_calibration_error",
    "compute_reliability_curve",
    "compute_sharpness",
    "compute_calibration_metrics",
    "evaluate_prediction_intervals",
]

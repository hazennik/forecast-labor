"""
Calibration-specific metrics for probabilistic forecasts.

Provides specialized metrics for evaluating probability calibration quality,
including reliability diagrams, sharpness, and calibration error metrics.

Key Metrics:
- Expected Calibration Error (ECE): Probability calibration quality
- Reliability Diagram Data: Predicted vs. observed frequency
- Sharpness: Concentration of predictive distributions
- Calibration Curves: Binned calibration assessment

References:
- Gneiting et al. (2007): Probabilistic Forecasts, Calibration and Sharpness
- Niculescu-Mizil & Caruana (2005): Predicting good probabilities with supervised learning
- Kuleshov et al. (2018): Accurate Uncertainties for Deep Learning Using Calibrated Regression
"""

from typing import Dict, Any, Tuple
import numpy as np
from loguru import logger

# Import ECE from main metrics module for convenience
from models_src.utils.metrics import expected_calibration_error


__all__ = [
    "expected_calibration_error",  # Re-export from main metrics
    "compute_reliability_curve",
    "compute_sharpness",
    "compute_calibration_metrics",
    "evaluate_prediction_intervals",
]


def compute_reliability_curve(
    y_true: np.ndarray, y_pred_probs: np.ndarray, n_bins: int = 10
) -> Dict[str, np.ndarray]:
    """
    Compute reliability curve data (predicted vs. observed frequencies).

    Reliability curves visualize calibration by binning predictions and
    comparing predicted probabilities to observed frequencies.
    Perfect calibration → points on diagonal.

    Args:
        y_true: True binary outcomes (0 or 1), N samples
        y_pred_probs: Predicted probabilities (0-1), N samples
        n_bins: Number of bins for grouping predictions

    Returns:
        curve_data: Dictionary with:
            - 'bin_centers': Center of each bin
            - 'predicted_probs': Average predicted probability per bin
            - 'observed_freqs': Average observed frequency per bin
            - 'counts': Number of samples per bin
            - 'confidence_lower': Lower confidence bound (Wilson score)
            - 'confidence_upper': Upper confidence bound (Wilson score)

    Example:
        >>> y_true = np.array([1, 0, 1, 1, 0, 1, 0, 0])
        >>> y_pred = np.array([0.9, 0.2, 0.8, 0.7, 0.3, 0.85, 0.15, 0.25])
        >>> curve = compute_reliability_curve(y_true, y_pred, n_bins=5)
        >>> # Plot: plt.plot(curve['predicted_probs'], curve['observed_freqs'])
    """
    # Validate inputs
    y_true = np.asarray(y_true)
    y_pred_probs = np.asarray(y_pred_probs)

    if len(y_true) != len(y_pred_probs):
        raise ValueError("y_true and y_pred_probs must have same length")

    if not np.all(np.isin(y_true, [0, 1])):
        raise ValueError("y_true must contain only 0s and 1s (binary outcomes)")

    if np.any((y_pred_probs < 0) | (y_pred_probs > 1)):
        raise ValueError("y_pred_probs must be in range [0, 1]")

    # Create bins
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_pred_probs, bin_boundaries[:-1]) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    # Compute statistics per bin
    bin_centers = []
    predicted_probs = []
    observed_freqs = []
    counts = []
    confidence_lower = []
    confidence_upper = []

    for bin_idx in range(n_bins):
        in_bin = bin_indices == bin_idx

        if not np.any(in_bin):
            # Empty bin - skip
            continue

        bin_lower = bin_boundaries[bin_idx]
        bin_upper = bin_boundaries[bin_idx + 1]
        bin_center = (bin_lower + bin_upper) / 2

        # Average predicted probability in bin
        avg_pred = np.mean(y_pred_probs[in_bin])

        # Observed frequency in bin
        obs_freq = np.mean(y_true[in_bin])

        # Sample count
        n_samples = np.sum(in_bin)

        # Wilson score confidence interval (more accurate than normal approximation)
        # 95% confidence interval
        z = 1.96  # 95% confidence
        if n_samples > 0:
            p = obs_freq
            denominator = 1 + z**2 / n_samples
            center = (p + z**2 / (2 * n_samples)) / denominator
            margin = (
                z * np.sqrt(p * (1 - p) / n_samples + z**2 / (4 * n_samples**2)) / denominator
            )

            lower_bound = max(0.0, center - margin)
            upper_bound = min(1.0, center + margin)
        else:
            lower_bound = 0.0
            upper_bound = 1.0

        bin_centers.append(bin_center)
        predicted_probs.append(avg_pred)
        observed_freqs.append(obs_freq)
        counts.append(int(n_samples))
        confidence_lower.append(lower_bound)
        confidence_upper.append(upper_bound)

    logger.debug(
        "reliability_curve_computed",
        extra={
            "n_bins": n_bins,
            "n_bins_with_data": len(bin_centers),
            "total_samples": len(y_true),
        },
    )

    return {
        "bin_centers": np.array(bin_centers),
        "predicted_probs": np.array(predicted_probs),
        "observed_freqs": np.array(observed_freqs),
        "counts": np.array(counts),
        "confidence_lower": np.array(confidence_lower),
        "confidence_upper": np.array(confidence_upper),
    }


def compute_sharpness(
    prediction_intervals: Tuple[np.ndarray, np.ndarray], confidence_level: float = 0.9
) -> Dict[str, float]:
    """
    Compute sharpness metrics for prediction intervals.

    Sharpness measures the concentration of predictive distributions.
    Narrower intervals (while maintaining coverage) = sharper predictions.

    Note: Sharpness should ONLY be compared among calibrated predictors.
    An uncalibrated predictor can achieve high sharpness with poor coverage.

    Args:
        prediction_intervals: Tuple of (lower_bounds, upper_bounds)
        confidence_level: Confidence level of intervals (for context)

    Returns:
        sharpness_metrics: Dictionary with:
            - 'mean_interval_width': Average interval width
            - 'median_interval_width': Median interval width
            - 'std_interval_width': Standard deviation of widths
            - 'min_interval_width': Minimum width
            - 'max_interval_width': Maximum width
            - 'cv_interval_width': Coefficient of variation (std/mean)

    Example:
        >>> lower = np.array([40, 45, 50])
        >>> upper = np.array([60, 65, 70])
        >>> metrics = compute_sharpness((lower, upper), confidence_level=0.9)
        >>> print(f"Mean width: {metrics['mean_interval_width']:.1f}")
    """
    lower_bounds, upper_bounds = prediction_intervals

    # Validate inputs
    lower_bounds = np.asarray(lower_bounds)
    upper_bounds = np.asarray(upper_bounds)

    if len(lower_bounds) != len(upper_bounds):
        raise ValueError("Lower and upper bounds must have same length")

    if len(lower_bounds) == 0:
        raise ValueError("prediction_intervals cannot be empty")

    if not np.all(lower_bounds <= upper_bounds):
        raise ValueError("Lower bounds must be <= upper bounds")

    # Compute interval widths
    widths = upper_bounds - lower_bounds

    # Compute sharpness metrics
    metrics = {
        "mean_interval_width": float(np.mean(widths)),
        "median_interval_width": float(np.median(widths)),
        "std_interval_width": float(np.std(widths)),
        "min_interval_width": float(np.min(widths)),
        "max_interval_width": float(np.max(widths)),
        "cv_interval_width": float(np.std(widths) / (np.mean(widths) + 1e-10)),
    }

    logger.debug(
        "sharpness_computed",
        extra={
            "confidence_level": confidence_level,
            "mean_width": metrics["mean_interval_width"],
            "n_intervals": len(widths),
        },
    )

    return metrics


def compute_calibration_metrics(
    y_true: np.ndarray, y_pred_probs: np.ndarray, n_bins: int = 10
) -> Dict[str, Any]:
    """
    Compute comprehensive calibration metrics.

    Combines multiple calibration quality measures into a single report.

    Args:
        y_true: True binary outcomes (0 or 1)
        y_pred_probs: Predicted probabilities (0-1)
        n_bins: Number of bins for reliability curve

    Returns:
        metrics: Dictionary with:
            - 'ece': Expected Calibration Error
            - 'max_calibration_error': Maximum bin-wise calibration error
            - 'mean_confidence': Average predicted probability
            - 'brier_score': Brier score (MSE for probabilities)
            - 'log_loss': Logarithmic loss (negative log-likelihood)
            - 'reliability_curve': Reliability curve data

    Example:
        >>> metrics = compute_calibration_metrics(y_true, y_pred_probs)
        >>> print(f"ECE: {metrics['ece']:.4f}")
        >>> print(f"Brier: {metrics['brier_score']:.4f}")
    """
    # Validate inputs
    y_true = np.asarray(y_true)
    y_pred_probs = np.asarray(y_pred_probs)

    if len(y_true) != len(y_pred_probs):
        raise ValueError("y_true and y_pred_probs must have same length")

    if not np.all(np.isin(y_true, [0, 1])):
        raise ValueError("y_true must contain only 0s and 1s")

    if np.any((y_pred_probs < 0) | (y_pred_probs > 1)):
        raise ValueError("y_pred_probs must be in range [0, 1]")

    # Compute ECE
    ece = expected_calibration_error(y_true, y_pred_probs, n_bins=n_bins)

    # Compute reliability curve for max calibration error
    reliability = compute_reliability_curve(y_true, y_pred_probs, n_bins=n_bins)

    # Max calibration error (MCE)
    calibration_errors = np.abs(reliability["predicted_probs"] - reliability["observed_freqs"])
    mce = float(np.max(calibration_errors)) if len(calibration_errors) > 0 else 0.0

    # Brier score (MSE for probabilities)
    brier_score = float(np.mean((y_pred_probs - y_true) ** 2))

    # Log loss (cross-entropy)
    # Clip predictions to avoid log(0)
    y_pred_clipped = np.clip(y_pred_probs, 1e-15, 1 - 1e-15)
    log_loss = -float(
        np.mean(y_true * np.log(y_pred_clipped) + (1 - y_true) * np.log(1 - y_pred_clipped))
    )

    # Mean confidence
    mean_confidence = float(np.mean(y_pred_probs))

    metrics = {
        "ece": ece,
        "max_calibration_error": mce,
        "mean_confidence": mean_confidence,
        "brier_score": brier_score,
        "log_loss": log_loss,
        "reliability_curve": reliability,
    }

    logger.info(
        "calibration_metrics_computed",
        extra={
            "ece": ece,
            "mce": mce,
            "brier_score": brier_score,
            "log_loss": log_loss,
            "n_samples": len(y_true),
        },
    )

    return metrics


def evaluate_prediction_intervals(
    y_true: np.ndarray,
    prediction_intervals: Tuple[np.ndarray, np.ndarray],
    confidence_level: float = 0.9,
) -> Dict[str, float]:
    """
    Evaluate prediction interval quality (coverage + sharpness).

    Combines coverage (calibration) and sharpness (informativeness) metrics.

    Args:
        y_true: True values
        prediction_intervals: Tuple of (lower_bounds, upper_bounds)
        confidence_level: Nominal confidence level (e.g., 0.9 for 90%)

    Returns:
        metrics: Dictionary with:
            - 'empirical_coverage': Fraction of points in intervals
            - 'target_coverage': Target coverage (confidence_level)
            - 'coverage_gap': Empirical - target coverage
            - 'mean_interval_width': Average interval width (sharpness)
            - 'median_interval_width': Median interval width
            - 'interval_score': Interval score (proper scoring rule)

    Note:
        Interval score is a proper scoring rule that penalizes both
        miscoverage and excessive width. Lower is better.

    Example:
        >>> lower, upper = conformal_predictor.predict_interval(y_pred, 0.9)
        >>> metrics = evaluate_prediction_intervals(y_test, (lower, upper), 0.9)
        >>> print(f"Coverage: {metrics['empirical_coverage']:.1%}")
        >>> print(f"Mean width: {metrics['mean_interval_width']:.1f}")
    """
    lower_bounds, upper_bounds = prediction_intervals

    # Validate inputs
    y_true = np.asarray(y_true)
    lower_bounds = np.asarray(lower_bounds)
    upper_bounds = np.asarray(upper_bounds)

    if len(y_true) != len(lower_bounds) or len(y_true) != len(upper_bounds):
        raise ValueError("All arrays must have same length")

    if len(y_true) == 0:
        raise ValueError("Arrays cannot be empty")

    if not np.all(lower_bounds <= upper_bounds):
        raise ValueError("Lower bounds must be <= upper bounds")

    # Coverage
    in_interval = (y_true >= lower_bounds) & (y_true <= upper_bounds)
    empirical_coverage = float(np.mean(in_interval))
    coverage_gap = empirical_coverage - confidence_level

    # Sharpness
    widths = upper_bounds - lower_bounds
    mean_width = float(np.mean(widths))
    median_width = float(np.median(widths))

    # Interval score (Gneiting & Raftery 2007)
    # Proper scoring rule: penalizes both width and miscoverage
    alpha = 1 - confidence_level
    interval_scores = widths.copy()

    # Penalize points below interval
    below = y_true < lower_bounds
    interval_scores[below] += (2 / alpha) * (lower_bounds[below] - y_true[below])

    # Penalize points above interval
    above = y_true > upper_bounds
    interval_scores[above] += (2 / alpha) * (y_true[above] - upper_bounds[above])

    mean_interval_score = float(np.mean(interval_scores))

    metrics = {
        "empirical_coverage": empirical_coverage,
        "target_coverage": confidence_level,
        "coverage_gap": coverage_gap,
        "mean_interval_width": mean_width,
        "median_interval_width": median_width,
        "interval_score": mean_interval_score,
    }

    logger.info(
        "prediction_intervals_evaluated",
        extra={
            "empirical_coverage": empirical_coverage,
            "target_coverage": confidence_level,
            "mean_width": mean_width,
            "interval_score": mean_interval_score,
            "n_samples": len(y_true),
        },
    )

    return metrics

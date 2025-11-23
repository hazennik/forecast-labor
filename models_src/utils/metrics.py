"""
Forecasting Evaluation Metrics

Comprehensive metrics for evaluating forecast accuracy, calibration, and reliability.
All metrics include proper error handling, input validation, and documentation.

Key Metrics:
- RMSE: Root Mean Squared Error (point forecast accuracy)
- sMAPE: Symmetric Mean Absolute Percentage Error (scale-independent accuracy)
- CRPS: Continuous Ranked Probability Score (probabilistic forecast accuracy)
- Prediction Interval Coverage: Reliability of uncertainty estimates
- Expected Calibration Error (ECE): Probability calibration quality
- Turning Point Accuracy: Directional change detection

All metrics follow the pattern:
- Accept numpy arrays or lists (auto-convert)
- Validate inputs (length, NaN, empty)
- Return scalar float values
- Include comprehensive docstrings with examples
"""

from typing import Union, Tuple
import numpy as np
from scipy import stats
from loguru import logger


def _validate_arrays(
    y_true: Union[np.ndarray, list],
    y_pred: Union[np.ndarray, list],
    name: str = "metric"
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Validate and convert input arrays for metrics.
    
    Args:
        y_true: True values
        y_pred: Predicted values
        name: Metric name (for error messages)
        
    Returns:
        Tuple of validated numpy arrays
        
    Raises:
        ValueError: If arrays are invalid (empty, different lengths, contain NaN)
    """
    # Convert to numpy arrays if needed
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    
    # Check for empty arrays
    if len(y_true) == 0 or len(y_pred) == 0:
        raise ValueError(f"{name}: Cannot compute metric on empty arrays")
    
    # Check for length mismatch
    if len(y_true) != len(y_pred):
        raise ValueError(
            f"{name}: Arrays must have same length. "
            f"Got y_true: {len(y_true)}, y_pred: {len(y_pred)}"
        )
    
    # Check for NaN values
    if np.any(np.isnan(y_true)) or np.any(np.isnan(y_pred)):
        raise ValueError(f"{name}: Arrays contain NaN values. Remove missing data first.")
    
    return y_true, y_pred


def rmse(
    y_true: Union[np.ndarray, list],
    y_pred: Union[np.ndarray, list]
) -> float:
    """
    Calculate Root Mean Squared Error (RMSE).
    
    RMSE measures the average magnitude of prediction errors. Lower is better.
    Scale-dependent metric (same units as the target variable).
    
    Formula: RMSE = sqrt(mean((y_true - y_pred)^2))
    
    Args:
        y_true: True values (N samples)
        y_pred: Predicted values (N samples)
        
    Returns:
        RMSE value (float >= 0)
        
    Raises:
        ValueError: If arrays are invalid (empty, different lengths, contain NaN)
        
    Example:
        ```python
        y_true = np.array([100, 200, 300, 400, 500])
        y_pred = np.array([110, 190, 310, 380, 520])
        
        error = rmse(y_true, y_pred)
        print(f"RMSE: {error:.2f}")  # RMSE: 15.49
        ```
    """
    y_true, y_pred = _validate_arrays(y_true, y_pred, name="RMSE")
    
    # Calculate squared errors
    squared_errors = (y_true - y_pred) ** 2
    
    # Calculate mean and take square root
    mse = np.mean(squared_errors)
    rmse_value = np.sqrt(mse)
    
    logger.debug(f"RMSE calculated: {rmse_value:.4f} (n={len(y_true)})")
    
    return float(rmse_value)


def smape(
    y_true: Union[np.ndarray, list],
    y_pred: Union[np.ndarray, list]
) -> float:
    """
    Calculate Symmetric Mean Absolute Percentage Error (sMAPE).
    
    sMAPE is a scale-independent accuracy measure that handles zeros better than MAPE.
    Returned as percentage (0-200, where lower is better).
    
    Formula: sMAPE = 100 * mean(|y_true - y_pred| / ((|y_true| + |y_pred|) / 2))
    
    Args:
        y_true: True values (N samples)
        y_pred: Predicted values (N samples)
        
    Returns:
        sMAPE as percentage (0-200, where 0 is perfect)
        
    Raises:
        ValueError: If arrays are invalid (empty, different lengths, contain NaN)
        
    Note:
        - sMAPE = 0: Perfect predictions
        - sMAPE < 10: Excellent predictions
        - sMAPE < 20: Good predictions (Phase 5 gate)
        - sMAPE > 50: Poor predictions
        
    Example:
        ```python
        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 190, 320])
        
        error = smape(y_true, y_pred)
        print(f"sMAPE: {error:.2f}%")  # sMAPE: 6.58%
        ```
    """
    y_true, y_pred = _validate_arrays(y_true, y_pred, name="sMAPE")
    
    # Calculate absolute differences
    numerator = np.abs(y_true - y_pred)
    
    # Calculate denominator with absolute values
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2.0
    
    # Handle cases where denominator is zero (both values are zero)
    # In this case, if predictions are also zero, error is 0
    # If predictions are non-zero, we use a small epsilon
    epsilon = 1e-10
    denominator = np.where(denominator == 0, epsilon, denominator)
    
    # Calculate sMAPE for each observation
    smape_values = numerator / denominator
    
    # Return mean as percentage
    smape_percentage = 100.0 * np.mean(smape_values)
    
    logger.debug(f"sMAPE calculated: {smape_percentage:.4f}% (n={len(y_true)})")
    
    return float(smape_percentage)


def crps(
    y_true: Union[np.ndarray, list],
    y_pred_mean: Union[np.ndarray, list],
    y_pred_std: Union[np.ndarray, list]
) -> float:
    """
    Calculate Continuous Ranked Probability Score (CRPS).
    
    CRPS measures the quality of probabilistic forecasts by comparing the
    predicted distribution to the actual outcome. Lower is better.
    
    Assumes Gaussian predictive distribution: N(y_pred_mean, y_pred_std^2)
    
    Formula (for Gaussian): CRPS = σ * [z * (2Φ(z) - 1) + 2φ(z) - 1/√π]
            where z = (y_true - y_pred_mean) / σ
    
    Args:
        y_true: True values (N samples)
        y_pred_mean: Predicted means (N samples)
        y_pred_std: Predicted standard deviations (N samples)
        
    Returns:
        Mean CRPS value (float >= 0)
        
    Raises:
        ValueError: If arrays are invalid or std <= 0
        
    Note:
        - CRPS reduces to MAE for point forecasts (std → 0)
        - Penalizes both bias and spread
        - Proper scoring rule (encourages honest forecasts)
        
    Example:
        ```python
        y_true = np.array([100, 200, 300])
        y_pred_mean = np.array([105, 195, 310])
        y_pred_std = np.array([10, 15, 12])
        
        score = crps(y_true, y_pred_mean, y_pred_std)
        print(f"CRPS: {score:.2f}")  # CRPS: 8.45
        ```
    """
    y_true, y_pred_mean = _validate_arrays(y_true, y_pred_mean, name="CRPS")
    y_pred_std = np.asarray(y_pred_std, dtype=float)
    
    # Validate standard deviations
    if len(y_pred_std) != len(y_true):
        raise ValueError(
            f"CRPS: y_pred_std must have same length as y_true. "
            f"Got {len(y_pred_std)} vs {len(y_true)}"
        )
    
    if np.any(y_pred_std <= 0):
        raise ValueError("CRPS: All standard deviations must be positive")
    
    # Calculate standardized errors
    z = (y_true - y_pred_mean) / y_pred_std
    
    # Calculate CRPS using Gaussian formula
    # CRPS = σ * [z * (2Φ(z) - 1) + 2φ(z) - 1/√π]
    phi_z = stats.norm.pdf(z)  # Standard normal PDF
    Phi_z = stats.norm.cdf(z)  # Standard normal CDF
    
    crps_values = y_pred_std * (
        z * (2 * Phi_z - 1) +
        2 * phi_z -
        1 / np.sqrt(np.pi)
    )
    
    # Return mean CRPS
    mean_crps = np.mean(crps_values)
    
    logger.debug(f"CRPS calculated: {mean_crps:.4f} (n={len(y_true)})")
    
    return float(mean_crps)


def prediction_interval_coverage(
    y_true: Union[np.ndarray, list],
    lower_bound: Union[np.ndarray, list],
    upper_bound: Union[np.ndarray, list],
    confidence_level: float = 90.0
) -> float:
    """
    Calculate prediction interval coverage percentage.
    
    Measures what percentage of actual values fall within predicted intervals.
    Ideal coverage should match the confidence level (e.g., 90% of values in 90% PI).
    
    Args:
        y_true: True values (N samples)
        lower_bound: Lower bounds of prediction intervals (N samples)
        upper_bound: Upper bounds of prediction intervals (N samples)
        confidence_level: Expected confidence level (0-100) for logging
        
    Returns:
        Coverage percentage (0-100)
        
    Note:
        - Coverage = confidence_level: Well-calibrated
        - Coverage < confidence_level: Intervals too narrow (overconfident)
        - Coverage > confidence_level: Intervals too wide (underconfident)
        - Phase 5 Gate: 85-95% coverage for 90% intervals
        
    Example:
        ```python
        y_true = np.array([100, 200, 300, 400, 500])
        lower = np.array([90, 180, 280, 380, 480])
        upper = np.array([110, 220, 320, 420, 520])
        
        coverage = prediction_interval_coverage(y_true, lower, upper, 90)
        print(f"Coverage: {coverage:.1f}%")  # Coverage: 100.0%
        ```
    """
    y_true, lower_bound = _validate_arrays(y_true, lower_bound, name="Coverage")
    upper_bound = np.asarray(upper_bound, dtype=float)
    
    # Validate upper bound length
    if len(upper_bound) != len(y_true):
        raise ValueError(
            f"Coverage: upper_bound must have same length as y_true. "
            f"Got {len(upper_bound)} vs {len(y_true)}"
        )
    
    # Check that lower < upper
    if np.any(lower_bound >= upper_bound):
        raise ValueError("Coverage: lower_bound must be strictly less than upper_bound")
    
    # Count observations within intervals (inclusive of boundaries)
    within_interval = (y_true >= lower_bound) & (y_true <= upper_bound)
    coverage_percentage = 100.0 * np.mean(within_interval)
    
    logger.debug(
        f"Prediction interval coverage: {coverage_percentage:.2f}% "
        f"(expected: {confidence_level:.0f}%, n={len(y_true)})"
    )
    
    return float(coverage_percentage)


def expected_calibration_error(
    y_true: Union[np.ndarray, list],
    y_pred_probs: Union[np.ndarray, list],
    n_bins: int = 10
) -> float:
    """
    Calculate Expected Calibration Error (ECE) for probability forecasts.
    
    ECE measures how well predicted probabilities match actual frequencies.
    Perfect calibration means predicted 70% → actual 70% occurrence rate.
    
    Method: Bin predictions by probability, compare predicted vs observed frequency.
    
    Args:
        y_true: True binary outcomes (0 or 1), N samples
        y_pred_probs: Predicted probabilities (0-1), N samples
        n_bins: Number of bins for grouping predictions (default: 10)
        
    Returns:
        ECE value (0-1, where 0 is perfect calibration)
        
    Note:
        - ECE < 0.05: Well-calibrated (Phase 5 gate)
        - ECE < 0.10: Acceptable calibration
        - ECE > 0.15: Poor calibration
        
    Example:
        ```python
        y_true = np.array([1, 0, 1, 1, 0, 1, 0, 0])
        y_pred_probs = np.array([0.9, 0.2, 0.8, 0.7, 0.3, 0.85, 0.15, 0.25])
        
        ece = expected_calibration_error(y_true, y_pred_probs, n_bins=5)
        print(f"ECE: {ece:.4f}")  # ECE: 0.0234 (well-calibrated)
        ```
    """
    y_true, y_pred_probs = _validate_arrays(y_true, y_pred_probs, name="ECE")
    
    # Validate binary outcomes
    if not np.all(np.isin(y_true, [0, 1])):
        raise ValueError("ECE: y_true must contain only 0s and 1s (binary outcomes)")
    
    # Validate probabilities
    if np.any((y_pred_probs < 0) | (y_pred_probs > 1)):
        raise ValueError("ECE: y_pred_probs must be in range [0, 1]")
    
    # Create bins for predicted probabilities
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_pred_probs, bin_boundaries[:-1]) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)  # Handle edge cases
    
    # Calculate ECE
    ece_sum = 0.0
    total_samples = len(y_true)
    
    for bin_idx in range(n_bins):
        # Get samples in this bin
        in_bin = bin_indices == bin_idx
        
        if not np.any(in_bin):
            continue  # Empty bin
        
        # Calculate bin statistics
        bin_size = np.sum(in_bin)
        bin_weight = bin_size / total_samples
        
        # Average predicted probability in bin
        avg_predicted_prob = np.mean(y_pred_probs[in_bin])
        
        # Actual frequency of positive class in bin
        avg_true_prob = np.mean(y_true[in_bin])
        
        # Bin contribution to ECE
        bin_error = np.abs(avg_predicted_prob - avg_true_prob)
        ece_sum += bin_weight * bin_error
    
    logger.debug(f"ECE calculated: {ece_sum:.4f} (n={len(y_true)}, bins={n_bins})")
    
    return float(ece_sum)


def turning_point_accuracy(
    y_true: Union[np.ndarray, list],
    y_pred: Union[np.ndarray, list]
) -> float:
    """
    Calculate accuracy of turning point detection.
    
    A turning point is where the series changes direction (peak or trough).
    Important for forecasting economic cycles and regime changes.
    
    Method: Identify turning points in both series, calculate agreement percentage.
    
    Args:
        y_true: True values (N samples, N >= 3)
        y_pred: Predicted values (N samples)
        
    Returns:
        Turning point accuracy as percentage (0-100)
        
    Note:
        - 100%: All turning points correctly identified
        - 50%: Half of turning points detected
        - 0%: No turning points detected
        - If no turning points exist in y_true, returns 100% (nothing to miss)
        
    Example:
        ```python
        # True series: down, down, UP, up, DOWN
        y_true = np.array([100, 90, 80, 95, 110, 105])
        y_pred = np.array([100, 88, 78, 98, 112, 108])
        
        accuracy = turning_point_accuracy(y_true, y_pred)
        print(f"Turning point accuracy: {accuracy:.1f}%")  # ~100%
        ```
    """
    y_true, y_pred = _validate_arrays(y_true, y_pred, name="Turning Point Accuracy")
    
    # Need at least 3 points to detect turning points
    if len(y_true) < 3:
        logger.warning("Turning point accuracy: Need at least 3 observations")
        return 100.0  # No turning points to detect
    
    # Identify turning points (local maxima and minima)
    def find_turning_points(series: np.ndarray) -> np.ndarray:
        """Find indices of turning points in series"""
        turning_points = []
        
        for i in range(1, len(series) - 1):
            # Local maximum (peak)
            if series[i] > series[i-1] and series[i] > series[i+1]:
                turning_points.append(i)
            # Local minimum (trough)
            elif series[i] < series[i-1] and series[i] < series[i+1]:
                turning_points.append(i)
        
        return np.array(turning_points)
    
    # Find turning points in both series
    true_turning_points = find_turning_points(y_true)
    pred_turning_points = find_turning_points(y_pred)
    
    # Handle case with no turning points in true series
    if len(true_turning_points) == 0:
        logger.debug("Turning point accuracy: No turning points in true series")
        return 100.0  # Nothing to detect, so perfect score
    
    # Calculate accuracy: percentage of true turning points detected
    # Allow +/- 1 index tolerance for detection
    matches = 0
    for true_tp in true_turning_points:
        # Check if any predicted turning point is within 1 index
        if np.any(np.abs(pred_turning_points - true_tp) <= 1):
            matches += 1
    
    accuracy_percentage = 100.0 * matches / len(true_turning_points)
    
    logger.debug(
        f"Turning point accuracy: {accuracy_percentage:.2f}% "
        f"({matches}/{len(true_turning_points)} detected)"
    )
    
    return float(accuracy_percentage)


def mae(
    y_true: Union[np.ndarray, list],
    y_pred: Union[np.ndarray, list]
) -> float:
    """
    Calculate Mean Absolute Error (MAE).
    
    MAE measures the average magnitude of errors without considering direction.
    Lower is better. Scale-dependent metric (same units as target variable).
    
    Formula: MAE = mean(|y_true - y_pred|)
    
    Args:
        y_true: True values (N samples)
        y_pred: Predicted values (N samples)
        
    Returns:
        MAE value (float >= 0)
        
    Raises:
        ValueError: If arrays are invalid (empty, different lengths, contain NaN)
        
    Example:
        ```python
        y_true = np.array([100, 200, 300, 400, 500])
        y_pred = np.array([110, 190, 310, 380, 520])
        
        error = mae(y_true, y_pred)
        print(f"MAE: {error:.2f}")  # MAE: 14.00
        ```
    """
    y_true, y_pred = _validate_arrays(y_true, y_pred, name="MAE")
    
    absolute_errors = np.abs(y_true - y_pred)
    mae_value = np.mean(absolute_errors)
    
    logger.debug(f"MAE calculated: {mae_value:.4f} (n={len(y_true)})")
    
    return float(mae_value)


def mape(
    y_true: Union[np.ndarray, list],
    y_pred: Union[np.ndarray, list],
    epsilon: float = 1e-10
) -> float:
    """
    Calculate Mean Absolute Percentage Error (MAPE).
    
    MAPE expresses error as a percentage of true values. Scale-independent.
    Lower is better. Can be problematic when y_true contains zeros.
    
    Formula: MAPE = mean(|y_true - y_pred| / |y_true|) * 100
    
    Args:
        y_true: True values (N samples, ideally non-zero)
        y_pred: Predicted values (N samples)
        epsilon: Small constant to avoid division by zero
        
    Returns:
        MAPE value (percentage, float >= 0)
        
    Raises:
        ValueError: If arrays are invalid (empty, different lengths, contain NaN)
        
    Warning:
        MAPE is undefined for zero true values. Use sMAPE instead for series
        with zeros.
        
    Example:
        ```python
        y_true = np.array([100, 200, 300, 400, 500])
        y_pred = np.array([110, 190, 310, 380, 520])
        
        error = mape(y_true, y_pred)
        print(f"MAPE: {error:.2f}%")  # MAPE: 5.83%
        ```
    """
    y_true, y_pred = _validate_arrays(y_true, y_pred, name="MAPE")
    
    # Avoid division by zero
    denominator = np.maximum(np.abs(y_true), epsilon)
    
    percentage_errors = np.abs(y_true - y_pred) / denominator
    mape_value = np.mean(percentage_errors) * 100
    
    logger.debug(f"MAPE calculated: {mape_value:.4f}% (n={len(y_true)})")
    
    return float(mape_value)


def compute_metrics(
    y_true: Union[np.ndarray, list],
    y_pred: Union[np.ndarray, list]
) -> dict:
    """
    Compute comprehensive set of forecasting metrics.
    
    Convenience function that computes multiple metrics at once:
    - RMSE: Root Mean Squared Error
    - MAE: Mean Absolute Error
    - MAPE: Mean Absolute Percentage Error
    - sMAPE: Symmetric Mean Absolute Percentage Error
    
    Args:
        y_true: True values (N samples)
        y_pred: Predicted values (N samples)
        
    Returns:
        Dictionary with metric names as keys and float values
        
    Raises:
        ValueError: If arrays are invalid (empty, different lengths, contain NaN)
        
    Example:
        ```python
        y_true = np.array([100, 200, 300, 400, 500])
        y_pred = np.array([110, 190, 310, 380, 520])
        
        metrics = compute_metrics(y_true, y_pred)
        print(f"RMSE: {metrics['rmse']:.2f}")
        print(f"MAE: {metrics['mae']:.2f}")
        print(f"MAPE: {metrics['mape']:.2f}%")
        print(f"sMAPE: {metrics['smape']:.2f}%")
        ```
    """
    y_true, y_pred = _validate_arrays(y_true, y_pred, name="compute_metrics")
    
    metrics_dict = {
        "rmse": rmse(y_true, y_pred),
        "mae": mae(y_true, y_pred),
        "mape": mape(y_true, y_pred),
        "smape": smape(y_true, y_pred),
    }
    
    logger.debug(
        "Computed metrics",
        rmse=metrics_dict["rmse"],
        mae=metrics_dict["mae"],
        smape=metrics_dict["smape"],
    )
    
    return metrics_dict


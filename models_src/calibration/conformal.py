"""
Split Conformal Prediction for distribution-free prediction intervals.

Provides coverage guarantees for prediction intervals without assuming
any distribution on the data. Uses calibration set residuals to construct
intervals with valid finite-sample coverage.

Key Features:
- Distribution-free coverage guarantees
- Split conformal method (train/calibration split)
- Adaptive intervals (width varies by prediction)
- Multiple confidence levels (80%, 90%, 95%)
- Coverage validation and diagnostics

References:
- Vovk et al. (2005): Algorithmic Learning in a Random World
- Lei et al. (2018): Distribution-Free Predictive Inference for Regression
- Angelopoulos & Bates (2021): A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification
"""

from typing import Dict, Any, Optional, Tuple, Union, List
from pathlib import Path
import numpy as np
import pandas as pd
from loguru import logger
import joblib


class ConformalPredictor:
    """
    Split conformal prediction for regression.
    
    Constructs prediction intervals with distribution-free coverage guarantees.
    Uses calibration set to compute non-conformity scores (residuals),
    then applies quantiles of these scores to form intervals.
    
    Args:
        confidence_levels: List of confidence levels (e.g., [0.8, 0.9, 0.95])
        adaptive: Whether to use adaptive intervals (width varies by prediction)
        adaptive_gamma: Smoothing parameter for adaptive intervals (higher = more adaptive)
        
    Attributes:
        quantiles_: Dictionary of non-conformity score quantiles per confidence level
        calibration_scores_: Non-conformity scores from calibration set
        is_fitted_: Whether conformal predictor has been fitted
        n_calibration_: Number of calibration samples
        coverage_diagnostics_: Coverage metrics from calibration set
        
    Example:
        >>> # Fit on calibration set (y_true, y_pred from held-out data)
        >>> conformal = ConformalPredictor(confidence_levels=[0.9])
        >>> conformal.fit(y_calib_true, y_calib_pred)
        >>> 
        >>> # Apply to test set predictions
        >>> lower, upper = conformal.predict_interval(y_test_pred, confidence_level=0.9)
        >>> coverage = np.mean((y_test_true >= lower) & (y_test_true <= upper))
        >>> print(f"Empirical coverage: {coverage:.1%}")  # Should be ~90%
    """
    
    DEFAULT_CONFIDENCE_LEVELS = [0.8, 0.9, 0.95]
    
    def __init__(
        self,
        confidence_levels: Optional[List[float]] = None,
        adaptive: bool = False,
        adaptive_gamma: float = 0.1
    ):
        """Initialize conformal predictor."""
        self.confidence_levels = (
            confidence_levels if confidence_levels is not None
            else self.DEFAULT_CONFIDENCE_LEVELS
        )
        self.adaptive = adaptive
        self.adaptive_gamma = adaptive_gamma
        
        # Fitted state (set during fit)
        self.quantiles_: Optional[Dict[float, float]] = None
        self.calibration_scores_: Optional[np.ndarray] = None
        self.is_fitted_: bool = False
        self.n_calibration_: Optional[int] = None
        self.coverage_diagnostics_: Optional[Dict[str, Any]] = None
        
        # For adaptive intervals
        self.y_pred_calibration_: Optional[np.ndarray] = None
        
        self._validate_parameters()
        
        logger.debug(
            "conformal_predictor_initialized",
            extra={
                'confidence_levels': self.confidence_levels,
                'adaptive': adaptive,
                'adaptive_gamma': adaptive_gamma
            }
        )
    
    def _validate_parameters(self) -> None:
        """Validate initialization parameters."""
        if len(self.confidence_levels) == 0:
            raise ValueError("confidence_levels list cannot be empty")
        
        for conf in self.confidence_levels:
            if not 0 < conf < 1:
                raise ValueError(
                    f"All confidence levels must be in (0, 1), got {conf}"
                )
        
        if self.adaptive_gamma <= 0:
            raise ValueError(
                f"adaptive_gamma must be positive, got {self.adaptive_gamma}"
            )
    
    def fit(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> 'ConformalPredictor':
        """
        Fit conformal predictor on calibration set.
        
        Computes non-conformity scores (absolute residuals) and their quantiles
        for each confidence level. These quantiles define prediction interval widths.
        
        Args:
            y_true: True values from calibration set (N samples)
            y_pred: Predicted values from calibration set (N samples)
            
        Returns:
            self: For method chaining
            
        Raises:
            ValueError: If inputs are invalid
        """
        # Validate inputs
        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)
        
        if len(y_true) != len(y_pred):
            raise ValueError(
                f"y_true and y_pred must have same length. "
                f"Got y_true={len(y_true)}, y_pred={len(y_pred)}"
            )
        
        if len(y_true) == 0:
            raise ValueError("y_true and y_pred cannot be empty")
        
        if len(y_true) < 30:
            logger.warning(
                "small_calibration_set",
                extra={
                    'n_samples': len(y_true),
                    'recommendation': 'Use at least 30-50 samples for reliable intervals'
                }
            )
        
        self.n_calibration_ = len(y_true)
        
        logger.info(
            "conformal_predictor_fit_started",
            extra={
                'n_calibration': self.n_calibration_,
                'confidence_levels': self.confidence_levels,
                'adaptive': self.adaptive
            }
        )
        
        # Compute non-conformity scores (absolute residuals)
        self.calibration_scores_ = np.abs(y_true - y_pred)
        
        # Store predictions for adaptive intervals
        if self.adaptive:
            self.y_pred_calibration_ = y_pred.copy()
        
        # Compute quantiles for each confidence level
        self.quantiles_ = {}
        
        for conf_level in self.confidence_levels:
            # For (1-α) coverage, use (1-α) quantile of scores
            # Add 1/n correction for finite-sample guarantee
            adjusted_quantile = min(1.0, conf_level + 1 / (self.n_calibration_ + 1))
            
            quantile_value = np.quantile(self.calibration_scores_, adjusted_quantile)
            self.quantiles_[conf_level] = float(quantile_value)
            
            logger.debug(
                "computed_conformal_quantile",
                extra={
                    'confidence_level': conf_level,
                    'quantile': float(quantile_value),
                    'adjusted_quantile': adjusted_quantile
                }
            )
        
        self.is_fitted_ = True
        
        # Compute coverage diagnostics on calibration set
        self._compute_coverage_diagnostics(y_true, y_pred)
        
        logger.info(
            "conformal_predictor_fit_completed",
            extra={
                'n_calibration': self.n_calibration_,
                'quantiles': {k: float(v) for k, v in self.quantiles_.items()}
            }
        )
        
        return self
    
    def predict_interval(
        self,
        y_pred: np.ndarray,
        confidence_level: float = 0.9
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Construct prediction intervals for new predictions.
        
        Args:
            y_pred: Point predictions (N samples)
            confidence_level: Desired confidence level (must be in fitted levels)
            
        Returns:
            lower: Lower bounds of prediction intervals (N samples)
            upper: Upper bounds of prediction intervals (N samples)
            
        Raises:
            ValueError: If not fitted or confidence level not available
        """
        if not self.is_fitted_:
            raise ValueError(
                "Conformal predictor must be fitted before prediction. Call fit() first."
            )
        
        if confidence_level not in self.quantiles_:
            raise ValueError(
                f"Confidence level {confidence_level} not found. "
                f"Available levels: {list(self.quantiles_.keys())}"
            )
        
        # Validate input
        y_pred = np.asarray(y_pred)
        
        if len(y_pred) == 0:
            raise ValueError("y_pred cannot be empty")
        
        logger.debug(
            "conformal_predict_interval",
            extra={
                'n_samples': len(y_pred),
                'confidence_level': confidence_level
            }
        )
        
        # Get quantile for this confidence level
        quantile = self.quantiles_[confidence_level]
        
        if self.adaptive:
            # Adaptive intervals: width varies by prediction magnitude
            interval_width = self._compute_adaptive_width(y_pred, quantile)
        else:
            # Fixed-width intervals
            interval_width = quantile
        
        # Construct intervals
        lower = y_pred - interval_width
        upper = y_pred + interval_width
        
        return lower, upper
    
    def _compute_adaptive_width(
        self,
        y_pred: np.ndarray,
        base_quantile: float
    ) -> np.ndarray:
        """
        Compute adaptive interval widths that vary by prediction magnitude.
        
        Uses locally weighted approach: predictions similar to calibration
        predictions get narrower intervals.
        
        Args:
            y_pred: Point predictions
            base_quantile: Base quantile value
            
        Returns:
            interval_widths: Array of interval half-widths
        """
        if self.y_pred_calibration_ is None:
            # Fallback to fixed width
            return np.full(len(y_pred), base_quantile)
        
        # Compute weights based on similarity to calibration predictions
        # Higher weight = prediction closer to calibration region
        weights = np.zeros(len(y_pred))
        
        for i, pred in enumerate(y_pred):
            # Distance to calibration predictions
            distances = np.abs(self.y_pred_calibration_ - pred)
            
            # Kernel weights (Gaussian-like)
            kernel_weights = np.exp(-distances / (self.adaptive_gamma * np.std(self.y_pred_calibration_)))
            
            # Weighted quantile of calibration scores
            sorted_indices = np.argsort(self.calibration_scores_)
            sorted_scores = self.calibration_scores_[sorted_indices]
            sorted_weights = kernel_weights[sorted_indices]
            
            # Normalize weights
            sorted_weights = sorted_weights / (sorted_weights.sum() + 1e-10)
            
            # Cumulative weights
            cumsum_weights = np.cumsum(sorted_weights)
            
            # Find weighted quantile
            target_quantile = 0.9  # Use 90th percentile for adaptive
            idx = np.searchsorted(cumsum_weights, target_quantile)
            idx = min(idx, len(sorted_scores) - 1)
            
            weights[i] = sorted_scores[idx]
        
        # Blend with base quantile for stability
        alpha = 0.7  # Weight towards adaptive
        interval_widths = alpha * weights + (1 - alpha) * base_quantile
        
        return interval_widths
    
    def _compute_coverage_diagnostics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> None:
        """
        Compute coverage diagnostics on calibration set.
        
        Args:
            y_true: True values
            y_pred: Predicted values
        """
        diagnostics = {}
        
        for conf_level in self.confidence_levels:
            lower, upper = self.predict_interval(y_pred, confidence_level=conf_level)
            
            # Empirical coverage
            coverage = np.mean((y_true >= lower) & (y_true <= upper))
            
            # Average interval width
            avg_width = np.mean(upper - lower)
            
            # Coverage by prediction magnitude (stratified)
            y_pred_sorted_idx = np.argsort(y_pred)
            n_strata = 5
            stratum_size = len(y_pred) // n_strata
            
            stratified_coverage = []
            for i in range(n_strata):
                start_idx = i * stratum_size
                end_idx = (i + 1) * stratum_size if i < n_strata - 1 else len(y_pred)
                
                stratum_idx = y_pred_sorted_idx[start_idx:end_idx]
                stratum_coverage = np.mean(
                    (y_true[stratum_idx] >= lower[stratum_idx]) &
                    (y_true[stratum_idx] <= upper[stratum_idx])
                )
                stratified_coverage.append(float(stratum_coverage))
            
            diagnostics[conf_level] = {
                'empirical_coverage': float(coverage),
                'avg_interval_width': float(avg_width),
                'stratified_coverage': stratified_coverage
            }
        
        self.coverage_diagnostics_ = diagnostics
    
    def validate_coverage(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        confidence_level: float = 0.9
    ) -> Dict[str, float]:
        """
        Validate coverage on a test set.
        
        Args:
            y_true: True values from test set
            y_pred: Predicted values from test set
            confidence_level: Confidence level to validate
            
        Returns:
            metrics: Dictionary with coverage metrics
                - 'empirical_coverage': Fraction of points in intervals
                - 'target_coverage': Target coverage (confidence_level)
                - 'coverage_gap': Difference from target
                - 'avg_interval_width': Average interval width
        """
        if not self.is_fitted_:
            raise ValueError("Conformal predictor must be fitted before validation")
        
        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)
        
        if len(y_true) != len(y_pred):
            raise ValueError("y_true and y_pred must have same length")
        
        # Construct intervals
        lower, upper = self.predict_interval(y_pred, confidence_level=confidence_level)
        
        # Compute metrics
        in_interval = (y_true >= lower) & (y_true <= upper)
        empirical_coverage = np.mean(in_interval)
        avg_width = np.mean(upper - lower)
        
        metrics = {
            'empirical_coverage': float(empirical_coverage),
            'target_coverage': float(confidence_level),
            'coverage_gap': float(empirical_coverage - confidence_level),
            'avg_interval_width': float(avg_width),
            'n_samples': len(y_true)
        }
        
        logger.info(
            "coverage_validation",
            extra=metrics
        )
        
        return metrics
    
    def get_params(self) -> Dict[str, Any]:
        """
        Get conformal predictor parameters and metadata.
        
        Returns:
            params: Dictionary of parameters
        """
        return {
            'confidence_levels': self.confidence_levels,
            'adaptive': self.adaptive,
            'adaptive_gamma': self.adaptive_gamma,
            'is_fitted': self.is_fitted_,
            'n_calibration': self.n_calibration_,
            'quantiles': self.quantiles_,
            'coverage_diagnostics': self.coverage_diagnostics_
        }
    
    def save(self, path: Path) -> None:
        """
        Save conformal predictor to disk.
        
        Args:
            path: Path to save predictor (.pkl or .joblib)
        """
        if not self.is_fitted_:
            raise ValueError("Cannot save unfitted conformal predictor. Call fit() first.")
        
        predictor_data = {
            'params': {
                'confidence_levels': self.confidence_levels,
                'adaptive': self.adaptive,
                'adaptive_gamma': self.adaptive_gamma
            },
            'state': {
                'quantiles': self.quantiles_,
                'calibration_scores': self.calibration_scores_,
                'n_calibration': self.n_calibration_,
                'coverage_diagnostics': self.coverage_diagnostics_,
                'y_pred_calibration': self.y_pred_calibration_
            }
        }
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        joblib.dump(predictor_data, path)
        
        logger.info(
            "conformal_predictor_saved",
            extra={
                'path': str(path),
                'file_size_bytes': path.stat().st_size
            }
        )
    
    @classmethod
    def load(cls, path: Path) -> 'ConformalPredictor':
        """
        Load conformal predictor from disk.
        
        Args:
            path: Path to saved predictor file
            
        Returns:
            predictor: Loaded conformal predictor
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Conformal predictor file not found: {path}")
        
        predictor_data = joblib.load(path)
        params = predictor_data['params']
        state = predictor_data['state']
        
        # Reconstruct predictor
        predictor = cls(
            confidence_levels=params['confidence_levels'],
            adaptive=params['adaptive'],
            adaptive_gamma=params['adaptive_gamma']
        )
        
        # Restore fitted state
        predictor.quantiles_ = state['quantiles']
        predictor.calibration_scores_ = state['calibration_scores']
        predictor.n_calibration_ = state['n_calibration']
        predictor.coverage_diagnostics_ = state['coverage_diagnostics']
        predictor.y_pred_calibration_ = state['y_pred_calibration']
        predictor.is_fitted_ = True
        
        logger.info(
            "conformal_predictor_loaded",
            extra={
                'path': str(path),
                'n_calibration': predictor.n_calibration_
            }
        )
        
        return predictor


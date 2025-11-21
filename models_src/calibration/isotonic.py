"""
Isotonic Regression Calibration for probabilistic forecasts.

Improves reliability of probability predictions by learning a monotonic
mapping from uncalibrated to calibrated probabilities.

Key Features:
- Non-parametric calibration (learns from data)
- Monotonic transformation (preserves probability ordering)
- Sklearn-compatible API (fit, transform, fit_transform)
- Before/after calibration metrics (ECE comparison)
- Reliability diagram generation

References:
- Zadrozny & Elkan (2002): Transforming classifier scores into accurate multiclass probability estimates
- Niculescu-Mizil & Caruana (2005): Predicting good probabilities with supervised learning
"""

from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from loguru import logger
import joblib

from models_src.utils.metrics import expected_calibration_error


class IsotonicCalibrator:
    """
    Isotonic regression calibrator for probability predictions.
    
    Learns a monotonic transformation to map uncalibrated probabilities
    to calibrated probabilities that better match observed frequencies.
    
    Args:
        out_of_bounds: How to handle predictions outside training range
            - 'clip': Clip to [0, 1] (default, safe)
            - 'nan': Return NaN for out-of-bounds values
        
    Attributes:
        calibrator_: Fitted IsotonicRegression model
        is_fitted_: Whether calibrator has been fitted
        n_samples_: Number of samples used for calibration
        ece_before_: ECE before calibration (on fit data)
        ece_after_: ECE after calibration (on fit data)
        
    Example:
        >>> # Fit calibrator on validation set
        >>> calibrator = IsotonicCalibrator()
        >>> calibrator.fit(y_val, uncalibrated_probs_val)
        >>> 
        >>> # Apply to test set
        >>> calibrated_probs = calibrator.transform(uncalibrated_probs_test)
        >>> 
        >>> # Check improvement
        >>> print(f"ECE before: {calibrator.ece_before_:.4f}")
        >>> print(f"ECE after: {calibrator.ece_after_:.4f}")
    """
    
    def __init__(self, out_of_bounds: str = 'clip'):
        """Initialize isotonic calibrator."""
        if out_of_bounds not in ['clip', 'nan']:
            raise ValueError(f"out_of_bounds must be 'clip' or 'nan', got '{out_of_bounds}'")
        
        self.out_of_bounds = out_of_bounds
        
        # Fitted state (set during fit)
        self.calibrator_: Optional[IsotonicRegression] = None
        self.is_fitted_: bool = False
        self.n_samples_: Optional[int] = None
        self.ece_before_: Optional[float] = None
        self.ece_after_: Optional[float] = None
        
        logger.debug(
            "isotonic_calibrator_initialized",
            extra={'out_of_bounds': out_of_bounds}
        )
    
    def fit(
        self,
        y_true: np.ndarray,
        y_pred_probs: np.ndarray
    ) -> 'IsotonicCalibrator':
        """
        Fit isotonic regression calibrator on validation data.
        
        Args:
            y_true: True binary outcomes (0 or 1), N samples
            y_pred_probs: Uncalibrated predicted probabilities (0-1), N samples
            
        Returns:
            self: For method chaining
            
        Raises:
            ValueError: If inputs are invalid
        """
        # Validate inputs
        y_true = np.asarray(y_true)
        y_pred_probs = np.asarray(y_pred_probs)
        
        if len(y_true) != len(y_pred_probs):
            raise ValueError(
                f"y_true and y_pred_probs must have same length. "
                f"Got y_true={len(y_true)}, y_pred_probs={len(y_pred_probs)}"
            )
        
        if len(y_true) == 0:
            raise ValueError("y_true and y_pred_probs cannot be empty")
        
        # Validate binary outcomes
        if not np.all(np.isin(y_true, [0, 1])):
            raise ValueError("y_true must contain only 0s and 1s (binary outcomes)")
        
        # Validate probabilities
        if np.any((y_pred_probs < 0) | (y_pred_probs > 1)):
            raise ValueError("y_pred_probs must be in range [0, 1]")
        
        # Check for sufficient positive and negative examples
        n_positive = np.sum(y_true)
        n_negative = len(y_true) - n_positive
        
        if n_positive == 0 or n_negative == 0:
            logger.warning(
                "calibration_data_imbalanced",
                extra={
                    'n_positive': int(n_positive),
                    'n_negative': int(n_negative),
                    'n_total': len(y_true)
                }
            )
        
        self.n_samples_ = len(y_true)
        
        logger.info(
            "isotonic_calibrator_fit_started",
            extra={
                'n_samples': self.n_samples_,
                'n_positive': int(n_positive),
                'n_negative': int(n_negative)
            }
        )
        
        # Calculate ECE before calibration
        self.ece_before_ = expected_calibration_error(y_true, y_pred_probs)
        
        # Fit isotonic regression
        # Maps uncalibrated probs → true labels, learns monotonic mapping
        self.calibrator_ = IsotonicRegression(
            y_min=0.0,
            y_max=1.0,
            increasing=True,
            out_of_bounds=self.out_of_bounds
        )
        self.calibrator_.fit(y_pred_probs, y_true)
        
        # Calculate ECE after calibration (on training data)
        y_pred_calibrated = self.calibrator_.predict(y_pred_probs)
        self.ece_after_ = expected_calibration_error(y_true, y_pred_calibrated)
        
        self.is_fitted_ = True
        
        # Calculate improvement metrics
        ece_improvement = self.ece_before_ - self.ece_after_
        ece_improvement_pct = (ece_improvement / self.ece_before_ * 100) if self.ece_before_ > 0 else 0
        
        logger.info(
            "isotonic_calibrator_fit_completed",
            extra={
                'n_samples': self.n_samples_,
                'ece_before': float(self.ece_before_),
                'ece_after': float(self.ece_after_),
                'ece_improvement': float(ece_improvement),
                'ece_improvement_pct': float(ece_improvement_pct)
            }
        )
        
        return self
    
    def transform(self, y_pred_probs: np.ndarray) -> np.ndarray:
        """
        Apply calibration transformation to predictions.
        
        Args:
            y_pred_probs: Uncalibrated predicted probabilities (0-1), N samples
            
        Returns:
            calibrated_probs: Calibrated probabilities (0-1), N samples
            
        Raises:
            ValueError: If calibrator not fitted or invalid input
        """
        if not self.is_fitted_:
            raise ValueError("Calibrator must be fitted before transform. Call fit() first.")
        
        # Validate input
        y_pred_probs = np.asarray(y_pred_probs)
        
        if len(y_pred_probs) == 0:
            raise ValueError("y_pred_probs cannot be empty")
        
        if np.any((y_pred_probs < 0) | (y_pred_probs > 1)):
            raise ValueError("y_pred_probs must be in range [0, 1]")
        
        logger.debug(
            "isotonic_calibrator_transform",
            extra={'n_samples': len(y_pred_probs)}
        )
        
        # Apply isotonic transformation
        calibrated_probs = self.calibrator_.predict(y_pred_probs)
        
        return calibrated_probs
    
    def fit_transform(
        self,
        y_true: np.ndarray,
        y_pred_probs: np.ndarray
    ) -> np.ndarray:
        """
        Fit calibrator and transform probabilities in one step.
        
        Args:
            y_true: True binary outcomes (0 or 1), N samples
            y_pred_probs: Uncalibrated predicted probabilities (0-1), N samples
            
        Returns:
            calibrated_probs: Calibrated probabilities (0-1), N samples
        """
        self.fit(y_true, y_pred_probs)
        return self.transform(y_pred_probs)
    
    def get_reliability_diagram_data(
        self,
        y_true: np.ndarray,
        y_pred_probs_uncalibrated: np.ndarray,
        y_pred_probs_calibrated: Optional[np.ndarray] = None,
        n_bins: int = 10
    ) -> Dict[str, Any]:
        """
        Generate reliability diagram data for visualization.
        
        Reliability diagrams plot predicted probability vs. observed frequency.
        Perfect calibration → points on diagonal.
        
        Args:
            y_true: True binary outcomes (0 or 1)
            y_pred_probs_uncalibrated: Uncalibrated predictions
            y_pred_probs_calibrated: Calibrated predictions (optional)
            n_bins: Number of bins for grouping predictions
            
        Returns:
            diagram_data: Dictionary with:
                - 'bins': Bin boundaries
                - 'uncalibrated_predicted': Average predicted prob per bin (uncalibrated)
                - 'uncalibrated_observed': Average observed frequency per bin (uncalibrated)
                - 'uncalibrated_counts': Number of samples per bin (uncalibrated)
                - 'calibrated_predicted': Average predicted prob per bin (calibrated, if provided)
                - 'calibrated_observed': Average observed frequency per bin (calibrated, if provided)
                - 'calibrated_counts': Number of samples per bin (calibrated, if provided)
        """
        # Validate inputs
        y_true = np.asarray(y_true)
        y_pred_probs_uncalibrated = np.asarray(y_pred_probs_uncalibrated)
        
        if len(y_true) != len(y_pred_probs_uncalibrated):
            raise ValueError("y_true and y_pred_probs_uncalibrated must have same length")
        
        # Compute uncalibrated reliability
        uncal_data = self._compute_reliability_curve(
            y_true,
            y_pred_probs_uncalibrated,
            n_bins
        )
        
        result = {
            'bins': uncal_data['bins'],
            'uncalibrated_predicted': uncal_data['predicted'],
            'uncalibrated_observed': uncal_data['observed'],
            'uncalibrated_counts': uncal_data['counts']
        }
        
        # Compute calibrated reliability if provided
        if y_pred_probs_calibrated is not None:
            y_pred_probs_calibrated = np.asarray(y_pred_probs_calibrated)
            
            if len(y_true) != len(y_pred_probs_calibrated):
                raise ValueError("y_true and y_pred_probs_calibrated must have same length")
            
            cal_data = self._compute_reliability_curve(
                y_true,
                y_pred_probs_calibrated,
                n_bins
            )
            
            result['calibrated_predicted'] = cal_data['predicted']
            result['calibrated_observed'] = cal_data['observed']
            result['calibrated_counts'] = cal_data['counts']
        
        return result
    
    def _compute_reliability_curve(
        self,
        y_true: np.ndarray,
        y_pred_probs: np.ndarray,
        n_bins: int
    ) -> Dict[str, np.ndarray]:
        """
        Compute reliability curve (predicted vs observed frequency).
        
        Args:
            y_true: True binary outcomes
            y_pred_probs: Predicted probabilities
            n_bins: Number of bins
            
        Returns:
            curve_data: Dictionary with bins, predicted, observed, counts
        """
        # Create bins
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_indices = np.digitize(y_pred_probs, bin_boundaries[:-1]) - 1
        bin_indices = np.clip(bin_indices, 0, n_bins - 1)
        
        predicted = []
        observed = []
        counts = []
        bins = []
        
        for bin_idx in range(n_bins):
            in_bin = bin_indices == bin_idx
            
            if not np.any(in_bin):
                # Empty bin - skip
                continue
            
            bin_lower = bin_boundaries[bin_idx]
            bin_upper = bin_boundaries[bin_idx + 1]
            bins.append((bin_lower + bin_upper) / 2)  # Bin center
            
            # Average predicted probability in bin
            predicted.append(np.mean(y_pred_probs[in_bin]))
            
            # Actual frequency of positive class in bin
            observed.append(np.mean(y_true[in_bin]))
            
            # Number of samples in bin
            counts.append(np.sum(in_bin))
        
        return {
            'bins': np.array(bins),
            'predicted': np.array(predicted),
            'observed': np.array(observed),
            'counts': np.array(counts)
        }
    
    def get_params(self) -> Dict[str, Any]:
        """
        Get calibrator parameters and metadata.
        
        Returns:
            params: Dictionary of parameters
        """
        return {
            'out_of_bounds': self.out_of_bounds,
            'is_fitted': self.is_fitted_,
            'n_samples': self.n_samples_,
            'ece_before': self.ece_before_,
            'ece_after': self.ece_after_,
            'ece_improvement': (
                self.ece_before_ - self.ece_after_
                if self.ece_before_ is not None and self.ece_after_ is not None
                else None
            )
        }
    
    def save(self, path: Path) -> None:
        """
        Save calibrator to disk.
        
        Args:
            path: Path to save calibrator (.pkl or .joblib)
        """
        if not self.is_fitted_:
            raise ValueError("Cannot save unfitted calibrator. Call fit() first.")
        
        calibrator_data = {
            'calibrator': self.calibrator_,
            'params': self.get_params()
        }
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        joblib.dump(calibrator_data, path)
        
        logger.info(
            "isotonic_calibrator_saved",
            extra={
                'path': str(path),
                'file_size_bytes': path.stat().st_size
            }
        )
    
    @classmethod
    def load(cls, path: Path) -> 'IsotonicCalibrator':
        """
        Load calibrator from disk.
        
        Args:
            path: Path to saved calibrator file
            
        Returns:
            calibrator: Loaded isotonic calibrator
        """
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Calibrator file not found: {path}")
        
        calibrator_data = joblib.load(path)
        params = calibrator_data['params']
        
        # Reconstruct calibrator
        calibrator = cls(out_of_bounds=params['out_of_bounds'])
        
        # Restore fitted state
        calibrator.calibrator_ = calibrator_data['calibrator']
        calibrator.is_fitted_ = params['is_fitted']
        calibrator.n_samples_ = params['n_samples']
        calibrator.ece_before_ = params['ece_before']
        calibrator.ece_after_ = params['ece_after']
        
        logger.info(
            "isotonic_calibrator_loaded",
            extra={
                'path': str(path),
                'n_samples': calibrator.n_samples_,
                'ece_before': calibrator.ece_before_,
                'ece_after': calibrator.ece_after_
            }
        )
        
        return calibrator


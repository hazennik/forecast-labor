"""Mixed-frequency forecasting pipeline.

This module connects raw daily/weekly/monthly source data to the existing model
stack: MIDASBridge builds monthly features, DFM extracts stable factors,
XGBoost supplies quantile intervals, and ensemble weights combine point forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Mapping, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from features.midas.bridge import MIDASBridge, RawSource
from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.gbm_quantile.xgb_quantile import XGBoostQuantile
from models_src.midas.bridged_model import MIDASBridgedRegression
from models_src.pipelines.ensemble_pipeline import (
    EnsembleConfig,
    EnsembleMethod,
    optimize_weights,
    validate_predictions_dict,
    weighted_average,
)


@dataclass
class MixedFrequencyPipelineConfig:
    """Configuration for mixed-frequency pipeline behavior."""

    confidence_level: float = 0.9
    min_interval_width: float = 1.0
    residual_scale_floor: float = 1.0

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be in (0, 1)")
        if self.min_interval_width <= 0.0:
            raise ValueError("min_interval_width must be positive")
        if self.residual_scale_floor <= 0.0:
            raise ValueError("residual_scale_floor must be positive")


class MixedFrequencyPipeline:
    """End-to-end mixed-frequency forecasting pipeline.

    Args:
        midas_bridge: Bridge that aligns raw mixed-frequency sources to monthly features.
        dfm: Statsmodels-backed dynamic factor model.
        xgboost: Quantile XGBoost model for nonlinear corrections and intervals.
        ensemble_config: Ensemble configuration controlling model weights.
        midas_model: Optional raw-source MIDAS model. A default bridged model is used
            when omitted.
        pipeline_config: Optional interval and residual configuration.
    """

    def __init__(
        self,
        midas_bridge: MIDASBridge,
        dfm: DynamicFactorModel,
        xgboost: XGBoostQuantile,
        ensemble_config: EnsembleConfig,
        midas_model: Optional[MIDASBridgedRegression] = None,
        pipeline_config: Optional[MixedFrequencyPipelineConfig] = None,
    ) -> None:
        """Initialize the mixed-frequency pipeline."""
        self.midas_bridge = midas_bridge
        self.dfm = dfm
        self.xgboost = xgboost
        self.midas_model = midas_model or MIDASBridgedRegression(
            source_configs=self.midas_bridge.source_configs,
            optimization_method="L-BFGS-B",
            random_state=self.dfm.random_state,
        )
        self.ensemble_config = ensemble_config
        self.pipeline_config = pipeline_config or MixedFrequencyPipelineConfig()

        self.feature_names_: Optional[list[str]] = None
        self.target_index_: Optional[pd.DatetimeIndex] = None
        self.vintage_date_: Optional[str] = None
        self.ensemble_weights_: Optional[Dict[str, float]] = None
        self.residual_scale_: Optional[float] = None
        self.is_fitted = False

    def fit(
        self,
        vintage_date: date,
        raw_sources: Mapping[str, RawSource],
        y_monthly: pd.Series,
    ) -> "MixedFrequencyPipeline":
        """Fit bridge, component models, and ensemble weights."""
        if not isinstance(y_monthly.index, pd.DatetimeIndex):
            raise ValueError("y_monthly must use a DatetimeIndex")
        if y_monthly.empty:
            raise ValueError("y_monthly cannot be empty")

        vintage_str = vintage_date.isoformat()
        target_dates = pd.DatetimeIndex(y_monthly.index)
        features = self.midas_bridge.build_features(raw_sources, target_dates, vintage_str)
        y_aligned = y_monthly.reindex(features.index)
        if y_aligned.isna().any():
            raise ValueError("y_monthly contains missing values after feature alignment")

        logger.info(
            "mixed_frequency_pipeline_fit_started",
            vintage_date=vintage_str,
            n_samples=len(features),
            n_features=features.shape[1],
        )

        self.dfm.fit(features, y_aligned, vintage_str)
        self.xgboost.fit(features, y_aligned, vintage_str)
        self.midas_model.fit(raw_sources, y_aligned, vintage_str)

        training_predictions = self._predict_components(raw_sources, features, target_dates)
        self.ensemble_weights_ = self._resolve_weights(training_predictions, y_aligned)
        combined = weighted_average(training_predictions, self.ensemble_weights_)
        residuals = y_aligned.to_numpy(dtype=float) - combined
        residual_scale = float(np.nanstd(residuals, ddof=0))
        self.residual_scale_ = max(residual_scale, self.pipeline_config.residual_scale_floor)

        self.feature_names_ = list(features.columns)
        self.target_index_ = target_dates
        self.vintage_date_ = vintage_str
        self.is_fitted = True

        logger.info(
            "mixed_frequency_pipeline_fit_completed",
            vintage_date=vintage_str,
            weights=self.ensemble_weights_,
            residual_scale=self.residual_scale_,
        )
        return self

    def predict(
        self,
        vintage_date: date,
        raw_sources: Mapping[str, RawSource],
        target_dates: Optional[pd.DatetimeIndex] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Generate point forecasts and prediction intervals from raw sources."""
        if not self.is_fitted:
            raise ValueError("Pipeline must be fitted before prediction. Call fit() first.")

        prediction_dates = (
            self._default_prediction_dates(vintage_date)
            if target_dates is None
            else pd.DatetimeIndex(target_dates)
        )
        features = self.midas_bridge.build_features(
            raw_sources,
            pd.DatetimeIndex(prediction_dates),
            vintage_date.isoformat(),
        )
        features = features.reindex(columns=self.feature_names_)
        predictions = self._predict_components(
            raw_sources, features, pd.DatetimeIndex(prediction_dates)
        )
        validate_predictions_dict(predictions, self.ensemble_config.model_names)
        point_forecast = weighted_average(predictions, self.ensemble_weights_)
        intervals = self._build_prediction_intervals(features, point_forecast)

        logger.info(
            "mixed_frequency_pipeline_predictions_generated",
            vintage_date=vintage_date.isoformat(),
            n_predictions=len(point_forecast),
        )
        return point_forecast, intervals

    def get_factors(self) -> np.ndarray:
        """Return DFM-extracted factors from training."""
        if not self.is_fitted:
            raise ValueError("Pipeline must be fitted before factors are available")
        return np.asarray(self.dfm.factors_, dtype=float).copy()

    def get_feature_importance(self) -> pd.DataFrame:
        """Return combined feature importance from XGBoost and DFM loadings."""
        if not self.is_fitted:
            raise ValueError("Pipeline must be fitted before feature importance is available")

        frames: list[pd.DataFrame] = []
        try:
            xgb_importance = self.xgboost.get_feature_importance().copy()
            xgb_importance["source_model"] = "xgboost"
            frames.append(xgb_importance)
        except ValueError:
            logger.warning("mixed_frequency_xgboost_importance_unavailable")

        dfm_importance = np.abs(self.dfm.loadings_).sum(axis=1)
        frames.append(
            pd.DataFrame(
                {
                    "feature": self.feature_names_,
                    "importance": dfm_importance,
                    "source_model": "dfm",
                }
            )
        )
        return pd.concat(frames, ignore_index=True, sort=False)

    def _predict_components(
        self,
        raw_sources: Mapping[str, RawSource],
        features: pd.DataFrame,
        target_dates: pd.DatetimeIndex,
    ) -> Dict[str, np.ndarray]:
        """Generate point predictions for every configured component."""
        xgb_predictions = self.xgboost.predict(features)
        point_predictions: Dict[str, np.ndarray] = {
            "dfm": self.dfm.predict(features),
            "midas": self.midas_model.predict(raw_sources, target_dates=target_dates),
            "xgboost": self._median_quantile(xgb_predictions),
        }
        return {
            name: np.asarray(point_predictions[name], dtype=float)
            for name in self.ensemble_config.model_names
        }

    def _resolve_weights(
        self,
        predictions: Dict[str, np.ndarray],
        y_true: pd.Series,
    ) -> Dict[str, float]:
        """Resolve configured, optimized, or equal model weights."""
        validate_predictions_dict(predictions, self.ensemble_config.model_names)
        if self.ensemble_config.optimize_weights:
            return optimize_weights(predictions, y_true.to_numpy(dtype=float))
        if self.ensemble_config.method == EnsembleMethod.WEIGHTED_AVERAGE:
            if self.ensemble_config.weights is None:
                raise ValueError("Weighted ensemble requires configured weights or optimization")
            return self.ensemble_config.weights
        weight = 1.0 / len(self.ensemble_config.model_names)
        return {name: weight for name in self.ensemble_config.model_names}

    def _build_prediction_intervals(
        self,
        features: pd.DataFrame,
        point_forecast: np.ndarray,
    ) -> np.ndarray:
        """Build intervals from XGBoost quantiles with a ragged-edge residual fallback."""
        xgb_predictions = self.xgboost.predict(features)
        try:
            lower, upper = self.xgboost.get_prediction_intervals(
                xgb_predictions,
                confidence_level=self.pipeline_config.confidence_level,
            )
        except ValueError:
            half_width = self._fallback_half_width(features)
            lower = point_forecast - half_width
            upper = point_forecast + half_width

        half_width = np.maximum(
            (np.asarray(upper, dtype=float) - np.asarray(lower, dtype=float)) / 2.0,
            self._fallback_half_width(features),
        )
        center = np.asarray(point_forecast, dtype=float)
        return np.column_stack([center - half_width, center + half_width])

    def _fallback_half_width(self, features: pd.DataFrame) -> np.ndarray:
        """Estimate interval half-width from residuals and latest availability."""
        residual_scale = self.residual_scale_ or self.pipeline_config.residual_scale_floor
        availability = self.midas_bridge.get_availability()
        recency_columns = [col for col in availability.columns if col.endswith("_recency_days")]
        if recency_columns:
            recency = availability[recency_columns].reindex(features.index).mean(axis=1).fillna(0.0)
            recency_multiplier = 1.0 + np.clip(recency.to_numpy(dtype=float), 0.0, 31.0) / 31.0
        else:
            recency_multiplier = np.ones(len(features), dtype=float)
        min_half_width = self.pipeline_config.min_interval_width / 2.0
        return np.maximum(residual_scale * recency_multiplier, min_half_width)

    def _median_quantile(self, predictions: Dict[float, np.ndarray]) -> np.ndarray:
        """Extract the median quantile, or the closest available quantile."""
        if 0.5 in predictions:
            return np.asarray(predictions[0.5], dtype=float)
        closest = min(predictions.keys(), key=lambda quantile: abs(quantile - 0.5))
        return np.asarray(predictions[closest], dtype=float)

    def _default_prediction_dates(self, vintage_date: date) -> pd.DatetimeIndex:
        """Default to the vintage month when explicit prediction dates are omitted."""
        return pd.DatetimeIndex([pd.Timestamp(vintage_date).to_period("M").to_timestamp()])

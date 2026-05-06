"""
MIDAS bridge layer for mixed-frequency feature construction.

The bridge connects raw daily, weekly, and monthly ETL outputs to model-ready
monthly features. It reuses MIDASLagConstructor for high-frequency sources and
adds deterministic missing-value handling for ragged-edge nowcasting.
"""

from typing import Any, Dict, Mapping, Optional, Union

import numpy as np
import pandas as pd
from loguru import logger

from features.midas.lag_constructor import MIDASLagConstructor, align_series_to_dates
from features.midas.source_config import DEFAULT_SOURCE_CONFIGS, SourceConfig


RawSource = Union[pd.DataFrame, pd.Series]


class MIDASBridge:
    """
    Build monthly model features from raw mixed-frequency source data.

    Args:
        source_configs: Mapping of source names to extraction/alignment configs.
        target_freq: Low-frequency target. Currently monthly ("M") is supported.
        almon_poly_degree: Degree used by high-frequency lag weighting.
        apply_almon_weights: Whether to weight high-frequency lag columns.
        fill_missing: Whether to fill ragged-edge missing values deterministically.

    Example:
        >>> bridge = MIDASBridge()
        >>> features = bridge.build_features(raw_sources, monthly_dates)
    """

    def __init__(
        self,
        source_configs: Optional[Mapping[str, SourceConfig]] = None,
        target_freq: str = "M",
        almon_poly_degree: int = 2,
        apply_almon_weights: bool = True,
        fill_missing: bool = True,
    ) -> None:
        """Initialize the MIDAS bridge."""
        if target_freq != "M":
            raise ValueError(f"target_freq must be 'M', got {target_freq}")
        if almon_poly_degree < 0:
            raise ValueError("almon_poly_degree must be non-negative")

        self.source_configs = dict(source_configs or DEFAULT_SOURCE_CONFIGS)
        self.target_freq = target_freq
        self.almon_poly_degree = almon_poly_degree
        self.apply_almon_weights = apply_almon_weights
        self.fill_missing = fill_missing
        self.feature_names_: Optional[list[str]] = None
        self.availability_: Optional[pd.DataFrame] = None

        logger.info(
            "midas_bridge_initialized",
            source_count=len(self.source_configs),
            target_freq=target_freq,
            almon_poly_degree=almon_poly_degree,
        )

    def build_features(
        self,
        raw_sources: Mapping[str, RawSource],
        target_dates: pd.DatetimeIndex,
        vintage_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Build monthly features from raw source data.

        Args:
            raw_sources: Mapping of source name to DataFrame or Series.
            target_dates: Monthly dates to align features to.
            vintage_date: Optional vintage date for logging and reproducibility metadata.

        Returns:
            Numeric DataFrame indexed by target_dates, with one set of columns per source.
        """
        if not isinstance(target_dates, pd.DatetimeIndex):
            raise ValueError("target_dates must be a DatetimeIndex")
        if len(target_dates) == 0:
            raise ValueError("target_dates cannot be empty")

        feature_frames: list[pd.DataFrame] = []
        availability_frames: list[pd.DataFrame] = []

        for source_name, config in self.source_configs.items():
            if source_name not in raw_sources:
                raise ValueError(f"Missing raw source: {source_name}")

            series = self._extract_series(raw_sources[source_name], config)
            series = self._apply_vintage_cutoff(series, vintage_date)
            source_features = self._build_source_features(series, config, target_dates)
            source_availability = self._build_availability(series, config, target_dates)

            feature_frames.append(source_features)
            availability_frames.append(source_availability)

        features = pd.concat(feature_frames, axis=1)
        features = features.sort_index(axis=1)

        if self.fill_missing:
            features = self._fill_feature_gaps(features)

        self.feature_names_ = list(features.columns)
        self.availability_ = pd.concat(availability_frames, axis=1).sort_index(axis=1)

        logger.info(
            "midas_bridge_features_built",
            vintage_date=vintage_date,
            output_shape=features.shape,
            missing_values=int(features.isna().sum().sum()),
        )

        return features

    def _extract_series(self, raw_source: RawSource, config: SourceConfig) -> pd.Series:
        """Extract a typed, sorted time series from raw source input."""
        if isinstance(raw_source, pd.Series):
            series = raw_source.copy()
            if not isinstance(series.index, pd.DatetimeIndex):
                raise ValueError(f"{config.source_name} series must use a DatetimeIndex")
        elif isinstance(raw_source, pd.DataFrame):
            missing_columns = {config.date_column, config.value_column} - set(raw_source.columns)
            if missing_columns:
                raise ValueError(
                    f"{config.source_name} missing required columns: {sorted(missing_columns)}"
                )
            frame = raw_source[[config.date_column, config.value_column]].copy()
            frame[config.date_column] = pd.to_datetime(frame[config.date_column])
            series = pd.Series(
                frame[config.value_column].to_numpy(),
                index=pd.DatetimeIndex(frame[config.date_column]),
                name=config.value_column,
            )
        else:
            raise TypeError(f"{config.source_name} must be a DataFrame or Series")

        series = pd.to_numeric(series, errors="coerce").sort_index()
        series = series[~series.index.duplicated(keep="last")]

        if series.empty:
            raise ValueError(f"{config.source_name} contains no observations")

        return series

    def _apply_vintage_cutoff(
        self, series: pd.Series, vintage_date: Optional[str]
    ) -> pd.Series:
        """Drop observations after the vintage date, when provided."""
        if vintage_date is None:
            return series

        cutoff = pd.Timestamp(vintage_date)
        return series[series.index <= cutoff]

    def _build_source_features(
        self,
        series: pd.Series,
        config: SourceConfig,
        target_dates: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """Build model feature columns for one source."""
        if config.frequency == "M":
            aligned = align_series_to_dates(series, target_dates, method=config.aggregation)
            return pd.DataFrame(
                {f"{config.source_name}_{config.value_column}": aligned},
                index=target_dates,
            )

        constructor = MIDASLagConstructor(
            source_freq=config.frequency,
            target_freq=self.target_freq,
            n_lags=config.n_lags,
            almon_poly_degree=self.almon_poly_degree,
            apply_weights=self.apply_almon_weights,
            column_prefix=f"{config.source_name}_{config.value_column}",
        )
        return constructor.construct_lags(series, target_dates)

    def _build_availability(
        self,
        series: pd.Series,
        config: SourceConfig,
        target_dates: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """Build numeric availability metadata for ragged-edge diagnostics."""
        counts = []
        recency_days = []

        for target_date in target_dates:
            available = series[series.index <= target_date]
            counts.append(min(len(available), config.n_lags))
            if len(available) == 0:
                recency_days.append(np.nan)
            else:
                recency_days.append((target_date - available.index[-1]).days)

        return pd.DataFrame(
            {
                f"{config.source_name}_available_observations": counts,
                f"{config.source_name}_recency_days": recency_days,
            },
            index=target_dates,
        )

    def _fill_feature_gaps(self, features: pd.DataFrame) -> pd.DataFrame:
        """Fill ragged-edge feature gaps without introducing randomness."""
        filled = features.ffill().bfill()
        medians = filled.median(axis=0, numeric_only=True)
        filled = filled.fillna(medians).fillna(0.0)
        return filled.astype(float)

    def get_availability(self) -> pd.DataFrame:
        """
        Return availability metadata from the latest build_features call.

        Raises:
            ValueError: If build_features has not been called yet.
        """
        if self.availability_ is None:
            raise ValueError("Availability is not available before build_features()")
        return self.availability_.copy()

    def convert_reconstructed_state(self, state: Any) -> Dict[str, pd.Series]:
        """
        Convert a VintageHarness ReconstructedState to raw_sources format.

        Args:
            state: ReconstructedState-like object with a ``data`` mapping.

        Returns:
            Mapping of configured source name to date-indexed numeric Series.
        """
        raw_sources: Dict[str, pd.Series] = {}
        for source_name, source_frame in state.data.items():
            if source_name not in self.source_configs:
                logger.warning("midas_bridge_state_source_skipped", source=source_name)
                continue

            config = self.source_configs[source_name]
            if not isinstance(source_frame, pd.DataFrame):
                logger.warning("midas_bridge_state_source_not_dataframe", source=source_name)
                continue

            required_columns = {config.date_column, config.value_column}
            missing_columns = required_columns - set(source_frame.columns)
            if missing_columns:
                logger.warning(
                    "midas_bridge_state_source_missing_columns",
                    source=source_name,
                    missing_columns=sorted(missing_columns),
                )
                continue

            raw_sources[source_name] = self._extract_series(source_frame, config)

        return raw_sources

    def build_features_from_harness_state(
        self,
        state: Any,
        target_dates: pd.DatetimeIndex,
    ) -> pd.DataFrame:
        """
        Build features directly from a VintageHarness ReconstructedState.

        Args:
            state: ReconstructedState-like object with ``as_of_date`` and ``data``.
            target_dates: Monthly dates to produce features for.

        Returns:
            Monthly-aligned feature DataFrame.
        """
        raw_sources = self.convert_reconstructed_state(state)
        return self.build_features(
            raw_sources=raw_sources,
            target_dates=target_dates,
            vintage_date=state.as_of_date.isoformat(),
        )

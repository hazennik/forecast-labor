"""Integration tests for the mixed-frequency DFM/MIDAS pipeline."""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backtests.vintage_harness.harness import ReconstructedState
from features.midas import MIDASBridge, SourceConfig
from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.gbm_quantile.xgb_quantile import XGBoostQuantile
from models_src.pipelines.ensemble_pipeline import EnsembleConfig, EnsembleMethod
from models_src.pipelines.mixed_frequency_pipeline import (
    MixedFrequencyPipeline,
    MixedFrequencyPipelineConfig,
)


@pytest.fixture
def source_configs() -> dict[str, SourceConfig]:
    """Small mixed-frequency source set for fast integration tests."""
    return {
        "treasury": SourceConfig(
            source_name="treasury",
            frequency="D",
            date_column="date",
            value_column="daily_withholding",
            n_lags=5,
            aggregation="sum",
        ),
        "claims": SourceConfig(
            source_name="claims",
            frequency="W",
            date_column="report_date",
            value_column="initial_claims",
            n_lags=3,
        ),
        "ces": SourceConfig(
            source_name="ces",
            frequency="M",
            date_column="date",
            value_column="all_employees",
            n_lags=1,
        ),
    }


@pytest.fixture
def target_dates() -> pd.DatetimeIndex:
    """Monthly target dates for pipeline tests."""
    return pd.date_range("2023-01-01", periods=18, freq="MS")


@pytest.fixture
def raw_sources(target_dates: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """Create deterministic raw daily, weekly, and monthly inputs."""
    daily_dates = pd.date_range("2022-09-01", "2024-08-05", freq="D")
    weekly_dates = pd.date_range("2022-09-04", "2024-08-04", freq="W")
    monthly_dates = pd.date_range("2022-09-01", "2024-08-01", freq="MS")

    daily_signal = (
        100.0
        + 0.04 * np.arange(len(daily_dates))
        + np.sin(np.arange(len(daily_dates)) / 12.0)
    )
    weekly_signal = 220_000.0 - 15.0 * np.arange(len(weekly_dates)) + 100.0 * np.cos(
        np.arange(len(weekly_dates)) / 5.0
    )
    monthly_signal = 150_000.0 + 80.0 * np.arange(len(monthly_dates)) + 10.0 * np.sin(
        np.arange(len(monthly_dates)) / 3.0
    )

    return {
        "treasury": pd.DataFrame(
            {"date": daily_dates, "daily_withholding": daily_signal}
        ),
        "claims": pd.DataFrame(
            {"report_date": weekly_dates, "initial_claims": weekly_signal}
        ),
        "ces": pd.DataFrame(
            {"date": monthly_dates, "all_employees": monthly_signal}
        ),
    }


@pytest.fixture
def y_monthly(target_dates: pd.DatetimeIndex) -> pd.Series:
    """Synthetic monthly NFP target linked to the source signals."""
    trend = 150_000.0 + 95.0 * np.arange(len(target_dates))
    cycle = 30.0 * np.sin(np.arange(len(target_dates)) / 2.0)
    return pd.Series(trend + cycle, index=target_dates, name="nfp")


@pytest.fixture
def pipeline(source_configs: dict[str, SourceConfig]) -> MixedFrequencyPipeline:
    """Create a small mixed-frequency pipeline."""
    return MixedFrequencyPipeline(
        midas_bridge=MIDASBridge(source_configs=source_configs),
        dfm=DynamicFactorModel(n_factors=2, max_iter=20, random_state=42),
        xgboost=XGBoostQuantile(
            quantiles=[0.5],
            n_estimators=5,
            max_depth=2,
            random_state=42,
        ),
        ensemble_config=EnsembleConfig(
            method=EnsembleMethod.SIMPLE_AVERAGE,
            model_names=["dfm", "midas", "xgboost"],
        ),
        pipeline_config=MixedFrequencyPipelineConfig(
            confidence_level=0.9,
            min_interval_width=1.0,
            residual_scale_floor=5.0,
        ),
    )


class TestMixedFrequencyPipeline:
    """Validate R5 pipeline integration behavior."""

    def test_pipeline_builds_from_raw_data(
        self,
        pipeline: MixedFrequencyPipeline,
        raw_sources: dict[str, pd.DataFrame],
        y_monthly: pd.Series,
    ) -> None:
        """Pipeline should fit all component models from raw mixed-frequency data."""
        result = pipeline.fit(date(2024, 8, 5), raw_sources, y_monthly)

        assert result is pipeline
        assert pipeline.is_fitted
        assert pipeline.feature_names_ is not None
        assert pipeline.ensemble_weights_ == {
            "dfm": pytest.approx(1 / 3),
            "midas": pytest.approx(1 / 3),
            "xgboost": pytest.approx(1 / 3),
        }

    def test_pipeline_produces_monthly_predictions(
        self,
        pipeline: MixedFrequencyPipeline,
        raw_sources: dict[str, pd.DataFrame],
        y_monthly: pd.Series,
    ) -> None:
        """Prediction should return one point forecast and interval per monthly date."""
        pipeline.fit(date(2024, 8, 5), raw_sources, y_monthly)

        predictions, intervals = pipeline.predict(
            date(2024, 8, 5),
            raw_sources,
            target_dates=pd.DatetimeIndex(y_monthly.index[-3:]),
        )

        assert predictions.shape == (3,)
        assert intervals.shape == (3, 2)
        assert np.isfinite(predictions).all()
        assert np.all(intervals[:, 0] < intervals[:, 1])

    def test_pipeline_handles_ragged_edge(
        self,
        pipeline: MixedFrequencyPipeline,
        raw_sources: dict[str, pd.DataFrame],
        y_monthly: pd.Series,
    ) -> None:
        """Missing recent high-frequency observations should widen intervals, not fail."""
        pipeline.fit(date(2024, 8, 5), raw_sources, y_monthly)
        ragged_sources = {
            **raw_sources,
            "treasury": raw_sources["treasury"].iloc[:-10],
            "claims": raw_sources["claims"].iloc[:-2],
        }

        predictions, intervals = pipeline.predict(
            date(2024, 8, 5),
            ragged_sources,
            target_dates=pd.DatetimeIndex([pd.Timestamp("2024-08-01")]),
        )

        assert predictions.shape == (1,)
        assert intervals.shape == (1, 2)
        assert np.isfinite(intervals).all()

    def test_pipeline_sequential_updates_tighten_uncertainty(
        self,
        pipeline: MixedFrequencyPipeline,
        raw_sources: dict[str, pd.DataFrame],
        y_monthly: pd.Series,
    ) -> None:
        """Later intra-month updates with fresher data should produce tighter intervals."""
        pipeline.fit(date(2024, 8, 5), raw_sources, y_monthly)
        target_date = pd.DatetimeIndex([pd.Timestamp("2024-08-01")])
        t48_sources = {**raw_sources, "treasury": raw_sources["treasury"].iloc[:-4]}
        t24_sources = {**raw_sources, "treasury": raw_sources["treasury"].iloc[:-3]}

        _, intervals_t48 = pipeline.predict(
            date(2024, 8, 3), t48_sources, target_dates=target_date
        )
        _, intervals_t24 = pipeline.predict(
            date(2024, 8, 4), t24_sources, target_dates=target_date
        )

        width_t48 = intervals_t48[0, 1] - intervals_t48[0, 0]
        width_t24 = intervals_t24[0, 1] - intervals_t24[0, 0]
        assert width_t24 <= width_t48

    def test_pipeline_exposes_factors_and_feature_importance(
        self,
        pipeline: MixedFrequencyPipeline,
        raw_sources: dict[str, pd.DataFrame],
        y_monthly: pd.Series,
    ) -> None:
        """Pipeline diagnostics should expose DFM factors and combined importance."""
        pipeline.fit(date(2024, 8, 5), raw_sources, y_monthly)

        factors = pipeline.get_factors()
        importance = pipeline.get_feature_importance()

        assert factors.shape == (len(y_monthly), 2)
        assert {"feature", "importance", "source_model"}.issubset(importance.columns)
        assert {"dfm", "xgboost"}.issubset(set(importance["source_model"]))

    def test_optimized_pipeline_can_assign_dfm_nonzero_weight(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        y_monthly: pd.Series,
    ) -> None:
        """Optimized ensemble should give DFM weight when its factor head adds signal."""
        pipeline = MixedFrequencyPipeline(
            midas_bridge=MIDASBridge(source_configs=source_configs),
            dfm=DynamicFactorModel(
                n_factors=2,
                max_iter=20,
                random_state=42,
                ridge_alphas=(0.01, 0.1, 1.0, 10.0),
            ),
            xgboost=XGBoostQuantile(
                quantiles=[0.5],
                n_estimators=1,
                max_depth=1,
                random_state=42,
            ),
            ensemble_config=EnsembleConfig(
                method=EnsembleMethod.WEIGHTED_AVERAGE,
                model_names=["dfm", "xgboost"],
                optimize_weights=True,
            ),
            pipeline_config=MixedFrequencyPipelineConfig(
                confidence_level=0.9,
                min_interval_width=1.0,
                residual_scale_floor=5.0,
            ),
        )

        pipeline.fit(date(2024, 8, 5), raw_sources, y_monthly)

        assert pipeline.ensemble_weights_ is not None
        assert sum(pipeline.ensemble_weights_.values()) == pytest.approx(1.0)
        assert pipeline.ensemble_weights_["dfm"] > 0.05


class TestVintageHarnessBridgeCompatibility:
    """Validate MIDASBridge compatibility with VintageHarness outputs."""

    def test_bridge_with_reconstructed_state(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """MIDASBridge should build features from a ReconstructedState object."""
        state = ReconstructedState(
            as_of_date=date(2024, 8, 5),
            data=raw_sources,
            vintage_dates={source: date(2024, 8, 5) for source in raw_sources},
            sources_requested=list(raw_sources),
            sources_available=list(raw_sources),
        )
        bridge = MIDASBridge(source_configs=source_configs)

        features = bridge.build_features_from_harness_state(state, target_dates)

        assert features.shape[0] == len(target_dates)
        assert not features.isna().any().any()

    def test_bridge_handles_partial_vintage_availability(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """Bridge conversion should skip unavailable state sources gracefully."""
        partial_configs = {"treasury": source_configs["treasury"]}
        state = ReconstructedState(
            as_of_date=date(2024, 8, 5),
            data={"treasury": raw_sources["treasury"], "unknown": pd.DataFrame({"date": []})},
            vintage_dates={"treasury": date(2024, 8, 5)},
            sources_requested=["treasury", "unknown"],
            sources_available=["treasury"],
        )
        bridge = MIDASBridge(source_configs=partial_configs)

        raw = bridge.convert_reconstructed_state(state)
        features = bridge.build_features_from_harness_state(state, target_dates)

        assert list(raw) == ["treasury"]
        assert features.shape == (len(target_dates), partial_configs["treasury"].n_lags)

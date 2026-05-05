"""Tests for the MIDAS mixed-frequency bridge layer."""

import numpy as np
import pandas as pd
import pytest

from features.midas import MIDASBridge, SourceConfig


@pytest.fixture
def target_dates() -> pd.DatetimeIndex:
    """Monthly target dates for bridge tests."""
    return pd.date_range("2024-01-01", periods=6, freq="MS")


@pytest.fixture
def source_configs() -> dict[str, SourceConfig]:
    """Small source configs to keep tests fast and interpretable."""
    return {
        "treasury": SourceConfig(
            source_name="treasury",
            frequency="D",
            date_column="date",
            value_column="daily_withholding",
            n_lags=5,
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
def raw_sources() -> dict[str, pd.DataFrame]:
    """Raw mixed-frequency inputs shaped like ETL outputs."""
    daily_dates = pd.date_range("2023-12-01", periods=170, freq="D")
    weekly_dates = pd.date_range("2023-12-03", periods=26, freq="W")
    monthly_dates = pd.date_range("2023-12-01", periods=7, freq="MS")

    return {
        "treasury": pd.DataFrame(
            {
                "date": daily_dates,
                "daily_withholding": np.linspace(100.0, 200.0, len(daily_dates)),
            }
        ),
        "claims": pd.DataFrame(
            {
                "report_date": weekly_dates,
                "initial_claims": np.linspace(220_000.0, 210_000.0, len(weekly_dates)),
            }
        ),
        "ces": pd.DataFrame(
            {
                "date": monthly_dates,
                "all_employees": np.linspace(150_000.0, 151_200.0, len(monthly_dates)),
            }
        ),
    }


class TestSourceConfig:
    """Validate source configuration invariants."""

    def test_monthly_source_must_use_one_lag(self) -> None:
        """Monthly pass-through sources should not masquerade as high-frequency lags."""
        with pytest.raises(ValueError, match="monthly source configs"):
            SourceConfig(
                source_name="bad_monthly",
                frequency="M",
                date_column="date",
                value_column="value",
                n_lags=2,
            )


class TestMIDASBridge:
    """Test bridge behavior from raw sources to model-ready features."""

    def test_bridge_accepts_raw_high_frequency_data(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """Bridge should turn raw daily/weekly/monthly sources into monthly features."""
        bridge = MIDASBridge(source_configs=source_configs)

        features = bridge.build_features(raw_sources, target_dates)

        assert features.shape == (6, 9)
        assert features.index.equals(target_dates)
        assert "ces_all_employees" in features.columns
        assert any(col.startswith("treasury_daily_withholding_lag_") for col in features)
        assert any(col.startswith("claims_initial_claims_lag_") for col in features)

    def test_bridge_outputs_numeric_dfm_compatible_features(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """DFM inputs need numeric monthly data with no ragged-edge NaNs."""
        bridge = MIDASBridge(source_configs=source_configs)

        features = bridge.build_features(raw_sources, target_dates)

        assert all(np.issubdtype(dtype, np.number) for dtype in features.dtypes)
        assert not features.isna().any().any()

    def test_bridge_applies_almon_weighting(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """Weighted and unweighted bridges should produce different lag magnitudes."""
        weighted = MIDASBridge(source_configs=source_configs, apply_almon_weights=True)
        unweighted = MIDASBridge(source_configs=source_configs, apply_almon_weights=False)

        weighted_features = weighted.build_features(raw_sources, target_dates)
        unweighted_features = unweighted.build_features(raw_sources, target_dates)

        treasury_cols = [
            col for col in weighted_features.columns if col.startswith("treasury_")
        ]
        assert not np.allclose(
            weighted_features[treasury_cols].to_numpy(),
            unweighted_features[treasury_cols].to_numpy(),
        )

    def test_bridge_marks_data_availability(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """Availability metadata should expose ragged-edge context separately."""
        bridge = MIDASBridge(source_configs=source_configs)

        bridge.build_features(raw_sources, target_dates)
        availability = bridge.get_availability()

        assert availability.shape == (6, 6)
        assert "treasury_available_observations" in availability.columns
        assert "claims_recency_days" in availability.columns
        assert (availability["treasury_available_observations"] <= 5).all()

    def test_bridge_handles_missing_recent_daily_data(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """Ragged-edge source data should not prevent feature construction."""
        raw_sources["treasury"] = raw_sources["treasury"].iloc[:-20]
        bridge = MIDASBridge(source_configs=source_configs)

        features = bridge.build_features(raw_sources, target_dates)
        availability = bridge.get_availability()

        assert not features.isna().any().any()
        assert availability["treasury_recency_days"].iloc[-1] > 0

    def test_bridge_deterministic_output(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """Same inputs should produce byte-for-byte equivalent features."""
        bridge = MIDASBridge(source_configs=source_configs)

        first = bridge.build_features(raw_sources, target_dates, vintage_date="2024-06-01")
        second = bridge.build_features(raw_sources, target_dates, vintage_date="2024-06-01")

        pd.testing.assert_frame_equal(first, second)

    def test_missing_source_raises_clear_error(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target_dates: pd.DatetimeIndex,
    ) -> None:
        """Missing source data should fail early with a useful message."""
        raw_sources.pop("claims")
        bridge = MIDASBridge(source_configs=source_configs)

        with pytest.raises(ValueError, match="Missing raw source: claims"):
            bridge.build_features(raw_sources, target_dates)

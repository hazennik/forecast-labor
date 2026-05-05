"""Tests for MIDASBridgedRegression."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from features.midas import SourceConfig
from models_src.midas import MIDASBridgedRegression


@pytest.fixture
def source_configs() -> dict[str, SourceConfig]:
    """Small source configs for fast bridged model tests."""
    return {
        "treasury": SourceConfig(
            source_name="treasury",
            frequency="D",
            date_column="date",
            value_column="daily_withholding",
            n_lags=4,
        ),
        "claims": SourceConfig(
            source_name="claims",
            frequency="W",
            date_column="report_date",
            value_column="initial_claims",
            n_lags=2,
        ),
    }


@pytest.fixture
def raw_sources() -> dict[str, pd.DataFrame]:
    """Create deterministic daily and weekly raw data."""
    daily_dates = pd.date_range("2023-01-01", periods=420, freq="D")
    weekly_dates = pd.date_range("2023-01-01", periods=70, freq="W")

    return {
        "treasury": pd.DataFrame(
            {
                "date": daily_dates,
                "daily_withholding": 100.0 + np.sin(np.arange(len(daily_dates)) / 10.0),
            }
        ),
        "claims": pd.DataFrame(
            {
                "report_date": weekly_dates,
                "initial_claims": 220_000.0 + np.cos(np.arange(len(weekly_dates)) / 5.0),
            }
        ),
    }


@pytest.fixture
def target() -> pd.Series:
    """Monthly target with a deterministic trend."""
    dates = pd.date_range("2023-03-01", periods=10, freq="MS")
    values = 150_000.0 + np.arange(len(dates)) * 100.0
    return pd.Series(values, index=dates, name="nfp")


class TestMIDASBridgedRegression:
    """Validate raw-source MIDAS regression workflow."""

    def test_fit_builds_bridge_and_underlying_model(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target: pd.Series,
    ) -> None:
        """Fitting should bridge raw sources before training MIDASRegression."""
        model = MIDASBridgedRegression(
            source_configs=source_configs,
            optimization_method="L-BFGS-B",
            random_state=42,
        )

        result = model.fit(raw_sources, target, vintage_date="2024-01-15")

        assert result is model
        assert model.bridge_ is not None
        assert model.model_ is not None
        assert model.feature_names_ is not None
        assert len(model.feature_names_) == 6
        assert model.vintage_date_ == "2024-01-15"

    def test_predict_from_raw_sources(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target: pd.Series,
    ) -> None:
        """Prediction should accept the same raw source shape used during fit."""
        model = MIDASBridgedRegression(
            source_configs=source_configs,
            optimization_method="L-BFGS-B",
            random_state=42,
        )
        model.fit(raw_sources, target, vintage_date="2024-01-15")

        predictions = model.predict(raw_sources, target_dates=pd.DatetimeIndex(target.index))

        assert predictions.shape == (len(target),)
        assert np.isfinite(predictions).all()

    def test_predict_requires_fit(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target: pd.Series,
    ) -> None:
        """Unfitted bridged models should fail before prediction."""
        model = MIDASBridgedRegression(source_configs=source_configs)

        with pytest.raises(ValueError, match="Model must be fitted"):
            model.predict(raw_sources, target_dates=pd.DatetimeIndex(target.index))

    def test_predict_requires_target_dates(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target: pd.Series,
    ) -> None:
        """Raw-source prediction must state the desired monthly forecast dates."""
        model = MIDASBridgedRegression(
            source_configs=source_configs,
            optimization_method="L-BFGS-B",
        )
        model.fit(raw_sources, target, vintage_date="2024-01-15")

        with pytest.raises(ValueError, match="target_dates must be provided"):
            model.predict(raw_sources)

    def test_save_and_load_preserves_predictions(
        self,
        source_configs: dict[str, SourceConfig],
        raw_sources: dict[str, pd.DataFrame],
        target: pd.Series,
    ) -> None:
        """Saved bridged models should reproduce predictions after loading."""
        model = MIDASBridgedRegression(
            source_configs=source_configs,
            optimization_method="L-BFGS-B",
            random_state=42,
        )
        model.fit(raw_sources, target, vintage_date="2024-01-15")
        expected = model.predict(raw_sources, target_dates=pd.DatetimeIndex(target.index))

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "midas_bridged.joblib"
            model.save(path)
            loaded = MIDASBridgedRegression.load(path)

        actual = loaded.predict(raw_sources, target_dates=pd.DatetimeIndex(target.index))
        np.testing.assert_allclose(actual, expected)

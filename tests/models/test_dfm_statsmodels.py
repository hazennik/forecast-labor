"""
Tests for the statsmodels-backed Dynamic Factor Model implementation.

These tests define the R4 contract: preserve the public DFM interface while
using a stable statsmodels DynamicFactor fit and learned-loading projection for
out-of-sample predictions.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.utils.base_model import BaseForecaster


@pytest.fixture
def factor_structured_data() -> tuple[pd.DataFrame, pd.Series]:
    """Create monthly data with a clear latent factor structure."""
    rng = np.random.default_rng(42)
    n_obs = 96
    dates = pd.date_range("2017-01-01", periods=n_obs, freq="MS")

    factor_1 = np.sin(np.linspace(0, 8 * np.pi, n_obs))
    factor_2 = np.linspace(-1.0, 1.0, n_obs)
    noise = rng.normal(0.0, 0.05, size=(n_obs, 5))

    X = pd.DataFrame(
        {
            "claims": 250_000 - 12_000 * factor_1 + 5_000 * factor_2 + noise[:, 0] * 1000,
            "withholdings": 5_000 + 220 * factor_1 + 120 * factor_2 + noise[:, 1] * 100,
            "hours": 34.5 + 0.3 * factor_1 - 0.1 * factor_2 + noise[:, 2],
            "openings": 8_000 + 500 * factor_1 + 200 * factor_2 + noise[:, 3] * 100,
            "sentiment": 100 + 6 * factor_1 + 3 * factor_2 + noise[:, 4],
        },
        index=dates,
    )
    y = pd.Series(140 + 35 * factor_1 + 20 * factor_2 + rng.normal(0.0, 3.0, n_obs), index=dates)
    return X, y


def test_inherits_from_base_forecaster() -> None:
    """The statsmodels DFM must preserve the BaseForecaster contract."""
    assert isinstance(DynamicFactorModel(n_factors=2), BaseForecaster)


def test_fit_extracts_factors_and_loadings(
    factor_structured_data: tuple[pd.DataFrame, pd.Series],
) -> None:
    """Fit should populate factor artifacts with stable, finite shapes."""
    X, y = factor_structured_data
    model = DynamicFactorModel(n_factors=2, max_iter=50, random_state=42)

    result = model.fit(X, y, vintage_date="2026-05-05")

    assert result is model
    assert model.is_fitted is True
    assert model.factors_.shape == (len(X), 2)
    assert model.loadings_.shape == (X.shape[1], 2)
    assert model.transition_.shape == (2, 2)
    assert model.explained_variance_ > 0
    assert np.all(np.isfinite(model.factors_))
    assert np.all(np.isfinite(model.loadings_))


def test_predict_on_new_data_uses_learned_loading_projection(
    factor_structured_data: tuple[pd.DataFrame, pd.Series],
) -> None:
    """Out-of-sample prediction should work through learned loadings."""
    X, y = factor_structured_data
    model = DynamicFactorModel(n_factors=2, max_iter=50, random_state=42)
    model.fit(X.iloc[:-12], y.iloc[:-12], vintage_date="2026-05-05")

    X_new = X.iloc[-12:]
    predictions = model.predict(X_new)
    projected_factors = model._extract_factors(model._preprocess_features(X_new, fit=False))

    assert predictions.shape == (12,)
    assert projected_factors.shape == (12, 2)
    assert np.all(np.isfinite(predictions))
    assert np.all(np.isfinite(projected_factors))


def test_supervised_head_uses_bridge_features_when_predictive() -> None:
    """Regularized DFM nowcast head should learn predictive bridge-feature signal."""
    rng = np.random.default_rng(123)
    n_obs = 96
    dates = pd.date_range("2017-01-01", periods=n_obs, freq="MS")
    common_factor = np.sin(np.linspace(0, 6 * np.pi, n_obs))
    direct_signal = np.linspace(-1.0, 1.0, n_obs)

    X = pd.DataFrame(
        {
            "common_1": 100.0 + common_factor + rng.normal(0.0, 0.05, n_obs),
            "common_2": 50.0 - 0.8 * common_factor + rng.normal(0.0, 0.05, n_obs),
            "bridge_signal": 20.0 + direct_signal + rng.normal(0.0, 0.02, n_obs),
        },
        index=dates,
    )
    y = pd.Series(
        75.0 + 20.0 * direct_signal + 2.0 * common_factor + rng.normal(0.0, 0.5, n_obs),
        index=dates,
    )
    train_X, test_X = X.iloc[:-18], X.iloc[-18:]
    train_y, test_y = y.iloc[:-18], y.iloc[-18:]

    factor_only = DynamicFactorModel(
        n_factors=1,
        max_iter=50,
        random_state=42,
        include_direct_features=False,
    )
    supervised = DynamicFactorModel(
        n_factors=1,
        max_iter=50,
        random_state=42,
        include_direct_features=True,
        ridge_alphas=(0.01, 0.1, 1.0, 10.0),
    )

    factor_only.fit(train_X, train_y, vintage_date="2026-05-05")
    supervised.fit(train_X, train_y, vintage_date="2026-05-05")

    factor_mse = np.mean((factor_only.predict(test_X) - test_y.to_numpy()) ** 2)
    supervised_mse = np.mean((supervised.predict(test_X) - test_y.to_numpy()) ** 2)

    assert supervised.prediction_coef_.shape[0] == supervised.n_factors + train_X.shape[1]
    assert supervised.selected_ridge_alpha_ in supervised.ridge_alphas
    assert supervised_mse < factor_mse * 0.75


def test_handles_nfp_scale_and_covid_shock() -> None:
    """Large labor-market scale values and shocks must not explode predictions."""
    rng = np.random.default_rng(7)
    n_obs = 84
    dates = pd.date_range("2018-01-01", periods=n_obs, freq="MS")
    shock = np.zeros(n_obs)
    shock[26:30] = [-1200, -800, 500, 300]

    X = pd.DataFrame(
        {
            "nfp_level": 150_000 + np.cumsum(rng.normal(120, 80, n_obs)) + shock,
            "private_level": 125_000 + np.cumsum(rng.normal(100, 70, n_obs)) + shock * 0.8,
            "claims": 220_000 + rng.normal(0, 15_000, n_obs) - shock * 120,
            "withholdings": 6_000 + rng.normal(0, 350, n_obs) + shock * 0.5,
        },
        index=dates,
    )
    y = pd.Series(150 + rng.normal(0, 50, n_obs) + shock * 0.1, index=dates)

    model = DynamicFactorModel(n_factors=2, max_iter=50, random_state=42)
    model.fit(X, y, vintage_date="2026-05-05")
    predictions = model.predict(X.iloc[-12:])

    assert np.all(np.isfinite(predictions))
    assert np.max(np.abs(predictions)) < 1_000_000


def test_predictions_differ_from_ols_on_raw_features(
    factor_structured_data: tuple[pd.DataFrame, pd.Series],
) -> None:
    """DFM should not collapse to a direct OLS regression on raw features."""
    X, y = factor_structured_data
    train_X = X.iloc[:-12]
    train_y = y.iloc[:-12]
    test_X = X.iloc[-12:]

    model = DynamicFactorModel(n_factors=2, max_iter=50, random_state=42)
    model.fit(train_X, train_y, vintage_date="2026-05-05")
    dfm_predictions = model.predict(test_X)

    standardized_train = (train_X - train_X.mean()) / train_X.std(ddof=0).replace(0, 1)
    standardized_test = (test_X - train_X.mean()) / train_X.std(ddof=0).replace(0, 1)
    ols_coef = np.linalg.lstsq(
        np.column_stack([standardized_train.to_numpy(), np.ones(len(train_X))]),
        train_y.to_numpy(),
        rcond=None,
    )[0]
    ols_predictions = (
        np.column_stack([standardized_test.to_numpy(), np.ones(len(test_X))]) @ ols_coef
    )

    assert not np.allclose(dfm_predictions, ols_predictions)


def test_save_load_restores_same_predictions(
    factor_structured_data: tuple[pd.DataFrame, pd.Series],
    tmp_path: Path,
) -> None:
    """Serialized statsmodels artifacts should restore prediction behavior."""
    X, y = factor_structured_data
    model = DynamicFactorModel(n_factors=2, max_iter=50, random_state=42)
    model.fit(X, y, vintage_date="2026-05-05")

    path = tmp_path / "dfm_statsmodels.joblib"
    model.save(path)
    loaded = DynamicFactorModel.load(path)

    expected = model.predict(X.iloc[-8:])
    actual = loaded.predict(X.iloc[-8:])

    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10)
    assert loaded.get_params()["implementation"] == "statsmodels_dynamic_factor"
    assert loaded.selected_ridge_alpha_ == model.selected_ridge_alpha_

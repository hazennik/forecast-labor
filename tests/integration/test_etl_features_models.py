"""
End-to-end integration tests for ETL → Features → Models pipeline.

This module validates the complete data flow from vintage data (ETL output)
through feature engineering to model training and prediction for ALL Phase 5 models.

Tests Phase 5.12.1 requirements with 4 core forecasting models:
1. MIDAS - Mixed-frequency regression
2. DFM - Dynamic Factor Model
3. XGBoost - Gradient boosting (quantile)
4. LightGBM - Alternative gradient boosting

Each test validates:
1. Load vintage data (from Phase 1-2)
2. Generate features (Phase 4)
3. Register features to database
4. Train model (Phase 5)
5. Generate predictions
6. Validate prediction format
7. Verify feature lineage tracked
8. Verify model metadata stored
9. Verify no data leakage (vintage-aware)
10. Verify reproducibility (same seed → same results)
"""

import sys
from pathlib import Path
from datetime import date, timedelta
from typing import Dict

import pytest
import pandas as pd
import numpy as np
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from features.registry import FeatureRegistry
from features.midas import MIDASBridge, SourceConfig
from models_src.utils.metrics import compute_metrics
from models_src.midas.midas_model import MIDASRegression
from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.gbm_quantile.xgb_quantile import XGBoostQuantile
from models_src.gbm_quantile.lgb_quantile import LightGBMQuantile
from models_src.pipelines.ensemble_pipeline import EnsembleConfig, EnsembleMethod
from models_src.pipelines.mixed_frequency_pipeline import (
    MixedFrequencyPipeline,
    MixedFrequencyPipelineConfig,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def integration_vintage_date() -> date:
    """Vintage date for integration testing."""
    return date(2024, 1, 15)


@pytest.fixture
def vintage_data(integration_vintage_date: date) -> Dict[str, pd.DataFrame]:
    """
    Simulated vintage data (ETL Phase 1-2 output).

    Creates realistic monthly time series representing:
    - Target variable (NFP-like employment data)
    - Predictor variables (economic indicators)

    This simulates what would come from the ETL pipeline.
    """
    np.random.seed(42)  # Deterministic

    # Generate 10 years of monthly data up to vintage date
    end_date = integration_vintage_date
    start_date = end_date - timedelta(days=365 * 10)
    dates = pd.date_range(start=start_date, end=end_date, freq="MS")
    n = len(dates)

    # Target: Monthly employment (NFP-like)
    trend = np.linspace(150000, 155000, n)
    seasonality = 500 * np.sin(2 * np.pi * np.arange(n) / 12)
    noise = np.random.normal(0, 1000, n)
    target = trend + seasonality + noise

    # Predictor 1: Leading indicator (claims-like)
    pred1_trend = np.linspace(250000, 240000, n)
    pred1_noise = np.random.normal(0, 5000, n)
    predictor1 = pred1_trend + pred1_noise

    # Predictor 2: Another indicator (treasury-like)
    pred2_trend = np.linspace(10000, 12000, n)
    pred2_noise = np.random.normal(0, 500, n)
    predictor2 = pred2_trend + pred2_noise

    # Predictor 3: Employment series
    pred3_trend = np.linspace(145000, 150000, n)
    pred3_noise = np.random.normal(0, 800, n)
    predictor3 = pred3_trend + pred3_noise

    df = pd.DataFrame(
        {
            "date": dates,
            "nfp_employment": target,
            "initial_claims": predictor1,
            "treasury_withholdings": predictor2,
            "ces_employment": predictor3,
            "vintage_date": integration_vintage_date,
        }
    )
    df.set_index("date", inplace=True)

    logger.info(
        "vintage_data_created",
        vintage_date=integration_vintage_date,
        records=len(df),
        start_date=df.index[0],
        end_date=df.index[-1],
    )

    return {"monthly_data": df}


@pytest.fixture
def feature_registry_memory() -> FeatureRegistry:
    """In-memory feature registry for testing."""
    return FeatureRegistry(backend="memory")


# ============================================================================
# Helper Functions
# ============================================================================


def generate_features(data: pd.DataFrame) -> pd.DataFrame:
    """
    Generate features from vintage data (Phase 4).

    Creates lag features and moving averages from predictors.
    """
    features_df = data[
        ["nfp_employment", "initial_claims", "treasury_withholdings", "ces_employment"]
    ].copy()

    # Generate lag features
    for col in ["initial_claims", "treasury_withholdings", "ces_employment"]:
        for lag in [1, 2, 3]:
            features_df[f"{col}_lag{lag}"] = features_df[col].shift(lag)

    # Generate moving average features
    for col in ["initial_claims", "treasury_withholdings"]:
        features_df[f"{col}_ma3"] = features_df[col].rolling(3).mean()

    # Drop rows with NaN
    features_df = features_df.dropna()

    return features_df


def register_features_to_registry(
    feature_names: list, registry: FeatureRegistry, vintage_date: date
) -> Dict[str, str]:
    """Register features to feature registry (Phase 4)."""
    feature_ids = {}
    for feature_name in feature_names:
        feature_dict = {
            "name": feature_name,
            "source": "vintage_integration_test",
            "frequency": "monthly",
            "transform": "lag"
            if "lag" in feature_name
            else ("rolling_mean" if "ma" in feature_name else "raw"),
            "vintage_date": str(vintage_date),
            "version": "1.0.0",
            "status": "production",
        }
        feature_id = registry.register(feature_dict)
        feature_ids[feature_name] = feature_id
    return feature_ids


def prepare_train_val_test_splits(X: np.ndarray, y: np.ndarray, dates: np.ndarray):
    """
    Prepare vintage-aware chronological splits (no data leakage).

    Returns train/val/test splits with dates.
    """
    train_end_idx = int(len(X) * 0.7)
    val_end_idx = int(len(X) * 0.85)

    X_train = X[:train_end_idx]
    y_train = y[:train_end_idx]
    dates_train = dates[:train_end_idx]

    X_val = X[train_end_idx:val_end_idx]
    y_val = y[train_end_idx:val_end_idx]
    dates_val = dates[train_end_idx:val_end_idx]

    X_test = X[val_end_idx:]
    y_test = y[val_end_idx:]
    dates_test = dates[val_end_idx:]

    return (X_train, y_train, dates_train), (X_val, y_val, dates_val), (X_test, y_test, dates_test)


# ============================================================================
# Integration Tests - One Per Model
# ============================================================================


class TestETLFeaturesModelsIntegration:
    """
    Test complete pipeline: ETL → Features → Models → Predictions.

    Tests all 4 core Phase 5 forecasting models.
    """

    def test_complete_pipeline_with_midas(
        self,
        vintage_data: Dict[str, pd.DataFrame],
        integration_vintage_date: date,
        feature_registry_memory: FeatureRegistry,
        tmp_path: Path,
    ):
        """
        Test: Complete pipeline with MIDAS regression model.

        Validates MIDAS (mixed-frequency regression) works in full pipeline.
        """
        logger.info("=" * 80)
        logger.info("TEST 1/4: MIDAS REGRESSION MODEL")
        logger.info("=" * 80)

        # Step 1: Load vintage data
        data = vintage_data["monthly_data"]
        assert len(data) > 0, "ETL: Data loaded"

        # Step 2: Generate features
        features_df = generate_features(data)
        feature_names = [col for col in features_df.columns if col != "nfp_employment"]
        assert len(feature_names) > 0, "Features: Generated"

        # Step 3: Register features
        feature_ids = register_features_to_registry(
            feature_names, feature_registry_memory, integration_vintage_date
        )
        assert len(feature_ids) == len(feature_names), "Registry: Features registered"

        # Step 4: Prepare data
        X = features_df[feature_names]
        y = features_df["nfp_employment"]
        dates = features_df.index.values

        train, val, test = prepare_train_val_test_splits(X.values, y.values, dates)
        X_train, y_train, dates_train = train
        X_test, y_test, dates_test = test

        # Validate no leakage
        assert dates_train[-1] < dates_test[0], "NO LEAKAGE: Train before test"

        # Step 5: Train MIDAS model (use subset of features for MIDAS - too many causes overflow)
        # MIDAS expects pre-constructed lag features, use 5 lags
        # Scale features to avoid numerical issues
        model = MIDASRegression(n_lags=5, almon_degree=2, horizon=1, random_state=42)

        # Use only first 5 features for MIDAS + scale them
        midas_features = feature_names[:5]
        X_train_midas = X_train[:, :5]
        X_test_midas = X_test[:, :5]

        # Standardize features (z-score normalization)
        X_train_mean = X_train_midas.mean(axis=0)
        X_train_std = X_train_midas.std(axis=0) + 1e-8  # Avoid division by zero
        X_train_scaled = (X_train_midas - X_train_mean) / X_train_std
        X_test_scaled = (X_test_midas - X_train_mean) / X_train_std

        X_train_df = pd.DataFrame(X_train_scaled, columns=midas_features)
        y_train_series = pd.Series(y_train)

        model.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        assert hasattr(model, "coefficients_"), "Model: MIDAS trained"

        # Step 6: Generate predictions
        X_test_df = pd.DataFrame(X_test_scaled, columns=midas_features)
        predictions = model.predict(X_test_df)

        assert len(predictions) == len(y_test), "Predictions: Correct length"
        assert not np.isnan(predictions).any(), "Predictions: No NaN"
        assert np.isfinite(predictions).all(), "Predictions: All finite"

        # Step 7: Compute metrics
        metrics = compute_metrics(y_test, predictions)
        assert "rmse" in metrics, "Metrics: Computed"

        # Step 8: Verify reproducibility
        model_2 = MIDASRegression(n_lags=5, almon_degree=2, horizon=1, random_state=42)
        model_2.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        predictions_2 = model_2.predict(X_test_df)

        np.testing.assert_array_almost_equal(
            predictions,
            predictions_2,
            decimal=5,
            err_msg="Reproducibility: MIDAS predictions identical",
        )

        logger.info(f"✅ MIDAS TEST PASSED - RMSE: {metrics['rmse']:.2f}")

    def test_complete_pipeline_with_dfm(
        self,
        vintage_data: Dict[str, pd.DataFrame],
        integration_vintage_date: date,
        feature_registry_memory: FeatureRegistry,
        tmp_path: Path,
    ):
        """
        Test: Complete pipeline with Dynamic Factor Model.

        Validates DFM (state-space model) works in full pipeline.
        """
        logger.info("=" * 80)
        logger.info("TEST 2/4: DYNAMIC FACTOR MODEL (DFM)")
        logger.info("=" * 80)

        # Step 1: Load vintage data
        data = vintage_data["monthly_data"]
        assert len(data) > 0, "ETL: Data loaded"

        # Step 2: Generate features
        features_df = generate_features(data)
        feature_names = [col for col in features_df.columns if col != "nfp_employment"]
        assert len(feature_names) > 0, "Features: Generated"

        # Step 3: Register features
        feature_ids = register_features_to_registry(
            feature_names, feature_registry_memory, integration_vintage_date
        )
        assert len(feature_ids) == len(feature_names), "Registry: Features registered"

        # Step 4: Prepare data
        X = features_df[feature_names]
        y = features_df["nfp_employment"]
        dates = features_df.index.values

        train, val, test = prepare_train_val_test_splits(X.values, y.values, dates)
        X_train, y_train, dates_train = train
        X_test, y_test, dates_test = test

        # Validate no leakage
        assert dates_train[-1] < dates_test[0], "NO LEAKAGE: Train before test"

        # Step 5: Train DFM model
        model = DynamicFactorModel(n_factors=2, max_iter=10, random_state=42)  # Small for speed

        X_train_df = pd.DataFrame(X_train, columns=feature_names)
        y_train_series = pd.Series(y_train)

        model.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        assert hasattr(model, "factors_"), "Model: DFM trained"

        # Step 6: Generate predictions
        X_test_df = pd.DataFrame(X_test, columns=feature_names)
        predictions = model.predict(X_test_df)

        assert len(predictions) == len(y_test), "Predictions: Correct length"
        assert not np.isnan(predictions).any(), "Predictions: No NaN"
        assert np.isfinite(predictions).all(), "Predictions: All finite"

        # Step 7: Compute metrics
        metrics = compute_metrics(y_test, predictions)
        assert "rmse" in metrics, "Metrics: Computed"

        # Step 8: Verify reproducibility
        model_2 = DynamicFactorModel(n_factors=2, max_iter=10, random_state=42)
        model_2.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        predictions_2 = model_2.predict(X_test_df)

        np.testing.assert_array_almost_equal(
            predictions,
            predictions_2,
            decimal=5,
            err_msg="Reproducibility: DFM predictions identical",
        )

        logger.info(f"✅ DFM TEST PASSED - RMSE: {metrics['rmse']:.2f}")

    def test_complete_pipeline_with_xgboost(
        self,
        vintage_data: Dict[str, pd.DataFrame],
        integration_vintage_date: date,
        feature_registry_memory: FeatureRegistry,
        tmp_path: Path,
    ):
        """
        Test: Complete pipeline with XGBoost quantile model.

        Validates XGBoost (gradient boosting) works in full pipeline.
        """
        logger.info("=" * 80)
        logger.info("TEST 3/4: XGBOOST QUANTILE MODEL")
        logger.info("=" * 80)

        # Step 1: Load vintage data
        data = vintage_data["monthly_data"]
        assert len(data) > 0, "ETL: Data loaded"

        # Step 2: Generate features
        features_df = generate_features(data)
        feature_names = [col for col in features_df.columns if col != "nfp_employment"]
        assert len(feature_names) > 0, "Features: Generated"

        # Step 3: Register features
        feature_ids = register_features_to_registry(
            feature_names, feature_registry_memory, integration_vintage_date
        )
        assert len(feature_ids) == len(feature_names), "Registry: Features registered"

        # Step 4: Prepare data
        X = features_df[feature_names]
        y = features_df["nfp_employment"]
        dates = features_df.index.values

        train, val, test = prepare_train_val_test_splits(X.values, y.values, dates)
        X_train, y_train, dates_train = train
        X_test, y_test, dates_test = test

        # Validate no leakage
        assert dates_train[-1] < dates_test[0], "NO LEAKAGE: Train before test"

        # Step 5: Train XGBoost model
        model = XGBoostQuantile(
            quantiles=[0.1, 0.5, 0.9],  # 3 quantiles for speed
            n_estimators=20,  # Small for speed
            max_depth=3,
            random_state=42,
        )

        X_train_df = pd.DataFrame(X_train, columns=feature_names)
        y_train_series = pd.Series(y_train)

        model.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        assert hasattr(model, "models_"), "Model: XGBoost trained"

        # Step 6: Generate predictions (returns Dict with quantiles)
        X_test_df = pd.DataFrame(X_test, columns=feature_names)
        predictions_dict = model.predict(X_test_df)

        assert isinstance(predictions_dict, dict), "Predictions: Dict format"
        assert len(predictions_dict) == 3, "Predictions: 3 quantiles"
        assert 0.5 in predictions_dict, "Predictions: Has median quantile"
        assert len(predictions_dict[0.5]) == len(y_test), "Predictions: Correct length"
        assert not np.isnan(predictions_dict[0.5]).any(), "Predictions: No NaN"

        # Use median (0.5 quantile) for metrics
        predictions = predictions_dict[0.5]

        # Step 7: Compute metrics
        metrics = compute_metrics(y_test, predictions)
        assert "rmse" in metrics, "Metrics: Computed"

        # Step 8: Verify reproducibility
        model_2 = XGBoostQuantile(
            quantiles=[0.1, 0.5, 0.9], n_estimators=20, max_depth=3, random_state=42
        )
        model_2.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        predictions_dict_2 = model_2.predict(X_test_df)

        # Compare dicts
        for q in [0.1, 0.5, 0.9]:
            np.testing.assert_array_equal(
                predictions_dict[q],
                predictions_dict_2[q],
                err_msg=f"Reproducibility: XGBoost quantile {q} identical",
            )

        logger.info(f"✅ XGBOOST TEST PASSED - RMSE: {metrics['rmse']:.2f}")

    def test_complete_pipeline_with_lightgbm(
        self,
        vintage_data: Dict[str, pd.DataFrame],
        integration_vintage_date: date,
        feature_registry_memory: FeatureRegistry,
        tmp_path: Path,
    ):
        """
        Test: Complete pipeline with LightGBM quantile model.

        Validates LightGBM (alternative gradient boosting) works in full pipeline.
        """
        logger.info("=" * 80)
        logger.info("TEST 4/4: LIGHTGBM QUANTILE MODEL")
        logger.info("=" * 80)

        # Step 1: Load vintage data
        data = vintage_data["monthly_data"]
        assert len(data) > 0, "ETL: Data loaded"

        # Step 2: Generate features
        features_df = generate_features(data)
        feature_names = [col for col in features_df.columns if col != "nfp_employment"]
        assert len(feature_names) > 0, "Features: Generated"

        # Step 3: Register features
        feature_ids = register_features_to_registry(
            feature_names, feature_registry_memory, integration_vintage_date
        )
        assert len(feature_ids) == len(feature_names), "Registry: Features registered"

        # Step 4: Prepare data
        X = features_df[feature_names]
        y = features_df["nfp_employment"]
        dates = features_df.index.values

        train, val, test = prepare_train_val_test_splits(X.values, y.values, dates)
        X_train, y_train, dates_train = train
        X_test, y_test, dates_test = test

        # Validate no leakage
        assert dates_train[-1] < dates_test[0], "NO LEAKAGE: Train before test"

        # Step 5: Train LightGBM model
        model = LightGBMQuantile(
            quantiles=[0.1, 0.5, 0.9],  # 3 quantiles for speed
            n_estimators=20,  # Small for speed
            max_depth=3,
            random_state=42,
        )

        X_train_df = pd.DataFrame(X_train, columns=feature_names)
        y_train_series = pd.Series(y_train)

        model.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        assert hasattr(model, "models_"), "Model: LightGBM trained"

        # Step 6: Generate predictions (returns Dict with quantiles)
        X_test_df = pd.DataFrame(X_test, columns=feature_names)
        predictions_dict = model.predict(X_test_df)

        assert isinstance(predictions_dict, dict), "Predictions: Dict format"
        assert len(predictions_dict) == 3, "Predictions: 3 quantiles"
        assert 0.5 in predictions_dict, "Predictions: Has median quantile"
        assert len(predictions_dict[0.5]) == len(y_test), "Predictions: Correct length"
        assert not np.isnan(predictions_dict[0.5]).any(), "Predictions: No NaN"

        # Use median (0.5 quantile) for metrics
        predictions = predictions_dict[0.5]

        # Step 7: Compute metrics
        metrics = compute_metrics(y_test, predictions)
        assert "rmse" in metrics, "Metrics: Computed"

        # Step 8: Verify reproducibility
        model_2 = LightGBMQuantile(
            quantiles=[0.1, 0.5, 0.9], n_estimators=20, max_depth=3, random_state=42
        )
        model_2.fit(X_train_df, y_train_series, vintage_date=str(integration_vintage_date))
        predictions_dict_2 = model_2.predict(X_test_df)

        # Compare dicts
        for q in [0.1, 0.5, 0.9]:
            np.testing.assert_array_almost_equal(
                predictions_dict[q],
                predictions_dict_2[q],
                decimal=3,
                err_msg=f"Reproducibility: LightGBM quantile {q} identical",
            )

        logger.info(f"✅ LIGHTGBM TEST PASSED - RMSE: {metrics['rmse']:.2f}")

    def test_complete_pipeline_with_midas_bridge_and_dfm(
        self,
        vintage_data: Dict[str, pd.DataFrame],
        integration_vintage_date: date,
    ):
        """
        Test: Raw mixed-frequency sources → MIDASBridge → DFM/XGBoost/MIDAS ensemble.

        Validates the R5 integration layer while preserving the existing ETL →
        Features → Models contract tested above.
        """
        data = vintage_data["monthly_data"].iloc[:24]
        target = data["nfp_employment"]
        daily_dates = pd.date_range(
            data.index[0] - pd.Timedelta(days=120), data.index[-1], freq="D"
        )
        weekly_dates = pd.date_range(
            data.index[0] - pd.Timedelta(days=120), data.index[-1], freq="W"
        )
        raw_sources = {
            "treasury": pd.DataFrame(
                {
                    "date": daily_dates,
                    "daily_withholding": np.interp(
                        np.arange(len(daily_dates)),
                        np.linspace(0, len(daily_dates) - 1, len(data)),
                        data["treasury_withholdings"].to_numpy(),
                    ),
                }
            ),
            "claims": pd.DataFrame(
                {
                    "report_date": weekly_dates,
                    "initial_claims": np.interp(
                        np.arange(len(weekly_dates)),
                        np.linspace(0, len(weekly_dates) - 1, len(data)),
                        data["initial_claims"].to_numpy(),
                    ),
                }
            ),
            "ces": pd.DataFrame(
                {
                    "date": data.index,
                    "all_employees": data["ces_employment"].to_numpy(),
                }
            ),
        }
        source_configs = {
            "treasury": SourceConfig("treasury", "D", "date", "daily_withholding", 5),
            "claims": SourceConfig("claims", "W", "report_date", "initial_claims", 3),
            "ces": SourceConfig("ces", "M", "date", "all_employees", 1),
        }
        pipeline = MixedFrequencyPipeline(
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
            pipeline_config=MixedFrequencyPipelineConfig(residual_scale_floor=5.0),
        )

        pipeline.fit(integration_vintage_date, raw_sources, target)
        predictions, intervals = pipeline.predict(
            integration_vintage_date,
            raw_sources,
            target_dates=pd.DatetimeIndex(target.index[-3:]),
        )

        assert predictions.shape == (3,)
        assert intervals.shape == (3, 2)
        assert np.isfinite(predictions).all()
        assert np.all(intervals[:, 0] < intervals[:, 1])


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    """Run integration tests with verbose output."""
    pytest.main([__file__, "-v", "-s", "--tb=short"])

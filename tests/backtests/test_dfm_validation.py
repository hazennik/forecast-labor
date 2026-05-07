"""
Phase 6.3.1a: DFM Validation with Real NFP Data

Tests DFM (Dynamic Factor Model) on ACTUAL BLS CES vintage data to validate:
1. Numerical stability with real mixed-frequency data (no 10^17 explosions)
2. Accuracy comparison: DFM vs MIDAS vs XGBoost (sMAPE, RMSE, PI coverage)
3. Whether DFM should be included in production ensemble

This addresses the Phase 5.13.2 limitation where DFM was excluded from
integration tests due to synthetic data sensitivity (codex_analysis_25.md).

DATA SOURCE: Real BLS CES (Current Employment Statistics) data from:
- data/vintages/bls_ces/{YYYY-MM-DD}/bls_ces_vintage.parquet

Success Criteria:
- DFM sMAPE < 20%
- Stable predictions (no |magnitude| > 1,000,000)
- DFM adds value to ensemble

References:
- Phase 5.13.2 completion notes
- docs/planning/codex_analyses/codex_analysis_25.md
- .cursorrules: TESTING_MATHEMATICAL_ALGORITHMS.md
"""

import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

import pytest
import pandas as pd
import numpy as np
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from features.midas import MIDASBridge, SourceConfig
from models_src.calibration.conformal import ConformalPredictor
from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.midas.midas_model import MIDASRegression
from models_src.gbm_quantile.xgb_quantile import XGBoostQuantile
from models_src.pipelines.ensemble_pipeline import EnsembleConfig, EnsembleMethod
from models_src.pipelines.ensemble_pipeline import optimize_weights, weighted_average
from models_src.pipelines.mixed_frequency_pipeline import (
    MixedFrequencyPipeline,
    MixedFrequencyPipelineConfig,
)
from models_src.utils.metrics import rmse, smape
from etl.common.vintage import VintageManager


# ============================================================================
# Test Configuration Constants
# ============================================================================

# Phase 6.3.1a Success Criteria
SMAPE_THRESHOLD = 20.0  # DFM sMAPE < 20%
STABILITY_THRESHOLD = 1_000_000  # No forecasts > 1M magnitude
PI_COVERAGE_MIN = 85.0  # Minimum 85% coverage for 90% intervals
PI_COVERAGE_MAX = 95.0  # Maximum 95% coverage for 90% intervals
MIN_TRAINING_SAMPLES = 60  # Minimum samples for meaningful model training (5 years monthly)
MIN_TEST_SAMPLES = 3  # Minimum test samples for evaluation
MIN_CALIBRATION_SAMPLES = 12  # Minimum holdout samples for conformal interval checks
CES_RELEASE_LAG_MONTHS = 1  # CES components release with NFP, so use only prior-month values.

# Key CES series for model features
NFP_SERIES_ID = "CES0000000001"  # Total Nonfarm Payrolls (target)
FEATURE_SERIES_IDS = [
    "CES0500000001",  # Total Private
    "CES0600000001",  # Goods-Producing
    "CES0700000001",  # Service-Providing
    "CES4200000001",  # Retail Trade
    "CES7000000001",  # Leisure and Hospitality
    "CES3000000001",  # Manufacturing
    "CES2000000001",  # Construction
]


def _source_name_for_series(series_id: str) -> str:
    """Return a bridge-safe source name for a CES series id."""
    return f"ces_{series_id.lower()}"


def build_ces_bridge_inputs(
    data: pd.DataFrame,
    target_series_id: str = NFP_SERIES_ID,
    feature_series_ids: List[str] = FEATURE_SERIES_IDS,
    release_lag_months: int = CES_RELEASE_LAG_MONTHS,
) -> Tuple[MIDASBridge, Dict[str, pd.DataFrame], pd.Series]:
    """
    Build real CES raw-source inputs for MIDASBridge validation.

    The available R7 real-data fixture is BLS CES monthly vintage data. Each
    sector series is passed through the bridge as its own monthly source. CES
    components are released with total NFP, so feature dates are shifted forward
    by one month; a target month can only use sector values known from prior
    releases.
    """
    if release_lag_months < 0:
        raise ValueError("release_lag_months must be non-negative")

    data = data.copy()
    data["date"] = pd.to_datetime(data["date"])

    target_data = data[data["series_id"] == target_series_id].copy()
    target_data = target_data.sort_values("date").set_index("date")
    if target_data.empty:
        raise ValueError(f"Target series {target_series_id} not found in data")

    target = target_data["mom_change"].dropna().rename("nfp_mom_change")
    source_configs: Dict[str, SourceConfig] = {}
    raw_sources: Dict[str, pd.DataFrame] = {}

    for series_id in feature_series_ids:
        series_data = data[data["series_id"] == series_id].copy()
        if series_data.empty or "mom_change" not in series_data.columns:
            continue

        source_name = _source_name_for_series(series_id)
        raw_frame = (
            series_data[["date", "mom_change"]]
            .dropna(subset=["mom_change"])
            .sort_values("date")
            .rename(columns={"mom_change": "ces_mom_change"})
        )
        if raw_frame.empty:
            continue
        if release_lag_months:
            raw_frame["date"] = raw_frame["date"] + pd.DateOffset(months=release_lag_months)

        source_configs[source_name] = SourceConfig(
            source_name=source_name,
            frequency="M",
            date_column="date",
            value_column="ces_mom_change",
            n_lags=1,
            aggregation="last",
        )
        raw_sources[source_name] = raw_frame

    if not raw_sources:
        raise ValueError("No bridge-compatible CES feature series found in data")

    bridge = MIDASBridge(source_configs=source_configs)
    return bridge, raw_sources, target


def split_train_calibration_test(
    features: pd.DataFrame,
    target: pd.Series,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Split a monthly vintage dataset into train, calibration, and test slices."""
    train_end = int(len(features) * 0.7)
    calibration_end = int(len(features) * 0.85)

    X_train = features.iloc[:train_end]
    X_calibration = features.iloc[train_end:calibration_end]
    X_test = features.iloc[calibration_end:]
    y_train = target.iloc[:train_end]
    y_calibration = target.iloc[train_end:calibration_end]
    y_test = target.iloc[calibration_end:]

    return X_train, X_calibration, X_test, y_train, y_calibration, y_test


def empirical_interval_coverage(
    y_true: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> float:
    """Compute empirical interval coverage as a percentage."""
    return float(np.mean((y_true >= lower) & (y_true <= upper)) * 100.0)


def interval_calibration_error(coverage_pct: float, nominal_pct: float = 90.0) -> float:
    """Compute absolute interval calibration error on a 0-1 scale."""
    return abs(coverage_pct - nominal_pct) / 100.0


# ============================================================================
# Data Loading Utilities
# ============================================================================


def load_vintage_data(vintage_manager: VintageManager, vintage_date: date) -> Optional[pd.DataFrame]:
    """
    Load CES vintage data from parquet file.
    
    Args:
        vintage_manager: VintageManager instance
        vintage_date: Date of vintage to load
        
    Returns:
        DataFrame with CES data or None if not available
    """
    try:
        data = vintage_manager.load_vintage("bls_ces", vintage_date)
        
        # Verify it's real data (not synthetic)
        if "source" in data.columns:
            source_type = data["source"].iloc[0] if len(data) > 0 else ""
            if "synthetic" in str(source_type).lower():
                logger.warning(f"Vintage {vintage_date} contains synthetic data, skipping")
                return None
        
        return data
    except Exception as e:
        logger.warning(f"Failed to load vintage {vintage_date}: {e}")
        return None


def prepare_features_and_target(
    data: pd.DataFrame,
    target_series_id: str = NFP_SERIES_ID,
    feature_series_ids: List[str] = FEATURE_SERIES_IDS,
    release_lag_months: int = CES_RELEASE_LAG_MONTHS,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Prepare features and target from CES vintage data.
    
    Uses sector-level employment as features to predict total NFP.
    Creates lagged features and month-over-month changes.
    
    Args:
        data: Raw CES vintage data
        target_series_id: Series ID for target variable (NFP)
        feature_series_ids: Series IDs for feature variables
        
    Returns:
        Tuple of (features DataFrame, target Series)
    """
    bridge, raw_sources, target = build_ces_bridge_inputs(
        data,
        target_series_id=target_series_id,
        feature_series_ids=feature_series_ids,
        release_lag_months=release_lag_months,
    )
    features = bridge.build_features(raw_sources, pd.DatetimeIndex(target.index))

    # Align bridged features and target
    common_index = features.index.intersection(target.index)
    features = features.loc[common_index]
    target = target.loc[common_index]

    if release_lag_months:
        features = features.iloc[release_lag_months:]
        target = target.iloc[release_lag_months:]
    
    # Drop rows with NaN
    valid_mask = ~(features.isna().any(axis=1) | target.isna())
    features = features[valid_mask]
    target = target[valid_mask]
    
    return features, target


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def vintage_base_path() -> Path:
    """Return path to vintage data directory."""
    return project_root / "data" / "vintages"


@pytest.fixture(scope="module")
def vintage_manager(vintage_base_path: Path) -> VintageManager:
    """Create VintageManager for accessing real vintage data."""
    return VintageManager(vintage_base_path)


@pytest.fixture(scope="module")
def real_vintage_dates(vintage_manager: VintageManager) -> List[date]:
    """
    Get list of vintage dates with REAL (non-synthetic) BLS CES data.
    
    Filters out synthetic test vintages and returns only dates with
    actual BLS API data.
    """
    all_vintages = vintage_manager.list_vintages("bls_ces")
    
    if not all_vintages:
        pytest.skip("No BLS CES vintages available. Run ETL and create_historical_vintages.py first.")
    
    real_vintages = []
    
    for vdate in all_vintages:
        try:
            data = vintage_manager.load_vintage("bls_ces", vdate)
            
            # Check if real data
            if "source" in data.columns:
                source = data["source"].iloc[0] if len(data) > 0 else ""
                if "BLS" in str(source) or "API" in str(source):
                    # Verify NFP series exists with sufficient data
                    nfp_data = data[data["series_id"] == NFP_SERIES_ID]
                    if len(nfp_data) >= MIN_TRAINING_SAMPLES:
                        real_vintages.append(vdate)
                        
        except Exception as e:
            logger.debug(f"Skipping vintage {vdate}: {e}")
            continue
    
    if len(real_vintages) < 10:
        pytest.skip(
            f"Only {len(real_vintages)} real vintages available (need 10+). "
            "Run: docker compose exec etl python scripts/create_historical_vintages.py"
        )
    
    logger.info(f"Found {len(real_vintages)} real BLS CES vintages for testing")
    return sorted(real_vintages)


@pytest.fixture(scope="module") 
def vintage_datasets(
    vintage_manager: VintageManager,
    real_vintage_dates: List[date]
) -> Dict[date, Dict]:
    """
    Load and prepare datasets from real vintage data.
    
    Returns dictionary mapping vintage dates to prepared features/target.
    """
    datasets = {}
    
    for vdate in real_vintage_dates:
        try:
            data = load_vintage_data(vintage_manager, vdate)
            
            if data is None:
                continue
            
            bridge, raw_sources, target = build_ces_bridge_inputs(data)
            features, target = prepare_features_and_target(data)
            
            if len(features) < MIN_TRAINING_SAMPLES + MIN_TEST_SAMPLES:
                logger.warning(f"Insufficient data for vintage {vdate}, skipping")
                continue
            
            datasets[vdate] = {
                "features": features,
                "target": target,
                "raw_sources": raw_sources,
                "source_configs": bridge.source_configs,
                "release_lag_months": CES_RELEASE_LAG_MONTHS,
                "n_samples": len(features),
                "date_range": (features.index.min(), features.index.max()),
            }
            
            logger.info(
                f"Loaded vintage {vdate}: {len(features)} samples, "
                f"{features.shape[1]} features, "
                f"date range {features.index.min().date()} to {features.index.max().date()}"
            )
            
        except Exception as e:
            logger.warning(f"Failed to prepare vintage {vdate}: {e}")
            continue
    
    if len(datasets) < 10:
        pytest.skip(f"Only {len(datasets)} valid vintages prepared (need 10+)")
    
    return datasets


# ============================================================================
# Unit Tests: DFM Numerical Stability
# ============================================================================


class TestDFMNumericalStability:
    """
    Test DFM numerical stability with REAL BLS CES data.
    
    Phase 5.13.2 Issue: DFM predictions exploded to 10^17 with synthetic data.
    Phase 6.3.1a Goal: Verify stability with actual NFP data.
    """

    def test_ces_bridge_features_are_pre_release(
        self,
        vintage_datasets: Dict[date, Dict],
    ):
        """Real CES validation must not use same-release sector changes."""
        vintage_date, data = next(iter(vintage_datasets.items()))
        features = data["features"]
        raw_sources = data["raw_sources"]

        first_target_date = features.index.min()
        for source_name, raw_frame in raw_sources.items():
            available = raw_frame[pd.to_datetime(raw_frame["date"]) <= first_target_date]
            assert not available.empty, f"{source_name} should have prior-release data"
            assert available["date"].max() == first_target_date

        assert data["release_lag_months"] == CES_RELEASE_LAG_MONTHS
        logger.info(
            "ces_bridge_pre_release_verified",
            vintage_date=vintage_date,
            first_target_date=str(first_target_date.date()),
        )
    
    def test_dfm_stability_on_real_data(
        self,
        vintage_datasets: Dict[date, Dict]
    ):
        """
        Measure DFM prediction stability across real vintages.
        
        Records stability metrics for Phase 6.3.1a validation.
        """
        stability_results = []
        
        for vintage_date, data in vintage_datasets.items():
            features = data["features"]
            target = data["target"]
            
            # Train/test split (80/20)
            split_idx = int(len(features) * 0.8)
            X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
            y_train, y_test = target.iloc[:split_idx], target.iloc[split_idx:]
            
            if len(X_train) < MIN_TRAINING_SAMPLES or len(X_test) < MIN_TEST_SAMPLES:
                continue
            
            try:
                # Initialize and train DFM
                dfm = DynamicFactorModel(
                    n_factors=min(3, X_train.shape[1] // 2),  # Scale factors to feature count
                    max_iter=100,
                    tol=1e-4,
                    random_state=42
                )
                
                dfm.fit(X_train, y_train, vintage_date=str(vintage_date))
                predictions = dfm.predict(X_test)
                
                # Stability check
                max_abs_pred = np.abs(predictions).max()
                is_stable = max_abs_pred < STABILITY_THRESHOLD
                has_nan = np.any(np.isnan(predictions))
                has_inf = np.any(np.isinf(predictions))
                
                stability_results.append({
                    "vintage_date": vintage_date,
                    "max_abs_prediction": max_abs_pred,
                    "is_stable": is_stable,
                    "has_nan": has_nan,
                    "has_inf": has_inf,
                    "n_train": len(X_train),
                    "n_test": len(X_test),
                })
                
                status = "STABLE" if is_stable else "UNSTABLE"
                logger.info(
                    f"DFM stability for {vintage_date}: {status} "
                    f"(max |pred| = {max_abs_pred:.2f}, n_train={len(X_train)})"
                )
                
            except Exception as e:
                logger.error(f"DFM failed for {vintage_date}: {e}")
                stability_results.append({
                    "vintage_date": vintage_date,
                    "max_abs_prediction": float('inf'),
                    "is_stable": False,
                    "error": str(e),
                })
        
        # Summary
        stable_count = sum(1 for r in stability_results if r.get("is_stable", False))
        total = len(stability_results)
        finite_count = sum(
            1 for r in stability_results if not r.get("has_nan", True) and not r.get("has_inf", True)
        )
        stability_rate = stable_count / total if total else 0.0
        
        logger.info(
            f"\n=== DFM Stability Summary (Real Data) ===\n"
            f"Vintages tested: {total}\n"
            f"Stable: {stable_count}/{total}\n"
            f"Finite predictions: {finite_count}/{total}\n"
            f"All stable: {stable_count == total}\n"
        )
        
        # Store results for reporting
        pytest.dfm_stability_results = stability_results
        
        assert total >= 10, f"Need at least 10 vintage tests, got {total}"
        assert stability_rate >= 0.90, f"DFM stability rate {stability_rate:.0%} below 90%"
        assert finite_count == total, "DFM produced NaN or Inf predictions on real vintages"
    
    def test_dfm_no_nan_predictions(self, vintage_datasets: Dict[date, Dict]):
        """Test that DFM produces no NaN predictions on real data."""
        nan_count = 0
        
        for vintage_date, data in list(vintage_datasets.items())[:5]:  # Test subset
            features = data["features"]
            target = data["target"]
            
            split_idx = int(len(features) * 0.8)
            X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
            y_train, y_test = target.iloc[:split_idx], target.iloc[split_idx:]
            
            if len(X_train) < MIN_TRAINING_SAMPLES:
                continue
            
            try:
                dfm = DynamicFactorModel(n_factors=2, random_state=42)
                dfm.fit(X_train, y_train, vintage_date=str(vintage_date))
                predictions = dfm.predict(X_test)
                
                if np.any(np.isnan(predictions)):
                    nan_count += 1
                    logger.warning(f"DFM produced NaN for {vintage_date}")
                    
            except Exception as e:
                logger.error(f"DFM error for {vintage_date}: {e}")
        
        logger.info(f"NaN check: {nan_count} vintages with NaN predictions")
        assert nan_count == 0, f"DFM produced NaN predictions for {nan_count} vintages"


# ============================================================================
# Unit Tests: DFM Accuracy
# ============================================================================


class TestDFMAccuracy:
    """
    Measure DFM accuracy on REAL NFP data.
    
    Target Criteria: sMAPE < 20%
    """
    
    def test_dfm_accuracy_on_real_data(
        self,
        vintage_datasets: Dict[date, Dict]
    ):
        """
        Measure DFM sMAPE and RMSE across real vintages.
        
        Records accuracy metrics for Phase 6.3.1a validation.
        """
        accuracy_results = []
        
        for vintage_date, data in vintage_datasets.items():
            features = data["features"]
            target = data["target"]
            
            split_idx = int(len(features) * 0.8)
            X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
            y_train, y_test = target.iloc[:split_idx], target.iloc[split_idx:]
            
            if len(X_train) < MIN_TRAINING_SAMPLES or len(X_test) < MIN_TEST_SAMPLES:
                continue
            
            try:
                dfm = DynamicFactorModel(
                    n_factors=min(3, X_train.shape[1] // 2),
                    random_state=42
                )
                dfm.fit(X_train, y_train, vintage_date=str(vintage_date))
                predictions = dfm.predict(X_test)
                
                # Skip if unstable
                if np.abs(predictions).max() > STABILITY_THRESHOLD:
                    logger.warning(f"Skipping accuracy for unstable {vintage_date}")
                    continue
                
                dfm_smape = smape(y_test.values, predictions)
                dfm_rmse = rmse(y_test.values, predictions)
                
                accuracy_results.append({
                    "vintage_date": vintage_date,
                    "smape": dfm_smape,
                    "rmse": dfm_rmse,
                    "target_std": y_test.std(),
                    "target_mean": y_test.mean(),
                    "meets_threshold": dfm_smape < SMAPE_THRESHOLD,
                })
                
                status = "PASS" if dfm_smape < SMAPE_THRESHOLD else "FAIL"
                logger.info(
                    f"DFM accuracy {vintage_date}: sMAPE={dfm_smape:.2f}% "
                    f"RMSE={dfm_rmse:.2f} ({status})"
                )
                
            except Exception as e:
                logger.error(f"DFM accuracy test failed for {vintage_date}: {e}")
        
        if not accuracy_results:
            pytest.skip("No valid accuracy results")
        
        # Summary
        avg_smape = np.mean([r["smape"] for r in accuracy_results])
        avg_rmse = np.mean([r["rmse"] for r in accuracy_results])
        pass_count = sum(1 for r in accuracy_results if r["meets_threshold"])
        
        logger.info(
            f"\n=== DFM Accuracy Summary (Real Data) ===\n"
            f"Vintages tested: {len(accuracy_results)}\n"
            f"Average sMAPE: {avg_smape:.2f}%\n"
            f"Average RMSE: {avg_rmse:.2f}\n"
            f"Pass rate: {pass_count}/{len(accuracy_results)}\n"
            f"Threshold: {SMAPE_THRESHOLD}%\n"
        )
        
        # Store for reporting
        pytest.dfm_accuracy_results = accuracy_results

        assert len(accuracy_results) >= 10, (
            f"Need at least 10 real-vintage accuracy results, got {len(accuracy_results)}"
        )
        assert np.isfinite(avg_smape), "Average DFM sMAPE must be finite"
        assert np.isfinite(avg_rmse), "Average DFM RMSE must be finite"


# ============================================================================
# Unit Tests: Model Comparison
# ============================================================================


class TestModelComparison:
    """
    Compare DFM vs MIDAS vs XGBoost on REAL NFP data.
    
    Goal: Determine if DFM adds value to the ensemble.
    """
    
    def test_model_comparison_on_real_data(
        self,
        vintage_datasets: Dict[date, Dict]
    ):
        """
        Compare all three model types on real vintage data.
        """
        comparison_results = []
        
        for vintage_date, data in vintage_datasets.items():
            features = data["features"]
            target = data["target"]
            
            split_idx = int(len(features) * 0.8)
            X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
            y_train, y_test = target.iloc[:split_idx], target.iloc[split_idx:]
            
            if len(X_train) < MIN_TRAINING_SAMPLES or len(X_test) < MIN_TEST_SAMPLES:
                continue
            
            vintage_str = str(vintage_date)
            results = {"vintage_date": vintage_date}
            
            # DFM
            try:
                dfm = DynamicFactorModel(
                    n_factors=min(3, X_train.shape[1] // 2),
                    random_state=42
                )
                dfm.fit(X_train, y_train, vintage_date=vintage_str)
                dfm_preds = dfm.predict(X_test)
                
                if np.abs(dfm_preds).max() < STABILITY_THRESHOLD:
                    results["dfm_smape"] = smape(y_test.values, dfm_preds)
                    results["dfm_rmse"] = rmse(y_test.values, dfm_preds)
                    results["dfm_stable"] = True
                else:
                    results["dfm_smape"] = np.nan
                    results["dfm_rmse"] = np.nan
                    results["dfm_stable"] = False
            except Exception as e:
                results["dfm_smape"] = np.nan
                results["dfm_rmse"] = np.nan
                results["dfm_stable"] = False
                results["dfm_error"] = str(e)
            
            # MIDAS
            try:
                midas = MIDASRegression(
                    n_lags=min(10, X_train.shape[1]),
                    almon_degree=2,
                    random_state=42
                )
                midas.fit(X_train, y_train, vintage_date=vintage_str)
                midas_preds = midas.predict(X_test)
                results["midas_smape"] = smape(y_test.values, midas_preds)
                results["midas_rmse"] = rmse(y_test.values, midas_preds)
            except Exception as e:
                results["midas_smape"] = np.nan
                results["midas_rmse"] = np.nan
                results["midas_error"] = str(e)
            
            # XGBoost
            try:
                xgb = XGBoostQuantile(
                    quantiles=[0.5],
                    n_estimators=50,
                    max_depth=3,
                    random_state=42
                )
                xgb.fit(X_train, y_train, vintage_date=vintage_str)
                xgb_preds = xgb.predict(X_test)[0.5]
                results["xgb_smape"] = smape(y_test.values, xgb_preds)
                results["xgb_rmse"] = rmse(y_test.values, xgb_preds)
            except Exception as e:
                results["xgb_smape"] = np.nan
                results["xgb_rmse"] = np.nan
                results["xgb_error"] = str(e)
            
            comparison_results.append(results)
            
            logger.info(
                f"Vintage {vintage_date}: "
                f"DFM={results.get('dfm_smape', 'N/A'):.2f}%, "
                f"MIDAS={results.get('midas_smape', 'N/A'):.2f}%, "
                f"XGB={results.get('xgb_smape', 'N/A'):.2f}%"
            )
        
        if not comparison_results:
            pytest.skip("No valid comparison results")
        
        # Compute averages
        df = pd.DataFrame(comparison_results)
        
        avg_dfm = df["dfm_smape"].mean()
        avg_midas = df["midas_smape"].mean()
        avg_xgb = df["xgb_smape"].mean()
        
        dfm_stable_pct = df["dfm_stable"].mean() * 100 if "dfm_stable" in df else 0
        
        logger.info(
            f"\n=== Model Comparison Summary (Real Data) ===\n"
            f"Vintages tested: {len(comparison_results)}\n"
            f"Average DFM sMAPE: {avg_dfm:.2f}% (stable: {dfm_stable_pct:.0f}%)\n"
            f"Average MIDAS sMAPE: {avg_midas:.2f}%\n"
            f"Average XGBoost sMAPE: {avg_xgb:.2f}%\n"
        )
        
        # Store for final report
        pytest.model_comparison_results = comparison_results


class TestVintageHonestDFMEnsembleWeight:
    """Verify DFM earns optimized weight on time-ordered public-data validations."""

    def test_dfm_earns_nonzero_optimized_weight_on_real_vintages(
        self,
        vintage_datasets: Dict[date, Dict],
    ):
        """DFM should receive non-zero weight when validation data supports it."""
        weight_results = []

        for vintage_date, data in vintage_datasets.items():
            features = data["features"]
            target = data["target"]
            X_train, X_validation, X_test, y_train, y_validation, y_test = (
                split_train_calibration_test(features, target)
            )

            if (
                len(X_train) < MIN_TRAINING_SAMPLES
                or len(X_validation) < MIN_CALIBRATION_SAMPLES
                or len(X_test) < MIN_TEST_SAMPLES
            ):
                continue

            vintage_str = str(vintage_date)
            dfm = DynamicFactorModel(
                n_factors=min(3, X_train.shape[1] // 2),
                random_state=42,
            )
            xgb = XGBoostQuantile(
                quantiles=[0.5],
                n_estimators=50,
                max_depth=3,
                random_state=42,
            )
            dfm.fit(X_train, y_train, vintage_date=vintage_str)
            xgb.fit(X_train, y_train, vintage_date=vintage_str)

            validation_predictions = {
                "dfm": dfm.predict(X_validation),
                "xgboost": xgb.predict(X_validation)[0.5],
            }
            weights = optimize_weights(validation_predictions, y_validation.to_numpy(dtype=float))

            test_predictions = {
                "dfm": dfm.predict(X_test),
                "xgboost": xgb.predict(X_test)[0.5],
            }
            combined = weighted_average(test_predictions, weights)
            weight_results.append(
                {
                    "vintage_date": vintage_date,
                    "dfm_weight": weights["dfm"],
                    "xgboost_weight": weights["xgboost"],
                    "test_smape": smape(y_test.values, combined),
                }
            )

        assert len(weight_results) >= 10, (
            f"Need at least 10 optimized-weight validations, got {len(weight_results)}"
        )

        avg_dfm_weight = float(np.mean([r["dfm_weight"] for r in weight_results]))
        nonzero_count = sum(1 for r in weight_results if r["dfm_weight"] > 1e-6)
        avg_test_smape = float(np.mean([r["test_smape"] for r in weight_results]))
        logger.info(
            f"\n=== Vintage-Honest DFM Weight Summary ===\n"
            f"Vintages tested: {len(weight_results)}\n"
            f"Average DFM optimized weight: {avg_dfm_weight:.3f}\n"
            f"Non-zero DFM weights: {nonzero_count}/{len(weight_results)}\n"
            f"Average optimized ensemble test sMAPE: {avg_test_smape:.2f}%\n"
        )

        pytest.dfm_weight_results = weight_results
        assert avg_dfm_weight > 0.05
        assert nonzero_count >= len(weight_results) // 2
        assert np.isfinite(avg_test_smape)


class TestDFMCalibrationIntegration:
    """Verify conformal calibration works on bridge-produced real CES features."""

    def test_bridge_to_calibration_pipeline(
        self,
        vintage_datasets: Dict[date, Dict],
    ):
        """MIDASBridge -> DFM -> ConformalPredictor should produce finite intervals."""
        interval_results = []

        for vintage_date, data in vintage_datasets.items():
            features = data["features"]
            target = data["target"]
            split = split_train_calibration_test(features, target)
            X_train, X_calibration, X_test, y_train, y_calibration, y_test = split

            if (
                len(X_train) < MIN_TRAINING_SAMPLES
                or len(X_calibration) < MIN_CALIBRATION_SAMPLES
                or len(X_test) < MIN_TEST_SAMPLES
            ):
                continue

            dfm = DynamicFactorModel(
                n_factors=min(3, X_train.shape[1] // 2),
                random_state=42,
            )
            dfm.fit(X_train, y_train, vintage_date=str(vintage_date))
            calibration_predictions = dfm.predict(X_calibration)
            test_predictions = dfm.predict(X_test)

            conformal = ConformalPredictor(confidence_levels=[0.9])
            conformal.fit(y_calibration.values, calibration_predictions)
            lower, upper = conformal.predict_interval(test_predictions, confidence_level=0.9)

            coverage = empirical_interval_coverage(y_test.values, lower, upper)
            ece = interval_calibration_error(coverage)
            interval_results.append(
                {
                    "vintage_date": vintage_date,
                    "coverage": coverage,
                    "ece": ece,
                    "avg_width": float(np.mean(upper - lower)),
                }
            )

            assert np.isfinite(lower).all()
            assert np.isfinite(upper).all()
            assert np.all(lower < upper)

        assert len(interval_results) >= 10, (
            f"Need at least 10 interval validation results, got {len(interval_results)}"
        )

        avg_coverage = float(np.mean([r["coverage"] for r in interval_results]))
        avg_ece = interval_calibration_error(avg_coverage)
        coverage_within_target = PI_COVERAGE_MIN <= avg_coverage <= PI_COVERAGE_MAX
        ece_meets_target = avg_ece < 0.05
        logger.info(
            f"\n=== DFM Calibration Summary (Bridge Features) ===\n"
            f"Vintages tested: {len(interval_results)}\n"
            f"Average 90% PI coverage: {avg_coverage:.1f}%\n"
            f"Average interval ECE: {avg_ece:.3f}\n"
            f"Coverage within target: {coverage_within_target}\n"
            f"ECE meets target: {ece_meets_target}\n"
        )

        pytest.dfm_calibration_results = interval_results
        pytest.dfm_calibration_summary = {
            "avg_coverage": avg_coverage,
            "avg_ece": avg_ece,
            "coverage_within_target": coverage_within_target,
            "ece_meets_target": ece_meets_target,
            "recommendation": (
                "calibration_pass" if coverage_within_target and ece_meets_target
                else "exclude_dfm_until_recalibrated"
            ),
        }
        assert np.isfinite(avg_coverage)
        assert np.isfinite(avg_ece)

    def test_calibration_with_ragged_edge(self, vintage_datasets: Dict[date, Dict]):
        """Missing recent source rows should not break bridge-based calibration."""
        vintage_date, data = next(iter(vintage_datasets.items()))
        target = data["target"]
        raw_sources = {
            name: frame.iloc[:-1].copy()
            for name, frame in data["raw_sources"].items()
        }
        bridge = MIDASBridge(source_configs=data["source_configs"])
        features = bridge.build_features(raw_sources, pd.DatetimeIndex(target.index), str(vintage_date))
        features = features.loc[features.index.intersection(target.index)]
        target = target.loc[features.index]

        split = split_train_calibration_test(features, target)
        X_train, X_calibration, X_test, y_train, y_calibration, _ = split
        dfm = DynamicFactorModel(n_factors=min(3, X_train.shape[1] // 2), random_state=42)
        dfm.fit(X_train, y_train, vintage_date=str(vintage_date))
        calibration_predictions = dfm.predict(X_calibration)
        test_predictions = dfm.predict(X_test)

        conformal = ConformalPredictor(confidence_levels=[0.9])
        conformal.fit(y_calibration.values, calibration_predictions)
        lower, upper = conformal.predict_interval(test_predictions, confidence_level=0.9)

        assert np.isfinite(test_predictions).all()
        assert np.isfinite(lower).all()
        assert np.isfinite(upper).all()
        assert np.all(lower < upper)


class TestMixedFrequencyRealDataPipeline:
    """Validate the R5 pipeline on 10+ real CES vintages via bridge-produced inputs."""

    def test_real_ces_bridge_pipeline_across_vintages(
        self,
        vintage_datasets: Dict[date, Dict],
    ):
        """MixedFrequencyPipeline should fit and predict on real CES bridge inputs."""
        pipeline_results = []

        for vintage_date, data in vintage_datasets.items():
            features = data["features"]
            target = data["target"]
            split_idx = int(len(target) * 0.85)
            y_train = target.iloc[:split_idx]
            y_test = target.iloc[split_idx:]

            if len(y_train) < MIN_TRAINING_SAMPLES or len(y_test) < MIN_TEST_SAMPLES:
                continue

            pipeline = MixedFrequencyPipeline(
                midas_bridge=MIDASBridge(source_configs=data["source_configs"]),
                dfm=DynamicFactorModel(
                    n_factors=min(3, features.shape[1] // 2),
                    max_iter=50,
                    random_state=42,
                ),
                xgboost=XGBoostQuantile(
                    quantiles=[0.05, 0.5, 0.95],
                    n_estimators=10,
                    max_depth=2,
                    random_state=42,
                ),
                ensemble_config=EnsembleConfig(
                    method=EnsembleMethod.WEIGHTED_AVERAGE,
                    model_names=["dfm", "midas", "xgboost"],
                    optimize_weights=True,
                ),
                pipeline_config=MixedFrequencyPipelineConfig(
                    confidence_level=0.9,
                    min_interval_width=1.0,
                    residual_scale_floor=1.0,
                ),
            )
            pipeline.fit(vintage_date, data["raw_sources"], y_train)
            predictions, intervals = pipeline.predict(
                vintage_date,
                data["raw_sources"],
                target_dates=pd.DatetimeIndex(y_test.index),
            )

            pipeline_smape = smape(y_test.values, predictions)
            pipeline_results.append(
                {
                    "vintage_date": vintage_date,
                    "smape": pipeline_smape,
                    "rmse": rmse(y_test.values, predictions),
                    "weights": pipeline.ensemble_weights_,
                }
            )

            assert pipeline.ensemble_weights_ is not None
            assert pipeline.ensemble_weights_["dfm"] >= 0.0
            assert predictions.shape == (len(y_test),)
            assert intervals.shape == (len(y_test), 2)
            assert np.isfinite(predictions).all()
            assert np.isfinite(intervals).all()
            assert np.all(intervals[:, 0] < intervals[:, 1])

        assert len(pipeline_results) >= 10, (
            f"Need at least 10 real-vintage pipeline results, got {len(pipeline_results)}"
        )
        avg_pipeline_smape = float(np.mean([r["smape"] for r in pipeline_results]))
        logger.info(
            f"\n=== Mixed-Frequency Real CES Pipeline Summary ===\n"
            f"Vintages tested: {len(pipeline_results)}\n"
            f"Average ensemble sMAPE: {avg_pipeline_smape:.2f}%\n"
            f"Average DFM optimized weight: "
            f"{np.mean([r['weights']['dfm'] for r in pipeline_results]):.3f}\n"
        )
        pytest.mixed_frequency_pipeline_results = pipeline_results
        assert np.isfinite(avg_pipeline_smape)


# ============================================================================
# Summary Report Generation
# ============================================================================


class TestDFMValidationSummary:
    """Generate comprehensive validation report for Phase 6.3.1a."""
    
    def test_generate_validation_report(
        self,
        vintage_datasets: Dict[date, Dict],
        real_vintage_dates: List[date]
    ):
        """
        Generate comprehensive DFM validation report with real data.
        """
        report_lines = [
            "=" * 70,
            "Phase 6.3.1a DFM Validation Report - REAL BLS CES DATA",
            "=" * 70,
            f"Generated: {datetime.now().isoformat()}",
            f"Vintage dates tested: {len(vintage_datasets)}",
            f"Data source: BLS CES API (real employment data)",
            "",
        ]
        
        # Run all validations
        stability_results = []
        accuracy_results = []
        comparison_results = []
        
        for vintage_date, data in vintage_datasets.items():
            features = data["features"]
            target = data["target"]
            
            split_idx = int(len(features) * 0.8)
            X_train, X_test = features.iloc[:split_idx], features.iloc[split_idx:]
            y_train, y_test = target.iloc[:split_idx], target.iloc[split_idx:]
            
            if len(X_train) < MIN_TRAINING_SAMPLES or len(X_test) < MIN_TEST_SAMPLES:
                continue
            
            vintage_str = str(vintage_date)
            result = {"vintage_date": vintage_date}
            
            try:
                # DFM
                dfm = DynamicFactorModel(
                    n_factors=min(3, X_train.shape[1] // 2),
                    random_state=42
                )
                dfm.fit(X_train, y_train, vintage_date=vintage_str)
                dfm_preds = dfm.predict(X_test)
                
                max_abs = np.abs(dfm_preds).max()
                is_stable = max_abs < STABILITY_THRESHOLD and not np.any(np.isnan(dfm_preds))
                
                result["dfm_stable"] = is_stable
                result["dfm_max_pred"] = max_abs
                
                if is_stable:
                    result["dfm_smape"] = smape(y_test.values, dfm_preds)
                    result["dfm_rmse"] = rmse(y_test.values, dfm_preds)
                
                # MIDAS
                midas = MIDASRegression(n_lags=min(10, X_train.shape[1]), random_state=42)
                midas.fit(X_train, y_train, vintage_date=vintage_str)
                midas_preds = midas.predict(X_test)
                result["midas_smape"] = smape(y_test.values, midas_preds)
                result["midas_rmse"] = rmse(y_test.values, midas_preds)
                
                # XGBoost
                xgb = XGBoostQuantile(quantiles=[0.5], n_estimators=50, random_state=42)
                xgb.fit(X_train, y_train, vintage_date=vintage_str)
                xgb_preds = xgb.predict(X_test)[0.5]
                result["xgb_smape"] = smape(y_test.values, xgb_preds)
                result["xgb_rmse"] = rmse(y_test.values, xgb_preds)
                
                comparison_results.append(result)
                
            except Exception as e:
                result["error"] = str(e)
                comparison_results.append(result)
        
        # Summarize
        total_tests = len(comparison_results)
        stable_count = sum(1 for r in comparison_results if r.get("dfm_stable", False))
        
        valid_dfm_smapes = [r["dfm_smape"] for r in comparison_results 
                           if "dfm_smape" in r and not np.isnan(r["dfm_smape"])]
        valid_midas_smapes = [r["midas_smape"] for r in comparison_results 
                             if "midas_smape" in r and not np.isnan(r["midas_smape"])]
        valid_xgb_smapes = [r["xgb_smape"] for r in comparison_results 
                           if "xgb_smape" in r and not np.isnan(r["xgb_smape"])]
        
        avg_dfm_smape = np.mean(valid_dfm_smapes) if valid_dfm_smapes else float('nan')
        avg_midas_smape = np.mean(valid_midas_smapes) if valid_midas_smapes else float('nan')
        avg_xgb_smape = np.mean(valid_xgb_smapes) if valid_xgb_smapes else float('nan')
        
        dfm_meets_accuracy = avg_dfm_smape < SMAPE_THRESHOLD if not np.isnan(avg_dfm_smape) else False
        all_stable = stable_count == total_tests
        
        report_lines.extend([
            "STABILITY RESULTS:",
            f"  - Total vintages tested: {total_tests}",
            f"  - DFM stable predictions: {stable_count}/{total_tests} ({100*stable_count/total_tests:.0f}%)",
            f"  - All stable: {all_stable}",
            "",
            "ACCURACY RESULTS (sMAPE):",
            f"  - Average DFM sMAPE: {avg_dfm_smape:.2f}%" if not np.isnan(avg_dfm_smape) else "  - Average DFM sMAPE: N/A (unstable)",
            f"  - Average MIDAS sMAPE: {avg_midas_smape:.2f}%",
            f"  - Average XGBoost sMAPE: {avg_xgb_smape:.2f}%",
            f"  - Threshold: {SMAPE_THRESHOLD}%",
            f"  - DFM meets threshold: {dfm_meets_accuracy}",
            "",
            "=" * 70,
            "RECOMMENDATION:",
        ])
        
        if all_stable and dfm_meets_accuracy:
            report_lines.append("  ✅ INCLUDE DFM in production ensemble")
            report_lines.append("  - DFM is numerically stable")
            report_lines.append(f"  - DFM meets accuracy threshold (sMAPE < {SMAPE_THRESHOLD}%)")
        elif stable_count > total_tests * 0.8 and dfm_meets_accuracy:
            report_lines.append("  ⚠️ CONSIDER DFM with caution")
            report_lines.append(f"  - DFM stable in {stable_count}/{total_tests} vintages")
            report_lines.append("  - May need monitoring in production")
        else:
            report_lines.append("  ❌ EXCLUDE DFM from production ensemble")
            if not all_stable:
                report_lines.append(f"  - DFM shows numerical instability ({stable_count}/{total_tests} stable)")
            if not dfm_meets_accuracy:
                report_lines.append(f"  - DFM accuracy below threshold (sMAPE: {avg_dfm_smape:.2f}% > {SMAPE_THRESHOLD}%)")
        
        report_lines.append("=" * 70)
        
        # Print report
        report = "\n".join(report_lines)
        logger.info(f"\n{report}")
        
        # Store detailed results
        pytest.dfm_final_report = {
            "total_vintages": total_tests,
            "stable_count": stable_count,
            "avg_dfm_smape": avg_dfm_smape,
            "avg_midas_smape": avg_midas_smape,
            "avg_xgb_smape": avg_xgb_smape,
            "recommendation": "include" if (all_stable and dfm_meets_accuracy) else "exclude",
            "details": comparison_results,
        }
        
        assert True  # Report generation always passes

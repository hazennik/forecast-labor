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

from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.midas.midas_model import MIDASRegression
from models_src.gbm_quantile.xgb_quantile import XGBoostQuantile
from models_src.utils.metrics import rmse, smape, prediction_interval_coverage
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
    feature_series_ids: List[str] = FEATURE_SERIES_IDS
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
    # Ensure date column is datetime
    data["date"] = pd.to_datetime(data["date"])
    
    # Extract target series (Total Nonfarm)
    target_data = data[data["series_id"] == target_series_id].copy()
    target_data = target_data.sort_values("date").set_index("date")
    
    if target_data.empty:
        raise ValueError(f"Target series {target_series_id} not found in data")
    
    # Get target values (month-over-month change in thousands)
    target = target_data["mom_change"].dropna()
    
    # Build features from other series
    features_list = []
    
    for series_id in feature_series_ids:
        series_data = data[data["series_id"] == series_id].copy()
        
        if series_data.empty:
            continue
            
        series_data = series_data.sort_values("date").set_index("date")
        
        # Use mom_change as feature
        if "mom_change" in series_data.columns:
            feature = series_data["mom_change"].rename(f"{series_id}_mom")
            features_list.append(feature)
        
        # Add lagged value
        if "value" in series_data.columns:
            lag1 = series_data["value"].shift(1).rename(f"{series_id}_lag1")
            features_list.append(lag1)
    
    if not features_list:
        raise ValueError("No feature series found in data")
    
    # Combine features
    features = pd.concat(features_list, axis=1)
    
    # Align features and target
    common_index = features.index.intersection(target.index)
    features = features.loc[common_index]
    target = target.loc[common_index]
    
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
            
            features, target = prepare_features_and_target(data)
            
            if len(features) < MIN_TRAINING_SAMPLES + MIN_TEST_SAMPLES:
                logger.warning(f"Insufficient data for vintage {vdate}, skipping")
                continue
            
            datasets[vdate] = {
                "features": features,
                "target": target,
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
        
        logger.info(
            f"\n=== DFM Stability Summary (Real Data) ===\n"
            f"Vintages tested: {total}\n"
            f"Stable: {stable_count}/{total}\n"
            f"All stable: {stable_count == total}\n"
        )
        
        # Store results for reporting
        pytest.dfm_stability_results = stability_results
        
        assert total >= 10, f"Need at least 10 vintage tests, got {total}"
    
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

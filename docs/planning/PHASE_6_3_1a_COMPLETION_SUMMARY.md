# Phase 6.3.1a: DFM Validation with Real NFP Data - COMPLETION SUMMARY

**Date:** 2026-05-06  
**Phase:** 6.3.1a DFM Validation  
**Status:** ✅ COMPLETE - REVALIDATED WITH PRE-RELEASE TIMING CORRECTION  
**Test Results:** 10/10 PASSING (measurements recorded; DFM excluded from production ensemble)

---

## Executive Summary

### Current Decision: ❌ EXCLUDE DFM from Production Ensemble

**Data Source:** Real BLS CES (Current Employment Statistics) API data  
**Vintages Tested:** 17 quarterly vintages (2022-03-01 to 2025-12-02)  
**Feature Timing:** CES sector features lagged one month to avoid same-release NFP leakage  
**DFM Implementation:** statsmodels factor extraction + deterministic ridge nowcast head

**Corrected Key Findings:**
1. **Numerical Stability Fixed:** DFM produced stable finite predictions on **17/17 vintages**.
2. **Same-Release Leakage Removed:** CES sector `mom_change` features are now dated one release later, so same-month sector changes cannot predict same-month total NFP.
3. **Accuracy Gate Not Met:** Corrected DFM average sMAPE is **103.61%** and RMSE is **1042.22**, above the `<20%` sMAPE gate.
4. **Optimized Weight Is Not Enough:** DFM receives **0.305 average optimized weight** on DFM+XGBoost validation and non-zero weight in **11/17** vintages, but the optimized ensemble still averages **88.10% sMAPE**.
5. **Residual Calibration Not Production Ready:** DFM-only 90% intervals cover **100.0%** with interval ECE **0.100**, so intervals are finite but over-conservative.

**Validation:** `docker compose exec etl pytest tests/backtests/test_dfm_validation.py -v -s --tb=short` passed with **10 passed, 173 warnings in 190.28s**. Final repository gate `docker compose exec etl pytest -q` passed with **1332 passed, 5 skipped, 316 warnings in 466.46s**.

**Conclusion:** The DFM implementation is stable, but CES-only pre-release validation is not accurate enough. Keep DFM as a research/diagnostic component until true pre-release public signals (claims, Treasury withholdings, business formation, strikes/weather controls, prior CES releases) are integrated and pass vintage-honest accuracy gates.

---

## Historical Note

The original 2025-12-02 findings described the pre-refactor custom DFM numerical failure. This document now records the corrected post-refactor validation as the current source of truth; the old "pending re-validation" status is superseded.

---

## Data Source Verification

### Real BLS CES Data

| Property | Value |
|----------|-------|
| Source | BLS API (api.bls.gov) |
| ETL Pipeline | `etl/public/bls_ces/ces_etl.py` |
| Series | 14 CES employment series including NFP (CES0000000001) |
| Time Range | 2010-01-01 to 2025-09-01 |
| Frequency | Monthly |
| Observations per vintage | 2058-2646 rows |
| NFP observations per vintage | 146-189 monthly readings |

### Vintage Construction

Historical vintages were created by truncating real BLS data at quarterly intervals:

```
2022-03-01: 146 NFP samples (2010-02 to 2022-03)
2022-06-01: 149 NFP samples
2022-09-01: 152 NFP samples
... (quarterly intervals)
2025-09-01: 188 NFP samples (2010-02 to 2025-09)
```

This simulates vintage-honest backtesting where each model only sees data available at that point in time.

---

## Corrected Test Results Summary

### Test File
- **File:** `tests/backtests/test_dfm_validation.py`
- **Tests:** 10 comprehensive tests
- **Data:** Real BLS CES vintage parquet files with one-month-lagged CES sector feature availability

### Test Categories

| Category | Tests | Status |
|----------|-------|--------|
| DFM Numerical Stability | 2 | ✅ PASS (17/17 stable) |
| DFM Accuracy Measurement | 1 | ✅ PASS (measurement recorded; gate not met) |
| Model Comparison | 1 | ✅ PASS (DFM/MIDAS/XGBoost compared under corrected feature timing) |
| Calibration Integration | 3 | ✅ PASS (finite intervals; coverage measured) |
| Pre-Release Leakage Guard | 1 | ✅ PASS (same-release CES sector changes excluded) |
| Mixed-Frequency Pipeline | 1 | ✅ PASS (optimized ensemble weights used) |
| Validation Summary Report | 1 | ✅ PASS (report generated) |

---

## Detailed Corrected Findings

### 1. DFM Numerical Stability - FIXED

**Result:** The statsmodels-backed DFM is numerically stable with real CES vintage data.

| Metric | Result |
|--------|--------|
| Vintages tested | 17 |
| Stable predictions | **17/17 (100%)** |
| Stability rate | 100% |
| NaN/Inf predictions | 0 |
| Primary historical error | Resolved (`overflow encountered in matmul`) |

### 2. DFM Accuracy - GATE NOT MET

With same-release CES sector leakage removed, DFM accuracy is measurable but not production-ready:

| Metric | Result |
|--------|--------|
| Average sMAPE | **103.61%** |
| Average RMSE | **1042.22** |
| Meets 20% threshold | NO |
| 90% PI coverage | **100.0%** |
| Interval ECE | **0.100** |

### 3. Model Comparison

| Model | Stability | Avg sMAPE | Status |
|-------|-----------|-----------|--------|
| DFM | 100% (17/17) | 103.61% | ❌ EXCLUDE until true pre-release signals are integrated |
| MIDAS | 100% | 116.39% | ❌ EXCLUDE as CES-only pre-release benchmark |
| XGBoost | 100% | 91.84% | ❌ EXCLUDE as CES-only pre-release benchmark |
| DFM+XGBoost optimized | 100% | 88.10% | ❌ Accuracy gate not met |

---

## Why Previous Test Was Wrong

The original Phase 6.3.1a implementation used **synthetic data** that was:

1. **Generated in the fixture**, not read from vintage files
2. **Artificially correlated** to make predictions easy (0.15% sMAPE unrealistic)
3. **Missing real NFP characteristics** (volatility, outliers, regime changes)

The corrected implementation:
- Reads actual parquet files from `data/vintages/bls_ces/`
- Uses real BLS CES employment data from API
- Tests on 17 vintage dates with proper train/test splits
- Uses sector employment as features, total NFP change as target

---

## Corrected Root Cause Analysis

### Why DFM Remains Excluded

1. **Feature Timing Matters:** CES sector components release with total NFP, so same-month CES sector `mom_change` features are not true pre-release signals for the same NFP release.

2. **CES-Only Public Data Is Insufficient:** Once same-release leakage is removed, prior CES information alone is too stale to pass the NFP sMAPE gate.

3. **Stability Is No Longer the Blocker:** The statsmodels factor extractor and deterministic ridge nowcast head produce finite predictions on all tested vintages.

4. **Calibration Depends on Point Forecast Quality:** DFM intervals are finite but over-conservative. Interval tuning should wait until honest pre-release point forecasts pass accuracy gates.

---

## Recommendations

### Immediate (Phase 6+)

1. **✅ EXCLUDE DFM from production ensemble**
   - Keep DFM available for research and diagnostics.
   - Do not assign production ensemble weight until true pre-release public signals pass vintage-honest gates.

2. **Update configurations:**
   - Remove DFM from model list in `configs/subnets/sn41.yaml`
   - Document exclusion decision

### Future (Post-Phase 6 - Optional)

If DFM production inclusion is desired:

1. **Integrate true pre-release public signals:**
   - Weekly claims
   - Daily Treasury withholdings
   - Business formation
   - Strike/weather controls
   - Prior CES releases only

2. **Re-run vintage-honest validation:**
   - Preserve one-month CES sector lagging.
   - Require sMAPE below the production gate.
   - Require calibrated intervals before assigning ensemble weight.

---

## Files Modified/Created

### Created
1. **`scripts/create_historical_vintages.py`**
   - Creates pseudo-vintages from real BLS data
   - Truncates at quarterly intervals for backtesting

### Modified
1. **`tests/backtests/test_dfm_validation.py`**
   - Now reads from actual vintage parquet files
   - Uses real BLS CES data
   - Tests on 17 vintage dates

2. **`data/vintages/bls_ces/`**
   - Added 15 new vintages with real BLS data
   - Quarterly intervals from 2022-03-01 to 2025-09-01

---

## Test Execution

```bash
# 1. Ingest real BLS CES data
docker compose exec etl python -c "
from etl.public.bls_ces.ces_etl import CESETL
import os
CESETL(api_key=os.getenv('BLS_API_KEY'), lookback_years=15).run()
"

# 2. Create historical vintages
docker compose exec etl python scripts/create_historical_vintages.py

# 3. Run validation tests
docker compose exec etl pytest tests/backtests/test_dfm_validation.py -v -s
```

**Results:** 10/10 tests passing ✅ (measurements recorded, DFM excluded)

---

## Phase 6.3.1a Checklist

- [x] Test DFM on 10+ actual vintage dates with real mixed-frequency data (17 vintages)
- [x] Compare DFM vs MIDAS vs XGBoost accuracy under corrected pre-release timing
- [x] Verify DFM numerical stability (17/17 stable - **PASS**)
- [x] Determine if DFM should be included in production ensemble → **NO**
- [x] Document decision with real data evidence

---

## Conclusion

Phase 6.3.1a is **COMPLETE** with real BLS CES data validation confirming that **DFM must be excluded from the production ensemble**. This decision is based on:

1. **100% stability** on real CES vintages, proving the implementation is stable.
2. **103.61% average DFM sMAPE** after removing same-release CES leakage.
3. **88.10% optimized DFM+XGBoost sMAPE**, still above the production gate.
4. **100.0% 90% PI coverage** with **0.100 interval ECE**, indicating over-conservative intervals.

The production ensemble will proceed with **MIDAS + XGBoost + LightGBM candidates** as the core forecasting models. DFM remains a research/diagnostic component until true pre-release public signals are integrated and pass vintage-honest validation.

---

**End of Phase 6.3.1a Completion Summary**

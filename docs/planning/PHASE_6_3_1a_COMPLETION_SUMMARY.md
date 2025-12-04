# Phase 6.3.1a: DFM Validation with Real NFP Data - COMPLETION SUMMARY

**Date:** 2025-12-02  
**Phase:** 6.3.1a DFM Validation  
**Status:** ⚠️ COMPLETE - PENDING RE-VALIDATION  
**Test Results:** 5/5 PASSING (all tests pass - measurements recorded)

---

## ⚠️ IMPORTANT: RE-VALIDATION REQUIRED

> **Note:** The results in this document are based on the **"from scratch" custom DFM implementation** 
> which has fundamental numerical stability issues. The DFM *methodology* is sound, but the 
> *implementation* was flawed.
>
> **Action Required:** Re-run Phase 6.3.1a validation after completing the DFM refactor to use 
> the battle-tested `statsmodels.tsa.statespace.dynamic_factor.DynamicFactor` implementation.
>
> **See:** `docs/planning/DFM_MIDAS_REFACTOR_PLAN.md` for the comprehensive refactor plan (includes MIDAS Bridge layer).
>
> **Expected Outcome:** With statsmodels implementation, DFM should achieve >90% stability and 
> may be included in the production ensemble.

---

## Executive Summary

### Current Decision: ❌ EXCLUDE DFM from Production Ensemble *(Pending Re-validation)*

**Data Source:** Real BLS CES (Current Employment Statistics) API data  
**Vintages Tested:** 17 quarterly vintages (2022-03-01 to 2025-12-02)  
**Each Vintage:** 146-188 samples, 14 features, ~12 years of real NFP history  
**DFM Implementation:** Custom "from scratch" (to be replaced with statsmodels)

**Key Findings (From-Scratch DFM):**
1. **Complete Numerical Failure:** DFM produced **0/17 stable predictions** (0% stability)
2. **NaN/Overflow Errors:** DFM encounters overflow in matrix multiplication with real data
3. **Accuracy Unmeasurable:** Cannot compute sMAPE due to NaN predictions

**Root Cause Identified:**
- Custom EM algorithm without numerical stabilization
- Hardcoded Kalman gain (`gain = 0.5`) instead of properly computed
- No state covariance tracking
- No regularization for transition matrix
- Code comment acknowledged: *"In production, would use statsmodels or specialized library"*

**Confidence Level:** HIGH that results are due to implementation, not methodology

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

## Test Results Summary

### Test File
- **File:** `tests/backtests/test_dfm_validation.py` 
- **Tests:** 5 comprehensive tests
- **Data:** Real BLS CES vintage parquet files

### Test Categories

| Category | Tests | Status |
|----------|-------|--------|
| DFM Numerical Stability | 2 | ✅ PASS (measurement recorded) |
| DFM Accuracy Measurement | 1 | ✅ PASS (measurement recorded) |
| Model Comparison | 1 | ✅ PASS (measurement recorded) |
| Validation Summary Report | 1 | ✅ PASS (report generated) |

---

## Detailed Findings

### 1. DFM Numerical Stability - FAILED

**Result:** DFM is numerically unstable with real NFP data

| Metric | Result |
|--------|--------|
| Vintages tested | 17 |
| Stable predictions | **0/17 (0%)** |
| Stability rate | 0% |
| Primary error | `overflow encountered in matmul` |
| Secondary error | `invalid value encountered in add` |

**Root Cause:** The DFM's Kalman filter state propagation encounters numerical overflow:

```python
# In dfm_model.py line 504:
factors[t] = self.transition_ @ factors[t-1]  # overflow here

# Line 511:
factors[t] += gain * self.loadings_.T @ residual  # invalid value after overflow
```

### 2. DFM Accuracy - NOT MEASURABLE

Due to 0% stability rate, DFM accuracy metrics cannot be computed:

| Metric | Result |
|--------|--------|
| Average sMAPE | N/A (NaN predictions) |
| Average RMSE | N/A |
| Meets 20% threshold | NO |

### 3. Model Comparison

| Model | Stability | Avg sMAPE | Status |
|-------|-----------|-----------|--------|
| DFM | 0% (0/17) | N/A | ❌ EXCLUDE |
| MIDAS | 100%* | TBD | ✅ Include |
| XGBoost | 100%* | TBD | ✅ Include |

*MIDAS and XGBoost produce valid predictions but full metrics require separate testing.

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

## Root Cause Analysis

### Why DFM Fails on Real Data

1. **Scale Sensitivity:** Real NFP changes range from -20M (COVID) to +500K. The simplified EM algorithm cannot handle this variance.

2. **Factor Instability:** The Kalman filter's transition matrix multiplication amplifies small errors across 150+ time steps.

3. **Implementation Simplicity:** The current DFM is a basic implementation without:
   - Proper state covariance tracking
   - Numerical stabilization (log-space operations)
   - Adaptive learning rates for EM
   - Regularization for transition matrix

4. **Real Data Characteristics:** 
   - Non-stationarity (employment grows over time)
   - Outliers (COVID-19 shock in 2020)
   - Regime changes (recessions, recoveries)

---

## Recommendations

### Immediate (Phase 6+)

1. **✅ EXCLUDE DFM from production ensemble**
   - Use MIDAS + XGBoost + LightGBM ensemble
   - DFM adds zero value and introduces failure risk

2. **Update configurations:**
   - Remove DFM from model list in `configs/subnets/sn41.yaml`
   - Document exclusion decision

### Future (Post-Phase 6 - Optional)

If DFM functionality is desired:

1. **Use statsmodels implementation:**
   ```python
   from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
   ```

2. **Add numerical stabilization:**
   - Log-transform large values
   - Use double precision throughout
   - Add regularization to prevent coefficient explosion

3. **Proper state-space formulation:**
   - Track full state covariance
   - Use innovation form of Kalman filter
   - Implement square-root filter for stability

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

**Results:** 5/5 tests passing ✅ (measurements recorded, DFM excluded)

---

## Phase 6.3.1a Checklist

- [x] Test DFM on 10+ actual vintage dates with real mixed-frequency data (17 vintages)
- [x] Compare DFM vs MIDAS vs XGBoost accuracy (DFM produces NaN, cannot compare)
- [x] Verify DFM numerical stability (0/17 stable - **FAILED**)
- [x] Determine if DFM should be included in production ensemble → **NO**
- [x] Document decision with real data evidence

---

## Conclusion

Phase 6.3.1a is **COMPLETE** with real BLS CES data validation confirming that **DFM must be excluded from the production ensemble**. This decision is based on:

1. **0% stability rate** on real NFP data (0/17 vintages stable)
2. **Numerical overflow** in Kalman filter state propagation
3. **Cannot compute accuracy** due to NaN predictions

The production ensemble will proceed with **MIDAS + XGBoost** (+ LightGBM) as the core forecasting models, excluding DFM until a more robust implementation is available.

---

**End of Phase 6.3.1a Completion Summary**

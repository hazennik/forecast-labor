# DFM + MIDAS Bridge Refactor Plan (Option C)
## Hybrid Architecture: True Mixed-Frequency Support

**Date Created:** 2025-12-04  
**Status:** 📋 PLANNED  
**Priority:** HIGH (Architectural Debt Resolution + Capability Gap Closure)  
**Estimated Effort:** 32-40 hours  
**Reference:** Phase 6.3.1a findings, 5_PILLARS.md, FORECASTING_CAPABILITIES.md, ACCURACY_MAP.md, `.cursorrules`

---

## Executive Summary

### Problem Statement

**Two critical gaps exist in the current architecture:**

| Gap | Component | Current State | Required State |
|-----|-----------|---------------|----------------|
| **Gap 1** | DFM | Custom "from scratch" → 0% stability on real data | Stable, production-ready |
| **Gap 2** | MIDAS Bridge | Does NOT exist (components disconnected) | True frequency bridging |

**Current Architecture (Broken):**
```
Raw Data (D/W/M) → Pre-aggregated Features → Models (MIDAS, DFM, XGB)
                        ↑
                   Manual aggregation
                   NO frequency bridging
                   NO ragged-edge handling
```

**Target Architecture (Option C):**
```
Raw Data → MIDAS Bridge Layer → Monthly Features → DFM → Ensemble
           (D/W → M bridging)   (clean aligned)   (stable)
           
Daily Treasury ──┐
                 ├──→ MIDAS Bridge ──→ Bridged Features ──→ DFM (statsmodels)
Weekly Claims ───┘                                              │
                                                                 ↓
Monthly BLS CES ───────────────────────────────────────→ XGBoost ──→ Ensemble
```

### Solution Overview

| Phase | Purpose | Deliverable | Est. Time |
|-------|---------|-------------|-----------|
| **R1** | Assessment | Baseline state documented | 2-3 hours |
| **R2** | MIDAS Bridge TDD | Tests written BEFORE implementation | 4-5 hours |
| **R3** | MIDAS Bridge Impl | True frequency bridging layer | 4-5 hours |
| **R4** | DFM Stabilization | statsmodels-based DFM | 4-5 hours |
| **R5** | Integration Layer | End-to-end pipeline | 3-4 hours |
| **R6** | Test Validation | All tests passing | 3-4 hours |
| **R7** | Real Data Validation | Phase 6.3.1a re-run with real data | 2-3 hours |
| **R8** | Documentation | All docs updated | 3-4 hours |
| **R9** | Cleanup & Finalization | Production-ready | 2-3 hours |

### Impact Scope

| Category | Files | Lines | Tests |
|----------|-------|-------|-------|
| **MIDAS Source** | 2 | ~870 | ~60 |
| **DFM Source** | 3 | ~1,072 | ~64 |
| **Integration/Pipeline** | 4 | ~400 | ~20 |
| **Feature Engineering** | 2 | ~200 | ~15 |
| **Documentation** | 30+ | ~500 mentions | N/A |

### Phase 5 Impact Assessment

**This refactor does NOT require reimplementation of Phases 1-5.**

| Impact Area | Tests Requiring Updates | Phase 5 Rework |
|-------------|-------------------------|----------------|
| DFM tests | ~50-70 (of ~200 model tests) | 15-20% effort |
| state_space tests | ~26 (evaluate, may skip) | Minimal |
| Integration tests | ~15-20 affected | Updates, not rewrites |

**Components Unaffected:**
- ✅ Calibration (`models_src/calibration/`) — unchanged
- ✅ Revision modeling (`models_src/revision/`) — unchanged  
- ✅ MinT reconciliation (`recon/mint/`) — unchanged
- ✅ GBM/LightGBM models — unchanged
- ✅ ETL pipelines — unchanged
- ✅ Feature transforms — unchanged (MIDASLagConstructor reused)

**Scope Clarification:**
This refactor provides **infrastructure** for mixed-frequency nowcasting (MIDAS Bridge + stable DFM). Probability calibration, revision modeling, and state/sector reconciliation remain fully operational and are exercised during Phase 6.3+ validation.

---

## Table of Contents

1. [Phase R1: Pre-Refactor Assessment](#phase-r1-pre-refactor-assessment)
2. [Phase R2: MIDAS Bridge Layer TDD](#phase-r2-midas-bridge-layer-tdd)
3. [Phase R3: MIDAS Bridge Layer Implementation](#phase-r3-midas-bridge-layer-implementation)
4. [Phase R4: DFM Stabilization with statsmodels](#phase-r4-dfm-stabilization-with-statsmodels)
5. [Phase R5: Integration Layer](#phase-r5-integration-layer)
6. [Phase R6: Unit & Integration Test Validation](#phase-r6-unit--integration-test-validation)
7. [Phase R7: Real Data Validation](#phase-r7-real-data-validation)
8. [Phase R8: Documentation Update](#phase-r8-documentation-update)
9. [Phase R9: Final Validation & Cleanup](#phase-r9-final-validation--cleanup)
10. [Appendix A: Complete Files Inventory](#appendix-a-complete-files-inventory)
11. [Appendix B: Test Inventory](#appendix-b-test-inventory)
12. [Appendix C: Rollback Plan](#appendix-c-rollback-plan)
13. [Appendix D: Capability Alignment Matrix](#appendix-d-capability-alignment-matrix)

---

## Phase R1: Pre-Refactor Assessment

**Purpose:** Document current state, identify all affected components, create backups  
**Estimated Time:** 2-3 hours  
**Blocking:** None  
**TDD:** N/A (assessment only)

### R1.1 Current State Documentation

#### R1.1.1 MIDAS Component Audit
- [ ] Run all MIDAS tests and record results
  ```bash
  docker compose exec etl pytest tests/models/test_midas.py tests/models/test_midas_properties.py tests/features/test_midas_lags.py -v --tb=short
  ```
- [ ] Document current MIDAS interface
  - `MIDASRegression.fit(X, y, vintage_date)` — X is pre-aggregated features, NOT raw data
  - `MIDASLagConstructor.construct_lags(series, target_dates)` — creates lags but NOT integrated
- [ ] Verify MIDAS components are NOT connected
  - Check: No imports of `MIDASLagConstructor` in `MIDASRegression`
  - Check: No pipeline code that chains them together

#### R1.1.2 DFM Component Audit
- [ ] Run all DFM tests and record results
  ```bash
  docker compose exec etl pytest tests/models/test_dfm.py tests/models/test_dfm_properties.py tests/models/test_dfm_state_space.py -v --tb=short
  ```
- [ ] Run Phase 6.3.1a validation tests
  ```bash
  docker compose exec etl pytest tests/backtests/test_dfm_validation.py -v -s
  ```
  - Record: 0% stability rate with real data
- [ ] Document current DFM interface
  - List all public methods: `__init__`, `fit`, `predict`, `get_params`, `save`, `load`
  - List all constructor parameters
  - List all fitted attributes

#### R1.1.3 ETL Data Sources Audit
- [ ] Verify available data sources and frequencies

  | Source | Frequency | ETL File | Status |
  |--------|-----------|----------|--------|
  | Treasury Withholdings | Daily | `etl/public/treasury_withholdings/treasury_etl.py` | ✅ Working |
  | UI Claims | Weekly | `etl/public/claims/claims_etl.py` | ✅ Working |
  | BLS CES (NFP) | Monthly | `etl/public/bls_ces/ces_etl.py` | ✅ Working |
  | BLS LAUS | Monthly | `etl/public/bls_laus/laus_etl.py` | ✅ Working |

#### R1.1.4 Integration Point Audit
- [ ] Identify all files that import MIDAS or DFM
  - `models_src/pipelines/ensemble_pipeline.py`
  - `models_src/pipelines/train_pipeline.py`
  - `tests/integration/test_etl_features_models.py`
  - `tests/integration/test_complete_workflow.py`
  - `scripts/build_features.py`

### R1.2 Backup Current Implementation

#### R1.2.1 Create Backup Branch
- [ ] Create backup branch
  ```bash
  git checkout -b backup/midas-dfm-pre-refactor
  git push origin backup/midas-dfm-pre-refactor
  git checkout main
  ```

#### R1.2.2 Archive Current Files
- [ ] Create archive directory
  ```bash
  mkdir -p docs/planning/archived/midas_dfm_pre_refactor
  ```
- [ ] Copy current implementations for reference:
  ```bash
  cp models_src/dfm/dfm_model.py docs/planning/archived/midas_dfm_pre_refactor/
  cp models_src/dfm/state_space.py docs/planning/archived/midas_dfm_pre_refactor/
  cp models_src/midas/midas_model.py docs/planning/archived/midas_dfm_pre_refactor/
  cp features/midas/lag_constructor.py docs/planning/archived/midas_dfm_pre_refactor/
  ```

### R1.3 Verify Dependencies

#### R1.3.1 statsmodels Availability
- [ ] Verify statsmodels in `requirements.txt`
  ```bash
  grep statsmodels requirements.txt
  ```
- [ ] Verify `statsmodels.tsa.statespace.dynamic_factor.DynamicFactor` available
  ```bash
  docker compose exec etl python -c "from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor; print('OK')"
  ```
- [ ] Test basic statsmodels DynamicFactor usage in Docker
  ```bash
  docker compose exec etl python -c "
  import numpy as np
  from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
  X = np.random.randn(100, 5)
  model = DynamicFactor(X, k_factors=2, factor_order=1)
  results = model.fit(disp=False)
  print(f'Factors shape: {results.factors.filtered.shape}')
  print('statsmodels DynamicFactor working!')
  "
  ```

### R1.4 Gate Check: Pre-Refactor

| Criterion | Required | Status |
|-----------|----------|--------|
| MIDAS baseline tests recorded | Yes | [ ] |
| DFM baseline tests recorded | Yes | [ ] |
| ETL data sources verified | Yes | [ ] |
| Integration points documented | Yes | [ ] |
| Backup branch created | Yes | [ ] |
| statsmodels available | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R2 until all R1 tasks are complete.**

---

## Phase R2: MIDAS Bridge Layer TDD

**Purpose:** Write tests FIRST that define expected behavior for the MIDAS Bridge  
**Estimated Time:** 4-5 hours  
**Blocking:** Phase R1 complete  
**TDD:** ✅ Tests written BEFORE implementation

### R2.1 Design MIDAS Bridge Architecture

#### R2.1.1 Define Bridge Interface
The MIDAS Bridge must:
1. Ingest raw high-frequency data (daily, weekly) from ETL
2. Align to monthly target dates using MIDAS methodology
3. Apply Almon polynomial weighting during alignment
4. Handle ragged-edge (missing recent data) gracefully
5. Output monthly-frequency feature matrix ready for DFM/XGBoost

**Target Interface:**
```python
class MIDASBridge:
    def build_features(
        self,
        vintage_date: date,
        target_dates: pd.DatetimeIndex,  # Monthly dates to predict
        raw_sources: Dict[str, pd.Series]  # {source_name: raw_series}
    ) -> pd.DataFrame:  # Monthly-aligned feature matrix
        ...
```

#### R2.1.2 Define Data Flow

**Data Source:** `VintageManager` (`etl/common/vintage.py`) provides raw vintage data.  
**Orchestration:** `VintageHarness` (`backtests/vintage_harness/harness.py`) for backtest coordination.

```
VintageManager.load_vintage(source, date)
    │
    ├── Treasury (daily) ──┐
    │                      │
    ├── Claims (weekly) ───┼──→ MIDASBridge ──→ Monthly Features ──→ DFM/XGBoost
    │                      │
    └── BLS CES (monthly) ─┘
```

**VintageManager Interface:**
```python
class VintageManager:
    def load_vintage(source_name: str, vintage_date: date) -> pd.DataFrame
    def list_vintages(source_name: str) -> List[date]
    def get_vintage_as_of(source_name: str, as_of_date: date) -> pd.DataFrame
```

### R2.2 Create MIDAS Bridge Test File

#### R2.2.1 Create `tests/features/test_midas_bridge.py`
Tests to define (TDD - write before implementation):

**Interface Tests:**
- [ ] `test_bridge_accepts_raw_high_frequency_data`
- [ ] `test_bridge_outputs_monthly_aligned_features`
- [ ] `test_bridge_handles_daily_to_monthly_conversion`
- [ ] `test_bridge_handles_weekly_to_monthly_conversion`
- [ ] `test_bridge_applies_almon_weighting`

**Ragged-Edge Tests:**
- [ ] `test_bridge_handles_missing_recent_daily_data`
- [ ] `test_bridge_handles_missing_recent_weekly_data`
- [ ] `test_bridge_forward_fills_gaps_correctly`
- [ ] `test_bridge_marks_data_availability`

**Integration Tests:**
- [ ] `test_bridge_integrates_with_vintage_manager`
- [ ] `test_bridge_produces_dfm_compatible_output`
- [ ] `test_bridge_produces_xgboost_compatible_output`

**Stability Tests:**
- [ ] `test_bridge_handles_large_values_treasury`
- [ ] `test_bridge_handles_covid_shock_claims`
- [ ] `test_bridge_deterministic_output`

**Almon Weight Behavior Tests:**
- [ ] `test_almon_weights_sum_to_one` — Weights must sum to 1.0
- [ ] `test_almon_weights_decay_pattern` — Recent lags have higher weight
- [ ] `test_almon_degree_affects_weight_shape` — Different degrees produce different shapes
- [ ] `test_almon_weights_with_large_n_lags` — Edge case: 50+ lags
- [ ] `test_almon_weights_numerical_stability` — No NaN/Inf with extreme degrees

**Note:** Some Almon tests already exist in `tests/features/test_midas_lags.py` (`test_almon_polynomial_weights`, `test_equal_weights_when_almon_disabled`). The new tests provide more explicit coverage.

#### R2.2.2 Run Tests to Confirm Failure (TDD Red Phase)
- [ ] Run tests
  ```bash
  docker compose exec etl pytest tests/features/test_midas_bridge.py -v
  ```
- [ ] Expected: All tests fail (ImportError or NotImplemented)
- [ ] Record failure count

### R2.3 Define MIDASBridge Acceptance Criteria

| Criterion | Threshold | Test Method |
|-----------|-----------|-------------|
| Frequency bridging works | D→M, W→M | Unit tests |
| Ragged-edge handled | No NaN in output | Ragged tests |
| Almon weights applied | Weights sum to 1.0 | Weight tests |
| DFM compatible output | Shape matches | Integration tests |
| Deterministic | Same input = same output | Reproducibility tests |

### R2.4 Gate Check: MIDAS Bridge TDD

| Criterion | Required | Status |
|-----------|----------|--------|
| Bridge architecture designed | Yes | [ ] |
| Test file created | Yes | [ ] |
| All tests fail (red phase) | Yes | [ ] |
| Acceptance criteria defined | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R3 until all R2 tasks are complete.**

---

## Phase R3: MIDAS Bridge Layer Implementation

**Purpose:** Implement the MIDAS Bridge to make tests pass  
**Estimated Time:** 4-5 hours  
**Blocking:** Phase R2 complete  
**TDD:** ✅ Implementation to make tests pass (Green phase)

### R3.1 Create MIDAS Bridge Module

#### R3.1.1 Create `features/midas/bridge.py`

**Note:** `MIDASLagConstructor` already exists at `features/midas/lag_constructor.py` with full functionality:
- ✅ Daily → Monthly alignment
- ✅ Weekly → Monthly alignment
- ✅ Almon polynomial weighting (`_compute_almon_weights`)
- ✅ Ragged-edge handling
- ✅ Deterministic output

The `MIDASBridge` will **reuse** `MIDASLagConstructor` internally, not reimplement it.

**Existing MIDASLagConstructor Interface:**
```python
class MIDASLagConstructor:
    def __init__(
        self,
        source_freq: Literal["D", "W"],     # Daily or Weekly
        target_freq: Literal["W", "M"],      # Weekly or Monthly
        n_lags: int,                         # Number of lags
        almon_poly_degree: int = 2,          # Almon polynomial degree
        apply_weights: bool = False,         # Apply weights to lags
    )
    
    def construct_lags(series: pd.Series, target_dates: pd.DatetimeIndex) -> pd.DataFrame
    def _compute_almon_weights(n_lags: int, degree: int) -> np.ndarray
```

**New MIDASBridge Structure:**
```python
class MIDASBridge:
    """
    MIDAS Bridge for true mixed-frequency data fusion.
    
    Ingests raw high-frequency data (daily, weekly) and produces
    monthly-aligned features suitable for DFM and ensemble models.
    """
    
    def __init__(
        self,
        daily_n_lags: int = 20,
        weekly_n_lags: int = 8,
        almon_degree: int = 2,
        handle_ragged: bool = True
    ):
        ...
    
    def build_features(
        self,
        vintage_date: date,
        target_dates: pd.DatetimeIndex,
        raw_sources: Dict[str, pd.Series]
    ) -> pd.DataFrame:
        ...
    
    def _align_daily_to_monthly(
        self,
        series: pd.Series,
        target_dates: pd.DatetimeIndex
    ) -> pd.DataFrame:
        ...
    
    def _align_weekly_to_monthly(
        self,
        series: pd.Series,
        target_dates: pd.DatetimeIndex
    ) -> pd.DataFrame:
        ...
    
    def _compute_almon_weights(
        self,
        n_lags: int,
        degree: int
    ) -> np.ndarray:
        ...
    
    def _handle_ragged_edge(
        self,
        aligned_features: pd.DataFrame,
        vintage_date: date
    ) -> pd.DataFrame:
        ...
```

**Key Design Decisions:**
- Uses existing `MIDASLagConstructor` internally (reuse, don't rewrite)
- Chains multiple constructors for multi-source data
- Produces clean monthly-aligned output with proper column naming

#### R3.1.2 Update `features/midas/__init__.py`
- [ ] Export `MIDASBridge`
- [ ] Keep existing exports (`MIDASLagConstructor`, utilities)

### R3.2 Connect Bridge to MIDASRegression

#### R3.2.1 Create `models_src/midas/bridged_regression.py`

**Decision:** Create new `MIDASBridgedRegression` class for cleaner separation of concerns.

**Structure:**
```python
class MIDASBridgedRegression(BaseForecaster):
    """
    MIDAS regression with integrated frequency bridging.
    
    Accepts raw high-frequency data directly and handles
    the full frequency bridging → regression pipeline.
    """
    
    def __init__(
        self,
        bridge_config: Dict[str, Any],
        regression_config: Dict[str, Any],
        random_state: int = 42
    ):
        ...
    
    def fit(
        self,
        raw_sources: Dict[str, pd.Series],
        y: pd.Series,
        vintage_date: str
    ) -> 'MIDASBridgedRegression':
        """Accepts raw data, not pre-aggregated."""
        ...
    
    def predict(
        self,
        raw_sources: Dict[str, pd.Series]
    ) -> np.ndarray:
        """Accepts raw data."""
        ...
    
    def _build_bridge_features(
        self,
        raw_sources: Dict[str, pd.Series],
        vintage_date: date
    ) -> pd.DataFrame:
        ...
```

#### R3.2.2 Update `models_src/midas/__init__.py`
- [ ] Export `MIDASBridgedRegression`
- [ ] Keep existing `MIDASRegression` for backward compatibility

#### R3.2.3 Interface Compatibility Layer

**Issue:** `MIDASBridgedRegression.fit(raw_sources, y, vintage_date)` differs from `BaseForecaster.fit(X, y, vintage_date)`.

**Solution:** Implement dual-mode interface for backward compatibility:

```python
class MIDASBridgedRegression(BaseForecaster):
    """
    Supports two fit modes:
    1. Legacy: fit(X, y, vintage_date) - pre-built feature matrix
    2. Raw: fit_raw(raw_sources, y, vintage_date) - raw high-frequency data
    """
    
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        vintage_date: str
    ) -> 'MIDASBridgedRegression':
        """Legacy mode: accepts pre-built feature matrix."""
        self._features = X
        # ... standard regression fit
        return self
    
    def fit_raw(
        self,
        raw_sources: Dict[str, pd.Series],
        y: pd.Series,
        vintage_date: str
    ) -> 'MIDASBridgedRegression':
        """New mode: accepts raw high-frequency data."""
        self._features = self.bridge.build_features(
            vintage_date=date.fromisoformat(vintage_date),
            target_dates=y.index,
            raw_sources=raw_sources
        )
        return self.fit(self._features, y, vintage_date)
```

**Benefits:**
- Existing pipelines/tests using `fit(X, y, vintage_date)` continue to work
- New pipelines can use `fit_raw(raw_sources, y, vintage_date)`
- `BaseForecaster` contract maintained (non-breaking change)

#### R3.2.4 Feature Naming Convention

**Issue:** Risk of feature name divergence between stored artifacts and runtime features.

**Solution:**
- Preserve existing names where possible: `{source}_midas_lags`
- New bridge columns: `{source}_bridge_lag_{n}` (explicit distinction)
- Add feature version tracking:

```python
class MIDASBridge:
    VERSION = "1.0.0"
    
    def build_features(...) -> pd.DataFrame:
        df = ...
        df.attrs['bridge_version'] = self.VERSION
        df.attrs['build_timestamp'] = datetime.now().isoformat()
        return df
```

- Feature registry MUST track bridge version used

### R3.3 Run MIDAS Bridge Tests

#### R3.3.1 Run TDD Tests
- [ ] Run new tests
  ```bash
  docker compose exec etl pytest tests/features/test_midas_bridge.py -v
  ```
- [ ] Target: All tests pass (green phase)
- [ ] Fix any failing tests

#### R3.3.2 Run Existing MIDAS Tests
- [ ] Run existing tests to ensure no regression
  ```bash
  docker compose exec etl pytest tests/models/test_midas.py tests/features/test_midas_lags.py -v
  ```

### R3.4 Gate Check: MIDAS Bridge Implementation

| Criterion | Required | Status |
|-----------|----------|--------|
| `MIDASBridge` class created | Yes | [ ] |
| `MIDASBridgedRegression` created | Yes | [ ] |
| All new tests pass | Yes | [ ] |
| All existing MIDAS tests pass | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R4 until all R3 tasks are complete.**

---

## Phase R4: DFM Stabilization with statsmodels

**Purpose:** Replace from-scratch DFM with statsmodels implementation  
**Estimated Time:** 4-5 hours  
**Blocking:** Phase R3 complete  
**TDD:** ✅ Implementation to make tests pass

### R4.1 Create DFM TDD Tests

#### R4.1.1 Create `tests/models/test_dfm_statsmodels.py`

**Tests to define:**

**Interface Tests:**
- [ ] `test_inherits_from_base_forecaster`
- [ ] `test_has_required_methods`
- [ ] `test_fit_returns_self`
- [ ] `test_predict_returns_array`
- [ ] `test_interface_unchanged_from_old_dfm`

**Numerical Stability Tests:**
- [ ] `test_handles_large_values_nfp_scale`
- [ ] `test_handles_covid_shock`
- [ ] `test_no_nan_predictions`
- [ ] `test_no_inf_predictions`
- [ ] `test_predictions_within_bounds`

**Mathematical Property Tests:**
- [ ] `test_factors_extracted`
- [ ] `test_factor_count_matches_config`
- [ ] `test_loadings_shape_correct`
- [ ] `test_explained_variance_positive`
- [ ] `test_different_from_ols_baseline`

**Out-of-Sample Prediction Tests (Critical Fix):**
- [ ] `test_predict_on_new_data_works`
- [ ] `test_predict_uses_learned_loadings`
- [ ] `test_predict_consistent_with_training`

**Serialization Tests:**
- [ ] `test_save_creates_file`
- [ ] `test_load_restores_model`
- [ ] `test_loaded_model_same_predictions`

#### R4.1.2 Run Tests to Confirm Failure (TDD Red Phase)
- [ ] Run tests
  ```bash
  docker compose exec etl pytest tests/models/test_dfm_statsmodels.py -v
  ```
- [ ] Expected: All tests fail
- [ ] Record failure count

### R4.2 Implement statsmodels DFM

#### R4.2.1 Replace `models_src/dfm/dfm_model.py`

**Model Choice: `DynamicFactor` (not `DynamicFactorMQ`)**

| Model | Use Case | Our Architecture |
|-------|----------|------------------|
| `DynamicFactor` | Single-frequency data | ✅ Correct choice |
| `DynamicFactorMQ` | Monthly + Quarterly mixed | ❌ Not needed |

**Rationale:** The MIDAS Bridge pre-aligns all data to monthly frequency:
- Daily Treasury → Monthly (via MIDAS Bridge)
- Weekly Claims → Monthly (via MIDAS Bridge)
- Monthly BLS CES → Monthly (pass-through)

The DFM receives **homogeneous monthly data**, so `DynamicFactor` is appropriate. `DynamicFactorMQ` would only be needed if DFM itself handled mixed frequencies.

**Key Changes:**

1. **Replace custom EM algorithm** with `statsmodels.tsa.statespace.dynamic_factor.DynamicFactor`

2. **Fix `_extract_factors()` for out-of-sample prediction:**
   - **Current (broken):** Assumes statsmodels can apply filter to new data
   - **Fixed:** Use learned loadings matrix to project new observations
   
   ```python
   def _extract_factors(self, X_new: np.ndarray) -> np.ndarray:
       """
       Extract factors from new data using learned loadings.
       
       Correct approach for out-of-sample factor extraction:
       1. Standardize X_new using training statistics
       2. Project onto learned factors: factors = X_scaled @ pseudo_inverse(loadings)
       (NOT using Kalman filter on new data - statsmodels doesn't support this)
       """
       X_scaled = (X_new - self.X_mean_) / self.X_std_
       # Use pseudo-inverse of loadings to project to factor space
       loadings_pinv = np.linalg.pinv(self.loadings_)
       factors = X_scaled @ loadings_pinv
       return factors
   ```

3. **Add proper error handling and logging**

4. **Maintain identical interface to old DFM**

**API Compatibility Guarantee:**
| Element | Status | Notes |
|---------|--------|-------|
| Class name | `DynamicFactorModel` | ✅ Preserved |
| Constructor | `(n_factors, max_iter, tol, random_state)` | ✅ Unchanged |
| `fit(X, y, vintage_date)` | ✅ Unchanged | Returns self |
| `predict(X)` | ✅ Unchanged | Returns np.ndarray |
| `save(path)` / `load(path)` | ✅ Unchanged | joblib format |
| `factors_`, `loadings_`, `is_fitted` | ✅ Preserved | Same attribute names |
| `_em_step()`, `_kalman_smooth()` | ❌ Removed | Internal, replaced by statsmodels |

**Serialization Approach:**

statsmodels `DynamicFactorResults` objects are complex. We extract key artifacts to maintain existing numpy-based save/load format:

```python
def _extract_model_artifacts(self, results: DynamicFactorResults) -> Dict:
    """Extract serializable artifacts from statsmodels results."""
    return {
        'loadings_': results.coefficients_of_determination,  # or custom extraction
        'transition_': results.params[:self.n_factors**2].reshape(self.n_factors, -1),
        'factors_': results.factors.filtered.T,
        'X_mean_': self.X_mean_,
        'X_std_': self.X_std_,
        # Metadata
        'statsmodels_version': statsmodels.__version__,
        'n_iter_': results.nobs,
    }
```

**Note:** The exact extraction depends on statsmodels internals; will be finalized during implementation.

**Determinism Enforcement:**

```python
def fit(self, X: pd.DataFrame, y: pd.Series, vintage_date: str) -> 'DynamicFactorModel':
    """Deterministic fitting with random_state control."""
    # Set numpy random state for any stochastic operations
    np.random.seed(self.random_state)
    
    # statsmodels DynamicFactor uses MLE, generally deterministic
    # but we seed for any numerical noise
    self.model_ = DynamicFactor(
        endog=X.values,
        k_factors=self.n_factors,
        factor_order=1
    )
    
    self.results_ = self.model_.fit(disp=False, maxiter=self.max_iter)
    
    # Same seed + same data = same results
    return self
```

**Test:** Add `test_dfm_reproducibility_with_seed()` to verify determinism.

#### R4.2.2 Evaluate `models_src/dfm/state_space.py`

**Decision Required:**
- [ ] **Keep:** If utilities are useful for validation or debugging
- [ ] **Deprecate:** Mark as deprecated, keep for compatibility
- [ ] **Delete:** Remove if no longer needed

**Decision Criteria:**

| Criterion | Assessment | Action |
|-----------|------------|--------|
| `StateSpaceRepresentation` class | Useful for validating statsmodels output shapes | **KEEP** |
| `build_transition_matrix()` | Not needed (statsmodels handles internally) | **DEPRECATE** |
| `build_observation_matrix()` | Not needed (statsmodels handles internally) | **DEPRECATE** |
| `validate_state_space_dimensions()` | Useful for debugging | **KEEP** |
| `is_stable` property | Useful for post-fit validation | **KEEP** |

**Recommendation:** 
- **KEEP** `state_space.py` with deprecation warnings on builder functions
- **UPDATE** `test_dfm_state_space.py` to test validation utilities on statsmodels output
- **DO NOT DELETE** — validation utilities remain valuable for debugging

```python
# Example deprecation
import warnings

def build_transition_matrix(...):
    warnings.warn(
        "build_transition_matrix is deprecated. "
        "statsmodels DynamicFactor handles transition matrix internally.",
        DeprecationWarning
    )
    # ... existing implementation for compatibility
```

### R4.3 Run DFM Tests

#### R4.3.1 Run New TDD Tests
- [ ] Run tests
  ```bash
  docker compose exec etl pytest tests/models/test_dfm_statsmodels.py -v
  ```
- [ ] Target: All tests pass

#### R4.3.2 Update and Run Existing DFM Tests
- [ ] Update `tests/models/test_dfm.py` for new implementation
  - Remove EM-specific tests
  - Keep interface tests
  - Update convergence tests to statsmodels equivalents
- [ ] Update `tests/models/test_dfm_properties.py`
  - Adapt mathematical property tests
  - Remove EM-specific property tests
- [ ] Handle `tests/models/test_dfm_state_space.py`
  - Skip or update based on R4.2.2 decision

#### R4.3.3 Run All DFM Tests
- [ ] Run complete DFM test suite
  ```bash
  docker compose exec etl pytest tests/models/test_dfm*.py -v --tb=short
  ```

### R4.4 Gate Check: DFM Stabilization

| Criterion | Required | Status |
|-----------|----------|--------|
| New DFM implementation created | Yes | [ ] |
| Out-of-sample prediction fixed | Yes | [ ] |
| All new tests pass | Yes | [ ] |
| All updated existing tests pass | Yes | [ ] |
| state_space.py decision made | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R5 until all R4 tasks are complete.**

---

## Phase R5: Integration Layer

**Purpose:** Connect MIDAS Bridge → DFM → Ensemble  
**Estimated Time:** 3-4 hours  
**Blocking:** Phase R4 complete

### R5.1 Create Integration Pipeline

#### R5.1.1 Create `models_src/pipelines/mixed_frequency_pipeline.py`

**Structure:**
```python
class MixedFrequencyPipeline:
    """
    End-to-end mixed-frequency forecasting pipeline.
    
    Integrates:
    - MIDAS Bridge (frequency bridging)
    - DFM (factor extraction, stability)
    - XGBoost (non-linear corrections)
    - Ensemble (combination)
    """
    
    def __init__(
        self,
        midas_bridge: MIDASBridge,
        dfm: DynamicFactorModel,
        xgboost: XGBoostQuantile,
        ensemble_config: EnsembleConfig
    ):
        ...
    
    def fit(
        self,
        vintage_date: date,
        raw_sources: Dict[str, pd.Series],
        y_monthly: pd.Series
    ) -> 'MixedFrequencyPipeline':
        ...
    
    def predict(
        self,
        vintage_date: date,
        raw_sources: Dict[str, pd.Series]
    ) -> Tuple[np.ndarray, np.ndarray]:  # predictions, prediction_intervals
        ...
    
    def get_factors(self) -> np.ndarray:
        """Return DFM-extracted factors."""
        ...
    
    def get_feature_importance(self) -> pd.DataFrame:
        """Return combined feature importance."""
        ...
```

**Data Flow:**
```
Raw Sources (D/W/M)
    │
    ↓
MIDASBridge.build_features()
    │
    ↓
Monthly-Aligned Features
    │
    ├──→ DFM.fit(features) → factors, predictions
    │
    ├──→ XGBoost.fit(features) → predictions
    │
    └──→ MIDASBridgedRegression.fit(raw) → predictions
               │
               ↓
         Ensemble.combine() → final predictions + intervals
```

#### R5.1.2 Update `models_src/pipelines/ensemble_pipeline.py`

- [ ] Ensure `EnsembleForecaster` can accept new DFM
- [ ] Add mixed-frequency pipeline as ensemble option
- [ ] Update docstrings to reflect new capabilities

### R5.2 Update Feature Building Pipeline

#### R5.2.1 Update `scripts/build_features.py`

- [ ] Add option to use `MIDASBridge` for feature building
- [ ] Maintain backward compatibility with existing feature building
- [ ] Add CLI flag: `--use-midas-bridge`

**Feature Versioning Rules:**

| Context | Feature Source | Purpose |
|---------|----------------|---------|
| **Training artifacts** | `scripts/build_features.py --use-midas-bridge` | Stored parquet with version metadata |
| **Runtime prediction** | `MIDASBridge.build_features()` | Real-time feature construction |
| **Backtest validation** | `VintageHarness` + `MIDASBridge` | Vintage-consistent features |

**Implementation:**
```python
# scripts/build_features.py
def main():
    parser.add_argument('--use-midas-bridge', action='store_true',
                       help='Use MIDASBridge for D/W→M alignment')
    parser.add_argument('--bridge-version', type=str, default='1.0.0',
                       help='Track bridge version in feature metadata')
    
    # When saving features:
    if args.use_midas_bridge:
        features_df.attrs['bridge_version'] = args.bridge_version
        features_df.attrs['feature_hash'] = hashlib.sha256(
            features_df.to_json().encode()
        ).hexdigest()[:16]
```

**Migration Utility:** Add `scripts/migrate_feature_registry.py --bridge-upgrade` for transitioning existing features.

#### R5.2.2 Additional Script Updates Required

| Script | Action | Changes |
|--------|--------|---------|
| `scripts/train_sample_model.py` | UPDATE | Update DFM instantiation to new implementation |
| `scripts/test_pipelines.py` | UPDATE | Add bridge validation tests |
| `scripts/verify_vintage_harness.py` | UPDATE | Test with MIDASBridge integration |

### R5.3 Integration Tests

#### R5.3.1 Create `tests/integration/test_mixed_frequency_pipeline.py`

**Tests:**
- [ ] `test_pipeline_builds_from_raw_data`
- [ ] `test_pipeline_produces_monthly_predictions`
- [ ] `test_pipeline_handles_ragged_edge`
- [ ] `test_pipeline_integrates_with_vintage_manager`
- [ ] `test_pipeline_produces_prediction_intervals`

#### R5.3.2 Update Existing Integration Tests

- [ ] Update `tests/integration/test_etl_features_models.py`
  - Add tests for MIDAS Bridge integration
  - Add tests for new DFM
- [ ] Update `tests/integration/test_complete_workflow.py`
  - Update DFM references
  - Add mixed-frequency pipeline tests

#### R5.3.3 Intra-Month Update Tests

**Rationale:** ACCURACY_MAP.md Section 8 specifies T-48h → T-2h optimal window for intra-month nowcasting. Must verify pipeline supports sequential updates with new data arrivals.

**Tests to Add in `tests/integration/test_mixed_frequency_pipeline.py`:**
- [ ] `test_pipeline_sequential_updates` — Call `predict()` multiple times with progressively updated `raw_sources`
- [ ] `test_prediction_uncertainty_with_more_data` — Later updates (more data) should have tighter prediction intervals
- [ ] `test_ragged_edge_graceful_degradation` — Missing recent daily/weekly data produces valid (wider) intervals, not errors

**Example Test Structure:**
```python
def test_pipeline_sequential_updates(self, pipeline, vintage_date):
    """Verify pipeline can be called multiple times as new data arrives."""
    # Simulate T-48h: Only data through 2 days ago
    raw_sources_t48 = load_raw_sources(vintage_date, cutoff_days=2)
    pred_t48, intervals_t48 = pipeline.predict(vintage_date, raw_sources_t48)
    
    # Simulate T-24h: Data through yesterday
    raw_sources_t24 = load_raw_sources(vintage_date, cutoff_days=1)
    pred_t24, intervals_t24 = pipeline.predict(vintage_date, raw_sources_t24)
    
    # Both should produce valid predictions
    assert not np.isnan(pred_t48).any()
    assert not np.isnan(pred_t24).any()
    
    # Intervals should narrow with more data (optional assertion)
    # assert intervals_t24 width <= intervals_t48 width
```

**Note:** Automated triggering of updates is Phase 9 (Nowcast Agent) scope; these tests verify the infrastructure supports it.

### R5.4 Gate Check: Integration Layer

| Criterion | Required | Status |
|-----------|----------|--------|
| Mixed-frequency pipeline created | Yes | [ ] |
| Ensemble pipeline updated | Yes | [ ] |
| Feature building script updated | Yes | [ ] |
| All integration tests pass | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R6 until all R5 tasks are complete.**

---

## Phase R6: Unit & Integration Test Validation

**Purpose:** Comprehensive test validation across all components  
**Estimated Time:** 3-4 hours  
**Blocking:** Phase R5 complete

### Test Runtime Budget

**Clarification:** The analysis estimated ~700-1,200 new tests, but actual count is lower:

| Category | Tests | Notes |
|----------|-------|-------|
| **New tests** | ~50 | Bridge, statsmodels DFM, pipeline |
| **Modified tests** | ~100 | Interface updates, not rewrites |
| **Total impacted** | ~150 | Of ~300 model/feature tests |

**CI Considerations:**
- Add +5 minutes buffer for new integration tests
- Run MIDAS Bridge tests in parallel with DFM tests
- Consider separate CI job for integration tests if timeout issues arise

### R6.1 Run All MIDAS Tests

#### R6.1.1 MIDAS Unit Tests
- [ ] `tests/models/test_midas.py`
- [ ] `tests/models/test_midas_properties.py`
- [ ] `tests/features/test_midas_lags.py`
- [ ] `tests/features/test_midas_bridge.py` (new)

```bash
docker compose exec etl pytest tests/models/test_midas*.py tests/features/test_midas*.py -v --tb=short
```

#### R6.1.2 Record Results
| Test File | Tests | Pass | Fail | Skip |
|-----------|-------|------|------|------|
| test_midas.py | ? | ? | ? | ? |
| test_midas_properties.py | ? | ? | ? | ? |
| test_midas_lags.py | ? | ? | ? | ? |
| test_midas_bridge.py | ? | ? | ? | ? |

### R6.2 Run All DFM Tests

#### R6.2.1 DFM Unit Tests
- [ ] `tests/models/test_dfm.py`
- [ ] `tests/models/test_dfm_properties.py`
- [ ] `tests/models/test_dfm_state_space.py`
- [ ] `tests/models/test_dfm_statsmodels.py` (new)

```bash
docker compose exec etl pytest tests/models/test_dfm*.py -v --tb=short
```

#### R6.2.2 Record Results
| Test File | Tests | Pass | Fail | Skip |
|-----------|-------|------|------|------|
| test_dfm.py | ? | ? | ? | ? |
| test_dfm_properties.py | ? | ? | ? | ? |
| test_dfm_state_space.py | ? | ? | ? | ? |
| test_dfm_statsmodels.py | ? | ? | ? | ? |

### R6.3 Run All Integration Tests

#### R6.3.1 Integration Tests
- [ ] `tests/integration/test_etl_features_models.py`
- [ ] `tests/integration/test_complete_workflow.py`
- [ ] `tests/integration/test_mixed_frequency_pipeline.py` (new)
- [ ] `tests/models/test_ensemble_pipeline.py`

```bash
docker compose exec etl pytest tests/integration/ tests/models/test_ensemble_pipeline.py -v --tb=short
```

#### R6.3.2 Record Results
| Test File | Tests | Pass | Fail | Skip |
|-----------|-------|------|------|------|
| test_etl_features_models.py | ? | ? | ? | ? |
| test_complete_workflow.py | ? | ? | ? | ? |
| test_mixed_frequency_pipeline.py | ? | ? | ? | ? |
| test_ensemble_pipeline.py | ? | ? | ? | ? |

### R6.4 Run Pipeline Scripts

#### R6.4.1 Verify Scripts Work
- [ ] `scripts/build_features.py --use-midas-bridge`
- [ ] Training pipeline with new DFM
- [ ] Ensemble pipeline with mixed-frequency support

### R6.5 Gate Check: Test Validation

| Criterion | Required | Status |
|-----------|----------|--------|
| All MIDAS tests pass | Yes | [ ] |
| All DFM tests pass | Yes | [ ] |
| All integration tests pass | Yes | [ ] |
| Pipeline scripts work | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R7 until all R6 tasks are complete.**

---

## Phase R7: Real Data Validation

**Purpose:** Re-run Phase 6.3.1a validation with real BLS CES data  
**Estimated Time:** 2-3 hours  
**Blocking:** Phase R6 complete  
**Critical:** This is the ultimate validation test

### R7.1 Run Phase 6.3.1a DFM Validation

#### R7.1.1 Update Validation Tests
- [ ] Update `tests/backtests/test_dfm_validation.py` for new DFM
- [ ] Ensure tests use real BLS CES vintage data
- [ ] Ensure tests use MIDAS Bridge for feature building

**Data Preprocessing Requirements:**

The from-scratch DFM failed (0% stability) partly due to insufficient preprocessing. The statsmodels implementation should include:

```python
def _preprocess_features(self, X: pd.DataFrame) -> np.ndarray:
    """
    Preprocess features for DFM stability.
    
    1. Handle NaN/Inf: Replace or drop
    2. Standardize: z-score normalization
    3. Winsorize: Clip COVID-era outliers (optional)
    4. Validate: Log feature statistics
    """
    # 1. Validate input
    if X.isna().any().any():
        logger.warning(f"NaN values found in {X.isna().sum().sum()} cells")
        X = X.fillna(method='ffill').fillna(method='bfill')
    
    # 2. Standardize
    self.X_mean_ = X.mean()
    self.X_std_ = X.std().replace(0, 1)  # Avoid division by zero
    X_scaled = (X - self.X_mean_) / self.X_std_
    
    # 3. Winsorize extreme values (optional, for COVID period)
    lower, upper = X_scaled.quantile(0.01), X_scaled.quantile(0.99)
    X_scaled = X_scaled.clip(lower=lower, upper=upper, axis=1)
    
    # 4. Log statistics for debugging
    logger.info(f"Feature stats - mean: {X_scaled.mean().mean():.4f}, "
                f"std: {X_scaled.std().mean():.4f}, "
                f"min: {X_scaled.min().min():.4f}, "
                f"max: {X_scaled.max().max():.4f}")
    
    return X_scaled.values
```

**Test:** Add `test_dfm_handles_preprocessing()` to verify robustness.

**Test Fixture Migration Guidance:**

When updating `tests/backtests/test_dfm_validation.py` for statsmodels DFM, verify fixture compatibility:

| Fixture/Attribute | Current State | After Refactor | Action |
|-------------------|---------------|----------------|--------|
| `factors_` shape | `(n_samples, n_factors)` | Same (extracted from statsmodels) | Verify shape unchanged |
| `loadings_` shape | `(n_features, n_factors)` | Same | Verify shape unchanged |
| `SMAPE_THRESHOLD` | 20.0 | May improve with stable DFM | Monitor, don't lower prematurely |
| `STABILITY_THRESHOLD` | 1,000,000 | Should rarely trigger | Expect near-100% stability |
| `PI_COVERAGE_MIN/MAX` | 85.0 / 95.0 | Same targets | Now testable (DFM stable) |

**Transition Period Validation:**
```python
def test_statsmodels_vs_scratch_comparison(self, vintage_date, features, target):
    """One-time comparison to validate statsmodels produces comparable results."""
    # Run both implementations on same data
    dfm_scratch = DynamicFactorModelScratch(n_factors=2, random_state=42)
    dfm_statsmodels = DynamicFactorModel(n_factors=2, random_state=42)
    
    # Fit both
    dfm_scratch.fit(features, target, vintage_date=str(vintage_date))
    dfm_statsmodels.fit(features, target, vintage_date=str(vintage_date))
    
    # Log differences for review (not strict assertions)
    logger.info(f"Factors correlation: {np.corrcoef(dfm_scratch.factors_.flatten(), dfm_statsmodels.factors_.flatten())[0,1]:.4f}")
    logger.info(f"Loadings correlation: {np.corrcoef(dfm_scratch.loadings_.flatten(), dfm_statsmodels.loadings_.flatten())[0,1]:.4f}")
```

**Note:** This comparison test is for validation during transition only; remove after confirming statsmodels implementation is stable.

#### R7.1.2 Run DFM Validation
- [ ] Execute validation
  ```bash
  docker compose exec etl pytest tests/backtests/test_dfm_validation.py -v -s
  ```

#### R7.1.3 Record Results

**Available Real Vintage Data (Confirmed):**
- **Total BLS CES Vintages:** 18 directories
- **Real Data Vintages:** 16 (15 quarterly from 2022-03-01 to 2025-09-01 + 1 direct API 2025-12-02)
- **Synthetic Vintages:** 2 (2024-01-15, 2025-11-29 — exclude from validation)
- **Date Range:** 2022-03-01 to 2025-12-02 (3+ years)
- **✅ Requirement Met:** 10+ real vintage dates (we have 16)

**Stability Comparison:**
| Metric | Old (From Scratch) | New (statsmodels) | Target |
|--------|--------------------|--------------------|--------|
| Stability Rate | 0% (0/17) | ? | > 90% |
| NaN Predictions | Many | ? | 0 |
| Overflow Errors | Yes | ? | No |

**Accuracy Comparison:**
| Model | Avg sMAPE | Avg RMSE | Recommendation |
|-------|-----------|----------|----------------|
| DFM (new) | ? | ? | ? |
| MIDAS Bridged | ? | ? | ? |
| XGBoost | ? | ? | ? |
| Ensemble | ? | ? | ? |

#### R7.1.4 Calibration Integration Validation

**Rationale:** ACCURACY_MAP.md Section 5.2 requires 74-86% PI coverage. The refactor must verify calibration works with bridge-produced features, not just pre-aggregated features.

**Gap Addressed:** Current `test_dfm_validation.py` defines `PI_COVERAGE_MIN/MAX` but does NOT exercise calibration. `test_complete_workflow.py` exercises calibration but with pre-aggregated features.

**Tests to Add in `tests/backtests/test_dfm_validation.py`:**
- [ ] `test_bridge_to_calibration_pipeline` — MIDASBridge → DFM → ConformalPredictor
- [ ] `test_mixed_frequency_interval_coverage` — Verify 85-95% coverage on real vintages
- [ ] `test_calibration_with_ragged_edge` — Partial data doesn't break calibration

**Test Structure:**
```python
class TestDFMCalibrationIntegration:
    """
    Verify calibration works with bridge-produced features.
    
    Target: ACCURACY_MAP.md Section 5.2 (74-86% PI coverage)
    """
    
    def test_mixed_frequency_interval_coverage(
        self,
        vintage_datasets: Dict[date, Dict],
        midas_bridge: MIDASBridge
    ):
        """
        Verify prediction interval coverage meets ACCURACY_MAP targets.
        """
        from models_src.calibration.conformal import ConformalPredictor
        
        coverage_results = []
        
        for vintage_date, data in vintage_datasets.items():
            # Build features via bridge (not pre-aggregated)
            bridged_features = midas_bridge.build_features(
                vintage_date=vintage_date,
                target_dates=data["target"].index,
                raw_sources=data["raw_sources"]
            )
            
            # Train DFM on bridged features
            dfm = DynamicFactorModel(n_factors=3, random_state=42)
            # ... split, fit, predict ...
            
            # Apply calibration
            conformal = ConformalPredictor(confidence_levels=[0.9])
            conformal.fit(val_actuals, val_predictions)  # fit(y_true, y_pred)
            lower, upper = conformal.predict_interval(test_predictions)  # returns (lower, upper) tuple
            
            # Measure coverage
            coverage = prediction_interval_coverage(
                test_actuals, lower, upper
            )
            coverage_results.append(coverage)
        
        avg_coverage = np.mean(coverage_results)
        logger.info(f"Average 90% PI coverage: {avg_coverage:.1f}%")
        
        # ACCURACY_MAP.md target: 85-95% for 90% intervals
        assert PI_COVERAGE_MIN <= avg_coverage <= PI_COVERAGE_MAX, \
            f"Coverage {avg_coverage:.1f}% outside target range [{PI_COVERAGE_MIN}, {PI_COVERAGE_MAX}]"
```

**Success Criteria:**
| Metric | Target | Source |
|--------|--------|--------|
| 90% PI Coverage | 85-95% | ACCURACY_MAP.md Section 5.2 |
| ECE (Expected Calibration Error) | < 0.05 | IMPLEMENTATION_STATUS.md deployment gates |
| No NaN intervals | 100% | Basic stability |

### R7.2 DFM Ensemble Decision

#### R7.2.1 Evaluate Against Criteria
| Criterion | Threshold | Result | Pass? |
|-----------|-----------|--------|-------|
| Stability | > 90% | ? | ? |
| sMAPE | < 20% | ? | ? |
| No NaN/Inf | 100% | ? | ? |
| Adds ensemble value | Improves combined | ? | ? |

#### R7.2.2 Make Final Decision
- [ ] **If all criteria pass:** ✅ Include DFM in production ensemble
- [ ] **If criteria fail:** ❌ Exclude DFM, document why, plan future improvements

### R7.3 Mixed-Frequency Pipeline Validation

#### R7.3.1 Run End-to-End Test
- [ ] Execute mixed-frequency pipeline on 10+ vintages
- [ ] Verify MIDAS Bridge → DFM → Ensemble flow works
- [ ] Measure prediction accuracy

### R7.4 Gate Check: Real Data Validation

| Criterion | Required | Status |
|-----------|----------|--------|
| DFM validation tests pass | Yes | [ ] |
| Stability rate recorded | Yes | [ ] |
| sMAPE recorded | Yes | [ ] |
| Ensemble decision made | Yes | [ ] |
| Mixed-frequency pipeline validated | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R8 until all R7 tasks are complete.**

---

## Phase R8: Documentation Update

**Purpose:** Update all documentation to reflect new implementation  
**Estimated Time:** 3-4 hours  
**Blocking:** Phase R7 complete

### R8.1 Update Core Documentation

#### R8.1.1 `docs/planning/IMPLEMENTATION_STATUS.md`
- [ ] Update Phase 5.3 status (DFM re-implemented)
- [ ] Update Phase 6.3.1a results (re-validated with new DFM)
- [ ] Update Phase 6.4.2.1 ensemble decision
- [ ] Add reference to this refactor plan
- [ ] Update header to reflect completion

#### R8.1.2 `docs/planning/PHASE_6_3_1a_COMPLETION_SUMMARY.md`
- [ ] Replace old results with new results
- [ ] Update DFM recommendation (include/exclude)
- [ ] Update data source notes

#### R8.1.3 Update Capability Documentation
- [ ] `docs/5_PILLARS.md` — Verify DFM "Structural Engine" description accurate
- [ ] `docs/FORECASTING_CAPABILITIES.md` — Update mixed-frequency capability description
- [ ] `docs/ACCURACY_DESCRIPTION.md` — Update tier descriptions
- [ ] `docs/ACCURACY_MAP.md` — Update accuracy expectations
- [ ] `docs/FORECASTING_CAPABILITIES.md` — Document intra-month nowcast update capability
  - `MixedFrequencyPipeline.predict()` supports re-calling with updated `raw_sources`
  - As new daily Treasury or weekly claims data arrives, pipeline can regenerate forecasts
  - Optimal update window: T-48h → T-2h before NFP release (per ACCURACY_MAP.md Section 8)
  - **Note:** Automated triggering is Phase 9 (Nowcast Agent) scope; this refactor provides the infrastructure

### R8.2 Update Phase 5 Documentation

#### R8.2.1 Phase 5 Files
- [ ] `docs/planning/phase_5/PHASE_5_IMPLEMENTATION_PLAN.md`
- [ ] `docs/planning/phase_5/PHASE_5_MATHEMATICAL_VALIDATION_COMPLETE.md`
- [ ] `docs/planning/phase_5/PHASE_5_13_2_COMPLETION_SUMMARY.md`

### R8.3 Update Testing Documentation

#### R8.3.1 Testing Docs
- [ ] `docs/TESTING_MATHEMATICAL_ALGORITHMS.md` — Update DFM examples
- [ ] `docs/planning/phase_5/PHASE_5_TDD_BLINDSPOT_ANALYSIS.md` — Add lessons learned

### R8.4 Update Configuration

#### R8.4.1 Configuration Files
- [ ] `tests/fixtures/performance_baselines.json` — Update DFM baselines
- [ ] Any YAML configs referencing DFM

### R8.5 Gate Check: Documentation

| Criterion | Required | Status |
|-----------|----------|--------|
| IMPLEMENTATION_STATUS.md updated | Yes | [ ] |
| PHASE_6_3_1a_COMPLETION_SUMMARY.md updated | Yes | [ ] |
| Capability docs updated | Yes | [ ] |
| Phase 5 docs updated | Yes | [ ] |
| Testing docs updated | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R9 until all R8 tasks are complete.**

---

## Phase R9: Final Validation & Cleanup

**Purpose:** Complete final validation and cleanup  
**Estimated Time:** 2-3 hours  
**Blocking:** Phase R8 complete

### R9.1 Run Full Test Suite

#### R9.1.1 All Model Tests
- [ ] Run all model tests
  ```bash
  docker compose exec etl pytest tests/models/ -v --tb=short
  ```
- [ ] Target: All tests pass

#### R9.1.2 All Feature Tests
- [ ] Run all feature tests
  ```bash
  docker compose exec etl pytest tests/features/ -v --tb=short
  ```
- [ ] Target: All tests pass

#### R9.1.3 All Integration Tests
- [ ] Run all integration tests
  ```bash
  docker compose exec etl pytest tests/integration/ -v --tb=short
  ```
- [ ] Target: All tests pass

#### R9.1.4 All Backtest Tests
- [ ] Run all backtest tests
  ```bash
  docker compose exec etl pytest tests/backtests/ -v --tb=short
  ```
- [ ] Target: All tests pass

### R9.2 Code Quality Check

#### R9.2.1 Linting
- [ ] Run linting on modified files
  ```bash
  docker compose exec etl ruff check models_src/dfm/ models_src/midas/ features/midas/
  docker compose exec etl mypy models_src/dfm/ models_src/midas/ features/midas/ --ignore-missing-imports
  ```

#### R9.2.2 Code Review
- [ ] No TODO comments left in production code
- [ ] All docstrings complete
- [ ] All type hints present

### R9.3 Cleanup

#### R9.3.1 Decide on Deprecated Files
- [ ] `state_space.py` — Keep/Deprecate/Delete decision implemented
- [ ] Remove any temporary files

#### R9.3.2 Remove Backup Branch (Optional)
- [ ] After production validation, can delete `backup/midas-dfm-pre-refactor`

### R9.4 Final Documentation

#### R9.4.1 Create Completion Summary
Record final metrics:

| Metric | Before | After |
|--------|--------|-------|
| DFM Stability | 0% | ?% |
| DFM sMAPE | N/A | ?% |
| MIDAS Bridging | ❌ Not implemented | ✅ Implemented |
| Mixed-Frequency Pipeline | ❌ Not implemented | ✅ Implemented |
| DFM in Ensemble | No | ? |
| All Tests Passing | ?/? | ?/? |

#### R9.4.2 Mark Plan Complete
- [ ] Update this plan's status to ✅ COMPLETE
- [ ] Update IMPLEMENTATION_STATUS.md

### R9.5 Gate Check: Final

| Criterion | Required | Status |
|-----------|----------|--------|
| All model tests pass | Yes | [ ] |
| All feature tests pass | Yes | [ ] |
| All integration tests pass | Yes | [ ] |
| All backtest tests pass | Yes | [ ] |
| Linting passes | Yes | [ ] |
| Cleanup complete | Yes | [ ] |
| Completion summary created | Yes | [ ] |

---

## Appendix A: Complete Files Inventory

### A.1 Files to CREATE

| File | Purpose | Lines (Est.) |
|------|---------|--------------|
| `features/midas/bridge.py` | MIDAS Bridge Layer | ~200-300 |
| `models_src/midas/bridged_regression.py` | Bridged MIDAS Model | ~150-200 |
| `models_src/pipelines/mixed_frequency_pipeline.py` | Integration Pipeline | ~300-400 |
| `tests/features/test_midas_bridge.py` | Bridge Tests | ~300-400 |
| `tests/models/test_dfm_statsmodels.py` | DFM Tests | ~400-500 |
| `tests/integration/test_mixed_frequency_pipeline.py` | Integration Tests | ~300-400 |

### A.2 Files to REPLACE

| File | Current Lines | Action |
|------|---------------|--------|
| `models_src/dfm/dfm_model.py` | 612 | **REPLACE** with statsmodels |

### A.3 Files to UPDATE

| File | Action | Changes |
|------|--------|---------|
| `models_src/dfm/__init__.py` | UPDATE | Export new DFM |
| `models_src/midas/__init__.py` | UPDATE | Export bridge components |
| `features/midas/__init__.py` | UPDATE | Export MIDASBridge |
| `models_src/pipelines/ensemble_pipeline.py` | UPDATE | Support new components |
| `scripts/build_features.py` | UPDATE | Add bridge option, versioning |
| `scripts/train_sample_model.py` | UPDATE | Update DFM instantiation |
| `scripts/test_pipelines.py` | UPDATE | Add bridge validation |
| `scripts/verify_vintage_harness.py` | UPDATE | Test MIDASBridge integration |
| `tests/models/test_dfm.py` | UPDATE | Adapt for statsmodels |
| `tests/models/test_dfm_properties.py` | UPDATE | Adapt for statsmodels |
| `tests/integration/test_etl_features_models.py` | UPDATE | Add new tests |
| `tests/integration/test_complete_workflow.py` | UPDATE | Add new tests |
| `tests/backtests/test_dfm_validation.py` | UPDATE | Use new DFM |

### A.4 Files to EVALUATE

| File | Decision | Criteria |
|------|----------|----------|
| `models_src/dfm/state_space.py` | KEEP/DEPRECATE | Utility value |
| `tests/models/test_dfm_state_space.py` | KEEP/SKIP | Based on state_space.py |

### A.5 Documentation Files to UPDATE (30+)

**Priority 1 (Must Update):**
1. `docs/planning/IMPLEMENTATION_STATUS.md`
2. `docs/planning/PHASE_6_3_1a_COMPLETION_SUMMARY.md`
3. `docs/5_PILLARS.md`
4. `docs/FORECASTING_CAPABILITIES.md`
5. `docs/ACCURACY_MAP.md`

**Priority 2 (Should Update):**
6. `docs/planning/phase_5/PHASE_5_IMPLEMENTATION_PLAN.md`
7. `docs/planning/phase_5/PHASE_5_13_2_COMPLETION_SUMMARY.md`
8. `docs/TESTING_MATHEMATICAL_ALGORITHMS.md`
9. `tests/fixtures/performance_baselines.json`

---

## Appendix B: Test Inventory

### B.1 New Tests to Create

| Test File | Tests (Est.) | Purpose |
|-----------|--------------|---------|
| `test_midas_bridge.py` | ~15-20 | MIDAS Bridge functionality |
| `test_dfm_statsmodels.py` | ~20-25 | statsmodels DFM |
| `test_mixed_frequency_pipeline.py` | ~10-15 | Integration pipeline |

### B.2 Existing Tests to Update

| Test File | Current Tests | Update Scope |
|-----------|---------------|--------------|
| `test_dfm.py` | 25 | Remove EM-specific, keep interface |
| `test_dfm_properties.py` | 13 | Adapt mathematical tests |
| `test_midas.py` | ~20 | Minor updates for compatibility |
| `test_etl_features_models.py` | ~15 | Add bridge/DFM integration |
| `test_complete_workflow.py` | ~20 | Update DFM references |
| `test_dfm_validation.py` | 5 | Use new DFM |

### B.3 Tests to Evaluate

| Test File | Tests | Decision Depends On |
|-----------|-------|---------------------|
| `test_dfm_state_space.py` | 26 | state_space.py decision |

---

## Appendix C: Rollback Plan

### C.1 Immediate Rollback

If refactor causes unrecoverable issues:

```bash
# 1. Checkout backup branch
git checkout backup/midas-dfm-pre-refactor

# 2. Copy files back to main
git checkout main
git checkout backup/midas-dfm-pre-refactor -- models_src/dfm/ models_src/midas/ features/midas/
```

### C.2 Partial Rollback Options

| Scenario | Action |
|----------|--------|
| MIDAS Bridge fails, DFM works | Keep new DFM, revert bridge |
| DFM fails, MIDAS Bridge works | Keep bridge, revert DFM |
| Integration fails | Revert integration pipeline only |

### C.3 Rollback Decision Criteria

| Condition | Action |
|-----------|--------|
| > 30% tests fail after 6 hours debugging | Full rollback |
| Integration fundamentally broken | Full rollback |
| DFM stability < 50% on real data | Keep bridge, exclude DFM |
| MIDAS bridge unstable | Revert bridge, keep old approach |

---

## Appendix D: Capability Alignment Matrix

### D.1 Alignment with 5_PILLARS.md

| Requirement | Before | After | Status |
|-------------|--------|-------|--------|
| DFM as "Structural Engine" | ❌ Unstable | ✅ statsmodels stable | Closing |
| Fuse dozens of signals | ❌ Pre-aggregated only | ✅ MIDAS bridge | Closing |
| Turning point detection | ❌ DFM broken | ✅ Stable DFM factors | Closing |
| Low noise/stability | ❌ 0% stability | ✅ > 90% target | Closing |

### D.2 Alignment with FORECASTING_CAPABILITIES.md

| Capability | Before | After | Status |
|------------|--------|-------|--------|
| Daily nowcasts | ❌ Not implemented | ✅ MIDAS bridge | Closing |
| Weekly nowcasts | ❌ Not implemented | ✅ MIDAS bridge | Closing |
| Mixed-frequency fusion | ❌ Not implemented | ✅ MIDAS bridge | Closing |
| Ragged-edge handling | ❌ Not implemented | ✅ MIDAS bridge | Closing |

### D.3 Alignment with ACCURACY_MAP.md

| Target | Before | After | Status |
|--------|--------|-------|--------|
| Elite tier (DFM + MIDAS + ML) | ❌ DFM broken | ✅ Full hybrid | Closing |
| sMAPE < 20% | ❌ N/A (DFM NaN) | ✅ Target | Pending |
| Prediction intervals | ⚠️ Partial | ✅ Full | Pending |

### D.4 Alignment with Calibration Requirements

**Source:** ACCURACY_MAP.md Section 5, FORECASTING_CAPABILITIES.md Section 5, IMPLEMENTATION_STATUS.md deployment gates

| Requirement | Before Refactor | After Refactor | Validation |
|-------------|-----------------|----------------|------------|
| 74-86% PI Coverage (ACCURACY_MAP 5.2) | Untested with DFM (DFM unstable) | ✅ R7.1.4 tests verify | Pending |
| ECE < 0.05 (deployment gate) | Tested in `test_complete_workflow.py` | ✅ Add to bridge pipeline tests | Pending |
| Low-noise vectors (FORECASTING_CAPABILITIES 5.3) | Depends on stable DFM | ✅ statsmodels provides stability | Pending |
| Calibrated bins for SN41 | Partially working (MIDAS/XGB only) | ✅ Full ensemble with DFM | Pending |

**Key Insight:** Calibration module (`models_src/calibration/`) is unchanged, but this refactor enables its use with DFM for the first time (DFM was previously unstable and excluded from calibrated pipelines).

**Validation Path:**
1. R7.1.4 adds calibration tests with bridge-produced features
2. Phase 6.3.1a re-validation exercises full pipeline including calibration
3. Coverage metrics recorded in R7.1.3 accuracy comparison table

---

## Change Log

| Date | Phase | Status | Notes |
|------|-------|--------|-------|
| 2025-12-04 | Plan Created | 📋 PLANNED | Comprehensive Option C plan with MIDAS Bridge |
| 2025-12-04 | Clarifications | 📋 UPDATED | Added: VintageManager details, Almon weight tests, MIDASLagConstructor reuse note, DynamicFactor rationale, vintage count confirmation |
| 2025-12-04 | Risk Analysis | 📋 UPDATED | Added: Phase 5 Impact Assessment, Interface Compatibility Layer (R3.2.3), Feature Naming Convention (R3.2.4), API Compatibility Guarantee (R4.2.1), Serialization Approach (R4.2.1), Determinism Enforcement (R4.2.1), state_space.py Decision Criteria (R4.2.2), Feature Versioning Rules (R5.2.1), Additional Script Updates (R5.2.2), Test Runtime Budget (R6), Data Preprocessing Requirements (R7.1.1) |
| 2025-12-04 | Calibration & Validation | 📋 UPDATED | Added: R5.3.3 Intra-Month Update Tests, R7.1.1 Fixture Migration Guidance, R7.1.4 Calibration Integration Validation, D.4 Calibration Requirements Alignment |

---

**End of DFM + MIDAS Bridge Refactor Plan (Option C)**


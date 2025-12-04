# DFM Refactor Plan: From Scratch → Battle-Tested Implementation

**Date Created:** 2025-12-03  
**Status:** 📋 PLANNED  
**Priority:** HIGH (Architectural Debt Resolution)  
**Estimated Effort:** 16-23 hours  
**Reference:** Phase 6.3.1a findings, `.cursorrules`, `TESTING_MATHEMATICAL_ALGORITHMS.md`

---

## Executive Summary

### Problem Statement

The current DFM (Dynamic Factor Model) implementation is a **custom "from scratch"** implementation that:
1. **Fails on real data:** 0/17 stable predictions (0% stability) with actual BLS CES data
2. **Has numerical instability:** Overflow in matrix multiplication, invalid values in Kalman filter
3. **Lacks production robustness:** Missing covariance tracking, hardcoded Kalman gain, no regularization
4. **Acknowledged in code:** Comment on line 496 states `"In production, would use statsmodels or specialized library"`

### Solution

Replace the custom DFM with a **battle-tested statsmodels implementation** (`statsmodels.tsa.statespace.dynamic_factor.DynamicFactor`) while:
- Maintaining the existing `BaseForecaster` interface
- Following strict TDD methodology
- Validating all affected phases
- Updating all documentation and tests

### Impact Scope

| Category | Count | Details |
|----------|-------|---------|
| Core Source Files | 3 | 1,072 lines to replace/update |
| DFM-Specific Tests | 64 | 1,454 lines to adapt |
| Integration Tests | ~15 | Tests using DFM |
| Documentation Files | 29 | 248 total mentions |
| Phases Affected | 2 | Phase 5.3, Phase 6.3.1a |

---

## Table of Contents

1. [Phase R1: Pre-Refactor Assessment](#phase-r1-pre-refactor-assessment)
2. [Phase R2: TDD Test Foundation](#phase-r2-tdd-test-foundation)
3. [Phase R3: Core Implementation](#phase-r3-core-implementation)
4. [Phase R4: Unit Test Validation](#phase-r4-unit-test-validation)
5. [Phase R5: Integration Validation](#phase-r5-integration-validation)
6. [Phase R6: Real Data Validation](#phase-r6-real-data-validation)
7. [Phase R7: Documentation Update](#phase-r7-documentation-update)
8. [Phase R8: Final Validation & Cleanup](#phase-r8-final-validation--cleanup)
9. [Appendix A: Files Inventory](#appendix-a-files-inventory)
10. [Appendix B: Test Inventory](#appendix-b-test-inventory)
11. [Appendix C: Rollback Plan](#appendix-c-rollback-plan)

---

## Phase R1: Pre-Refactor Assessment

**Purpose:** Establish baseline state and confirm understanding before making changes.  
**Estimated Time:** 1-2 hours  
**Blocking:** None  
**TDD:** N/A (assessment only)

### R1.1 Current State Documentation

- [ ] **R1.1.1** Run all existing DFM tests and record results
  ```bash
  docker compose exec etl pytest tests/models/test_dfm.py tests/models/test_dfm_properties.py tests/models/test_dfm_state_space.py -v --tb=short > /tmp/dfm_baseline_tests.txt 2>&1
  ```
  - Record: Number of tests, pass/fail counts, any warnings
  - Expected: 64 tests passing (with synthetic data)

- [ ] **R1.1.2** Run integration tests that use DFM
  ```bash
  docker compose exec etl pytest tests/integration/test_etl_features_models.py::TestETLFeaturesModelsIntegration::test_complete_pipeline_with_dfm -v
  docker compose exec etl pytest tests/integration/test_complete_workflow.py -v -k "dfm or DFM"
  ```
  - Record: Which tests pass/fail

- [ ] **R1.1.3** Run Phase 6.3.1a DFM validation tests
  ```bash
  docker compose exec etl pytest tests/backtests/test_dfm_validation.py -v -s
  ```
  - Record: Stability rate (expected: 0%), any errors

- [ ] **R1.1.4** Document current DFM interface
  - List all public methods: `__init__`, `fit`, `predict`, `get_params`, `save`, `load`
  - List all constructor parameters
  - List all fitted attributes (e.g., `loadings_`, `transition_`, `factors_`)

### R1.2 Backup Current Implementation

- [ ] **R1.2.1** Create backup branch
  ```bash
  git checkout -b backup/dfm-from-scratch-implementation
  git push origin backup/dfm-from-scratch-implementation
  git checkout main
  ```

- [ ] **R1.2.2** Copy current files to archive (for reference)
  ```bash
  mkdir -p docs/planning/archived/dfm_from_scratch
  cp models_src/dfm/dfm_model.py docs/planning/archived/dfm_from_scratch/
  cp models_src/dfm/state_space.py docs/planning/archived/dfm_from_scratch/
  ```

### R1.3 Verify statsmodels Availability

- [ ] **R1.3.1** Confirm statsmodels is in requirements.txt
  ```bash
  grep statsmodels requirements.txt
  ```

- [ ] **R1.3.2** Verify statsmodels.DynamicFactor is available in Docker
  ```bash
  docker compose exec etl python -c "from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor; print('OK')"
  ```

- [ ] **R1.3.3** Test basic statsmodels DynamicFactor usage
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
| Baseline test results recorded | Yes | [ ] |
| Backup branch created | Yes | [ ] |
| statsmodels available | Yes | [ ] |
| Current interface documented | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R2 until all R1 tasks are complete.**

---

## Phase R2: TDD Test Foundation

**Purpose:** Write tests FIRST that define expected behavior for the new implementation.  
**Estimated Time:** 3-4 hours  
**Blocking:** Phase R1 complete  
**TDD:** ✅ Tests written BEFORE implementation

### R2.1 Create New Test File for statsmodels DFM

- [ ] **R2.1.1** Create `tests/models/test_dfm_statsmodels.py`
  
  This file will contain tests that:
  1. Test the new interface (same as old)
  2. Test mathematical properties
  3. Test numerical stability (the key improvement)
  4. Test with real-world scale data

```python
"""
Tests for battle-tested DFM implementation using statsmodels.

This test file validates:
1. Interface compatibility with BaseForecaster
2. Mathematical properties of DFM (factor extraction, state-space)
3. Numerical stability with real-world scale data
4. Reproducibility and determinism

TDD: These tests are written BEFORE the implementation.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

# Import will fail until implementation exists
# from models_src.dfm.dfm_model import DynamicFactorModel


class TestDFMInterface:
    """Test DFM maintains BaseForecaster interface."""
    
    def test_inherits_from_base_forecaster(self):
        """DFM must inherit from BaseForecaster."""
        pass  # Implement
    
    def test_has_required_methods(self):
        """DFM must have fit, predict, get_params, save, load."""
        pass  # Implement
    
    def test_fit_returns_self(self):
        """fit() must return self for method chaining."""
        pass  # Implement
    
    def test_predict_returns_array(self):
        """predict() must return numpy array."""
        pass  # Implement


class TestDFMNumericalStability:
    """Test DFM handles real-world scale data without overflow."""
    
    def test_handles_large_values(self):
        """DFM must handle NFP-scale values (100K-300K) without overflow."""
        pass  # Implement
    
    def test_handles_covid_shock(self):
        """DFM must handle extreme values like COVID shock (-20M jobs)."""
        pass  # Implement
    
    def test_no_nan_predictions(self):
        """DFM must never produce NaN predictions."""
        pass  # Implement
    
    def test_no_inf_predictions(self):
        """DFM must never produce Inf predictions."""
        pass  # Implement
    
    def test_predictions_within_bounds(self):
        """DFM predictions must be within reasonable bounds (|pred| < 1M)."""
        pass  # Implement


class TestDFMMathematicalProperties:
    """Test DFM mathematical correctness."""
    
    def test_factors_extracted(self):
        """DFM must extract latent factors from data."""
        pass  # Implement
    
    def test_factor_count_matches_config(self):
        """Number of factors must match n_factors parameter."""
        pass  # Implement
    
    def test_loadings_shape_correct(self):
        """Loadings matrix must be (n_features, n_factors)."""
        pass  # Implement
    
    def test_explained_variance_positive(self):
        """Factors must explain positive variance."""
        pass  # Implement


class TestDFMReproducibility:
    """Test DFM determinism and reproducibility."""
    
    def test_same_seed_same_result(self):
        """Same random_state must produce identical results."""
        pass  # Implement
    
    def test_different_seed_different_result(self):
        """Different random_state must produce different results."""
        pass  # Implement


class TestDFMSaveLoad:
    """Test DFM serialization."""
    
    def test_save_creates_file(self):
        """save() must create a file at specified path."""
        pass  # Implement
    
    def test_load_restores_model(self):
        """load() must restore a model that produces same predictions."""
        pass  # Implement
```

- [ ] **R2.1.2** Run tests to confirm they fail (TDD red phase)
  ```bash
  docker compose exec etl pytest tests/models/test_dfm_statsmodels.py -v
  ```
  - Expected: All tests fail (ImportError or assertion failures)

### R2.2 Define Acceptance Criteria for New Implementation

- [ ] **R2.2.1** Create acceptance criteria checklist

| Criterion | Threshold | Test Method |
|-----------|-----------|-------------|
| Interface compatibility | 100% methods match | Unit tests |
| Numerical stability | 0 NaN/Inf predictions | Stability tests |
| Real data stability | > 90% stable vintages | Phase 6.3.1a tests |
| sMAPE on real data | < 20% | Accuracy tests |
| Reproducibility | Identical with same seed | Reproducibility tests |
| Save/load integrity | 100% prediction match | Serialization tests |

### R2.3 Gate Check: TDD Foundation

| Criterion | Required | Status |
|-----------|----------|--------|
| New test file created | Yes | [ ] |
| Tests fail (red phase) | Yes | [ ] |
| Acceptance criteria defined | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R3 until all R2 tasks are complete.**

---

## Phase R3: Core Implementation

**Purpose:** Implement the new statsmodels-based DFM.  
**Estimated Time:** 2-3 hours  
**Blocking:** Phase R2 complete  
**TDD:** ✅ Implementation to make tests pass

### R3.1 Implement New DynamicFactorModel

- [ ] **R3.1.1** Create new implementation in `models_src/dfm/dfm_model.py`

**Target Implementation Structure:**

```python
"""
Dynamic Factor Model (DFM) for Mixed-Frequency Nowcasting

Battle-tested implementation using statsmodels.tsa.statespace.dynamic_factor.

This implementation wraps statsmodels' DynamicFactor to provide:
- Numerical stability (no overflow with real NFP data)
- Proper Kalman filtering with computed gains
- State covariance tracking
- Production-ready error handling

References:
- statsmodels: https://www.statsmodels.org/stable/statespace.html
- Stock & Watson (2002): "Forecasting Using Principal Components..."
"""

from typing import Dict, Any, Optional
from pathlib import Path
import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
from loguru import logger
import joblib

from models_src.utils.base_model import BaseForecaster


class DynamicFactorModel(BaseForecaster):
    """
    Dynamic Factor Model using statsmodels for numerical stability.
    
    Wraps statsmodels.tsa.statespace.dynamic_factor.DynamicFactor to provide:
    - Compatible interface with BaseForecaster
    - Proper Kalman filtering (not simplified)
    - Numerical stability with real-world scale data
    - Deterministic training with random_state
    
    Parameters:
        n_factors: Number of latent factors to extract
        factor_order: AR order for factor dynamics (default: 1)
        random_state: Random seed for reproducibility
    
    Example:
        >>> dfm = DynamicFactorModel(n_factors=2, random_state=42)
        >>> dfm.fit(X_train, y_train, vintage_date='2024-11-15')
        >>> predictions = dfm.predict(X_test)
    """
    
    def __init__(
        self,
        n_factors: int,
        factor_order: int = 1,
        random_state: int = 42
    ):
        """Initialize DynamicFactorModel."""
        super().__init__(random_state=random_state)
        
        if n_factors <= 0:
            raise ValueError(f"n_factors must be positive, got {n_factors}")
        
        self.n_factors = n_factors
        self.factor_order = factor_order
        self.is_fitted = False
        
        # Will be set during fit
        self.model_: Optional[DynamicFactor] = None
        self.results_ = None
        self.feature_names_: Optional[list] = None
        self.n_features_: Optional[int] = None
        
        # Standardization parameters
        self.X_mean_: Optional[np.ndarray] = None
        self.X_std_: Optional[np.ndarray] = None
        self.y_mean_: Optional[float] = None
        self.y_std_: Optional[float] = None
        
        # Prediction model (regress y on factors)
        self.prediction_coef_: Optional[np.ndarray] = None
        self.prediction_intercept_: Optional[float] = None
        
        logger.info(
            "Initialized DynamicFactorModel (statsmodels)",
            extra={
                'n_factors': n_factors,
                'factor_order': factor_order,
                'random_state': random_state
            }
        )
    
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        vintage_date: str
    ) -> 'DynamicFactorModel':
        """
        Train DFM on provided data using statsmodels.
        
        Args:
            X: Feature matrix (N_samples x N_features)
            y: Target variable (N_samples)
            vintage_date: Training data vintage (YYYY-MM-DD format)
            
        Returns:
            self: For method chaining
        """
        # Validate inputs
        self._validate_fit_inputs(X, y, vintage_date)
        
        # Store metadata
        self.vintage_date = vintage_date
        self.n_features_ = X.shape[1]
        self.feature_names_ = list(X.columns)
        
        # Set random seed
        np.random.seed(self.random_state)
        
        # Standardize features
        self.X_mean_ = X.mean().values
        self.X_std_ = X.std().values + 1e-8
        X_scaled = (X.values - self.X_mean_) / self.X_std_
        
        # Standardize target
        self.y_mean_ = y.mean()
        self.y_std_ = y.std() + 1e-8
        y_scaled = (y.values - self.y_mean_) / self.y_std_
        
        logger.info(
            "Fitting DynamicFactorModel",
            extra={
                'n_samples': len(X),
                'n_features': self.n_features_,
                'n_factors': self.n_factors,
                'vintage_date': vintage_date
            }
        )
        
        # Fit statsmodels DynamicFactor
        try:
            self.model_ = DynamicFactor(
                endog=X_scaled,
                k_factors=self.n_factors,
                factor_order=self.factor_order
            )
            self.results_ = self.model_.fit(disp=False)
            
            # Extract factors
            factors = self.results_.factors.filtered.T  # (n_samples, n_factors)
            
            # Train prediction model: regress y on factors
            self._train_prediction_model(factors, y_scaled)
            
            self.is_fitted = True
            
            logger.info(
                "DynamicFactorModel fitted successfully",
                extra={
                    'llf': float(self.results_.llf),
                    'aic': float(self.results_.aic)
                }
            )
            
        except Exception as e:
            logger.error(f"DFM fitting failed: {e}", exc_info=True)
            raise
        
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Generate predictions using trained DFM.
        
        Args:
            X: Feature matrix (N_samples x N_features)
            
        Returns:
            predictions: Array of predictions (N_samples,)
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction. Call fit() first.")
        
        # Validate features match training
        if list(X.columns) != self.feature_names_:
            raise ValueError(
                f"Feature names do not match training. "
                f"Expected {self.feature_names_}, got {list(X.columns)}"
            )
        
        # Standardize using training statistics
        X_scaled = (X.values - self.X_mean_) / self.X_std_
        
        # Extract factors using Kalman filter
        # Use the fitted model to filter new observations
        factors = self._extract_factors(X_scaled)
        
        # Predict using factor-to-target regression
        predictions_scaled = factors @ self.prediction_coef_ + self.prediction_intercept_
        
        # Rescale to original scale
        predictions = predictions_scaled * self.y_std_ + self.y_mean_
        
        return predictions
    
    def _extract_factors(self, X_scaled: np.ndarray) -> np.ndarray:
        """Extract factors from new data using Kalman filter."""
        # Apply the fitted filter to new data
        # Note: statsmodels provides this via apply() method
        filtered = self.model_.smooth(X_scaled)
        return filtered.factors.filtered.T
    
    def _train_prediction_model(self, factors: np.ndarray, y_scaled: np.ndarray) -> None:
        """Train linear regression from factors to target."""
        from scipy import linalg
        
        # Add intercept
        F_with_intercept = np.column_stack([factors, np.ones(len(factors))])
        
        # Least squares
        coef = linalg.lstsq(F_with_intercept, y_scaled)[0]
        
        self.prediction_coef_ = coef[:-1]
        self.prediction_intercept_ = coef[-1]
    
    def _validate_fit_inputs(self, X, y, vintage_date):
        """Validate fit inputs."""
        import re
        
        if len(X) != len(y):
            raise ValueError(f"X and y must have same length. Got X: {len(X)}, y: {len(y)}")
        
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', vintage_date):
            raise ValueError(f"vintage_date must be in YYYY-MM-DD format, got '{vintage_date}'")
        
        if X.shape[1] < self.n_factors:
            logger.warning(
                f"Number of features ({X.shape[1]}) < n_factors ({self.n_factors}). "
                "Consider reducing n_factors."
            )
    
    def get_params(self) -> Dict[str, Any]:
        """Get model parameters."""
        params = {
            'n_factors': self.n_factors,
            'factor_order': self.factor_order,
            'random_state': self.random_state,
            'is_fitted': self.is_fitted,
            'vintage_date': getattr(self, 'vintage_date', None),
            'n_features': self.n_features_,
            'implementation': 'statsmodels'  # Mark as battle-tested
        }
        
        if self.is_fitted and self.results_ is not None:
            params['llf'] = float(self.results_.llf)
            params['aic'] = float(self.results_.aic)
        
        return params
    
    def save(self, path: Path) -> None:
        """Save model to disk."""
        if not self.is_fitted:
            raise ValueError("Model must be fitted before saving.")
        
        model_data = {
            # Hyperparameters
            'n_factors': self.n_factors,
            'factor_order': self.factor_order,
            'random_state': self.random_state,
            
            # Metadata
            'vintage_date': self.vintage_date,
            'n_features_': self.n_features_,
            'feature_names_': self.feature_names_,
            
            # Standardization
            'X_mean_': self.X_mean_,
            'X_std_': self.X_std_,
            'y_mean_': self.y_mean_,
            'y_std_': self.y_std_,
            
            # Prediction model
            'prediction_coef_': self.prediction_coef_,
            'prediction_intercept_': self.prediction_intercept_,
            
            # statsmodels results (pickle the params, not the whole model)
            'results_params_': self.results_.params if self.results_ else None,
            
            # Base model metadata
            'model_id': self.model_id,
            'created_at': self.created_at,
            
            # Implementation marker
            'implementation': 'statsmodels'
        }
        
        joblib.dump(model_data, path)
        logger.info(f"Model saved to {path}")
    
    @classmethod
    def load(cls, path: Path) -> 'DynamicFactorModel':
        """Load model from disk."""
        model_data = joblib.load(path)
        
        # Reconstruct model
        model = cls(
            n_factors=model_data['n_factors'],
            factor_order=model_data.get('factor_order', 1),
            random_state=model_data['random_state']
        )
        
        # Restore attributes
        model.vintage_date = model_data['vintage_date']
        model.n_features_ = model_data['n_features_']
        model.feature_names_ = model_data['feature_names_']
        model.X_mean_ = model_data['X_mean_']
        model.X_std_ = model_data['X_std_']
        model.y_mean_ = model_data['y_mean_']
        model.y_std_ = model_data['y_std_']
        model.prediction_coef_ = model_data['prediction_coef_']
        model.prediction_intercept_ = model_data['prediction_intercept_']
        model.model_id = model_data['model_id']
        model.created_at = model_data['created_at']
        model.is_fitted = True
        
        # Note: Full statsmodels model not restored (would need to refit)
        # For prediction, we only need the prediction coefficients
        
        logger.info(f"Model loaded from {path}")
        return model
```

### R3.2 Update Module Exports

- [ ] **R3.2.1** Update `models_src/dfm/__init__.py`

```python
"""
Dynamic Factor Model (DFM) module

Provides mixed-frequency nowcasting using statsmodels state-space models.
Battle-tested implementation replacing custom from-scratch version.
"""

from models_src.dfm.dfm_model import DynamicFactorModel

# Note: state_space.py utilities may be deprecated or removed
# Keep only if needed for other purposes

__all__ = [
    'DynamicFactorModel',
]
```

### R3.3 Gate Check: Core Implementation

| Criterion | Required | Status |
|-----------|----------|--------|
| New dfm_model.py created | Yes | [ ] |
| __init__.py updated | Yes | [ ] |
| Code compiles without errors | Yes | [ ] |
| Basic import works | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R4 until all R3 tasks are complete.**

---

## Phase R4: Unit Test Validation

**Purpose:** Run all DFM unit tests and ensure they pass.  
**Estimated Time:** 4-6 hours  
**Blocking:** Phase R3 complete  
**TDD:** ✅ Green phase - make tests pass

### R4.1 Run New TDD Tests

- [ ] **R4.1.1** Run the new statsmodels tests
  ```bash
  docker compose exec etl pytest tests/models/test_dfm_statsmodels.py -v
  ```
  - Target: All tests pass

- [ ] **R4.1.2** Fix any failing tests by adjusting implementation
  - Document each fix
  - Ensure fixes don't break interface

### R4.2 Update Existing DFM Tests

- [ ] **R4.2.1** Update `tests/models/test_dfm.py` (25 tests)
  
  Changes needed:
  - Remove references to internal attributes that no longer exist
  - Update convergence tests (no longer EM-based)
  - Keep interface tests unchanged
  - Update any tests checking `max_iter` (statsmodels uses different params)

- [ ] **R4.2.2** Update `tests/models/test_dfm_properties.py` (13 tests)
  
  Changes needed:
  - Adapt EM-specific tests to statsmodels equivalents
  - Keep mathematical property tests
  - Update stability checks

- [ ] **R4.2.3** Evaluate `tests/models/test_dfm_state_space.py` (26 tests)
  
  Decision required:
  - If state_space.py is kept: Update tests
  - If state_space.py is deprecated: Mark tests as skip or delete
  - Document decision

### R4.3 Run All DFM Tests

- [ ] **R4.3.1** Run complete DFM test suite
  ```bash
  docker compose exec etl pytest tests/models/test_dfm*.py -v --tb=short
  ```
  - Target: All tests pass (or documented skips)

- [ ] **R4.3.2** Record test results
  - Number passing
  - Number skipped (with reasons)
  - Any remaining failures (with fix plan)

### R4.4 Gate Check: Unit Tests

| Criterion | Required | Status |
|-----------|----------|--------|
| New TDD tests pass | Yes | [ ] |
| test_dfm.py passes | Yes | [ ] |
| test_dfm_properties.py passes | Yes | [ ] |
| test_dfm_state_space.py handled | Yes | [ ] |
| All DFM tests pass | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R5 until all R4 tasks are complete.**

---

## Phase R5: Integration Validation

**Purpose:** Validate DFM works correctly in integrated pipelines.  
**Estimated Time:** 2-3 hours  
**Blocking:** Phase R4 complete

### R5.1 Update Integration Tests

- [ ] **R5.1.1** Update `tests/integration/test_etl_features_models.py`
  
  Locate `test_complete_pipeline_with_dfm` and verify:
  - DFM initialization works
  - DFM fit works
  - DFM predict works
  - Results are reasonable

- [ ] **R5.1.2** Update `tests/integration/test_complete_workflow.py`
  
  Update any tests that use DFM:
  - Lines ~260, ~515, ~618, ~1138 reference DFM
  - Verify interface compatibility
  - Check ensemble integration

### R5.2 Run Integration Tests

- [ ] **R5.2.1** Run ETL→Features→Models integration
  ```bash
  docker compose exec etl pytest tests/integration/test_etl_features_models.py -v
  ```

- [ ] **R5.2.2** Run complete workflow integration
  ```bash
  docker compose exec etl pytest tests/integration/test_complete_workflow.py -v
  ```

- [ ] **R5.2.3** Run ensemble pipeline tests
  ```bash
  docker compose exec etl pytest tests/models/test_ensemble_pipeline.py -v
  ```

### R5.3 Pipeline Integration Check

- [ ] **R5.3.1** Verify train_pipeline.py works with new DFM
  ```bash
  docker compose exec etl python -c "
  from models_src.dfm.dfm_model import DynamicFactorModel
  from models_src.pipelines.train_pipeline import train_model
  import pandas as pd
  import numpy as np
  
  # Create test data
  X = pd.DataFrame(np.random.randn(100, 5), columns=[f'f{i}' for i in range(5)])
  y = pd.Series(np.random.randn(100))
  
  # Train
  model = DynamicFactorModel(n_factors=2, random_state=42)
  trained = train_model(model, X, y, '2024-01-15')
  print('train_pipeline integration: OK')
  "
  ```

- [ ] **R5.3.2** Verify ensemble_pipeline.py works with new DFM
  ```bash
  docker compose exec etl python -c "
  from models_src.dfm.dfm_model import DynamicFactorModel
  from models_src.midas.midas_model import MIDASRegression
  from models_src.pipelines.ensemble_pipeline import EnsembleForecaster, EnsembleConfig, EnsembleMethod
  import pandas as pd
  import numpy as np
  
  # Create test data
  X = pd.DataFrame(np.random.randn(100, 5), columns=[f'f{i}' for i in range(5)])
  y = pd.Series(np.random.randn(100))
  
  # Train models
  dfm = DynamicFactorModel(n_factors=2, random_state=42)
  dfm.fit(X[:80], y[:80], '2024-01-15')
  
  midas = MIDASRegression(random_state=42)
  midas.fit(X[:80], y[:80], '2024-01-15')
  
  # Create ensemble
  config = EnsembleConfig(
      method=EnsembleMethod.SIMPLE_AVERAGE,
      model_names=['dfm', 'midas']
  )
  ensemble = EnsembleForecaster(models={'dfm': dfm, 'midas': midas}, config=config)
  preds = ensemble.predict(X[80:])
  print(f'Ensemble predictions shape: {preds.shape}')
  print('ensemble_pipeline integration: OK')
  "
  ```

### R5.4 Gate Check: Integration

| Criterion | Required | Status |
|-----------|----------|--------|
| ETL→Features→Models tests pass | Yes | [ ] |
| Complete workflow tests pass | Yes | [ ] |
| Ensemble pipeline tests pass | Yes | [ ] |
| train_pipeline.py works | Yes | [ ] |
| ensemble_pipeline.py works | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R6 until all R5 tasks are complete.**

---

## Phase R6: Real Data Validation

**Purpose:** Validate DFM works on real BLS CES data (the critical test).  
**Estimated Time:** 2-3 hours  
**Blocking:** Phase R5 complete

### R6.1 Run Phase 6.3.1a Validation

- [ ] **R6.1.1** Update `tests/backtests/test_dfm_validation.py` if needed
  - Ensure it uses the new DFM interface
  - Keep all validation criteria

- [ ] **R6.1.2** Run DFM validation with real data
  ```bash
  docker compose exec etl pytest tests/backtests/test_dfm_validation.py -v -s
  ```

- [ ] **R6.1.3** Record results
  
  | Metric | Old (From Scratch) | New (statsmodels) | Target |
  |--------|--------------------|--------------------|--------|
  | Stability Rate | 0% (0/17) | ? | > 90% |
  | NaN Predictions | Many | ? | 0 |
  | Overflow Errors | Yes | ? | No |
  | Avg sMAPE | N/A | ? | < 20% |

### R6.2 Compare with Other Models

- [ ] **R6.2.1** Run model comparison
  ```bash
  docker compose exec etl pytest tests/backtests/test_dfm_validation.py::TestModelComparison -v -s
  ```

- [ ] **R6.2.2** Record comparison results
  
  | Model | Stability | Avg sMAPE | Recommendation |
  |-------|-----------|-----------|----------------|
  | DFM (new) | ? | ? | ? |
  | MIDAS | 100% | TBD | ✅ Include |
  | XGBoost | 100% | TBD | ✅ Include |

### R6.3 DFM Ensemble Decision

Based on R6.1 and R6.2 results:

- [ ] **R6.3.1** Decide: Include DFM in production ensemble?
  
  | Criterion | Threshold | Result | Pass? |
  |-----------|-----------|--------|-------|
  | Stability | > 90% | ? | ? |
  | sMAPE | < 20% | ? | ? |
  | No NaN/Inf | 100% | ? | ? |
  | Adds ensemble value | Improves combined | ? | ? |

- [ ] **R6.3.2** Document decision and rationale

### R6.4 Gate Check: Real Data

| Criterion | Required | Status |
|-----------|----------|--------|
| DFM validation tests run | Yes | [ ] |
| Stability rate recorded | Yes | [ ] |
| sMAPE recorded | Yes | [ ] |
| Ensemble decision made | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R7 until all R6 tasks are complete.**

---

## Phase R7: Documentation Update

**Purpose:** Update all documentation to reflect new implementation.  
**Estimated Time:** 3-4 hours  
**Blocking:** Phase R6 complete

### R7.1 Update Core Documentation

- [ ] **R7.1.1** Update `docs/planning/IMPLEMENTATION_STATUS.md`
  - Update Phase 5.3 status
  - Update Phase 6.3.1a results
  - Update Phase 6.4.2.1 ensemble decision
  - Add reference to this refactor plan

- [ ] **R7.1.2** Update `docs/planning/PHASE_6_3_1a_COMPLETION_SUMMARY.md`
  - Replace old results with new results
  - Update recommendation

- [ ] **R7.1.3** Update `docs/5_PILLARS.md` if needed
  - Verify DFM description is still accurate

- [ ] **R7.1.4** Update `docs/ACCURACY_DESCRIPTION.md` if needed
  - Verify tier descriptions

### R7.2 Update Phase 5 Documentation

- [ ] **R7.2.1** Update `docs/planning/phase_5/PHASE_5_IMPLEMENTATION_PLAN.md`
  - Update DFM implementation notes
  - Mark as "re-implemented with statsmodels"

- [ ] **R7.2.2** Update `docs/planning/phase_5/PHASE_5_MATHEMATICAL_VALIDATION_COMPLETE.md`
  - Update property test references

- [ ] **R7.2.3** Update `docs/planning/phase_5/PHASE_5_13_2_COMPLETION_SUMMARY.md`
  - Update DFM integration notes

### R7.3 Update Testing Documentation

- [ ] **R7.3.1** Update `docs/TESTING_MATHEMATICAL_ALGORITHMS.md`
  - Update DFM examples to use statsmodels

- [ ] **R7.3.2** Update `docs/planning/phase_5/PHASE_5_TDD_BLINDSPOT_ANALYSIS.md`
  - Add lessons learned from DFM refactor

### R7.4 Update Configuration Files

- [ ] **R7.4.1** Update `tests/fixtures/performance_baselines.json`
  - Update DFM performance targets if different

### R7.5 Gate Check: Documentation

| Criterion | Required | Status |
|-----------|----------|--------|
| IMPLEMENTATION_STATUS.md updated | Yes | [ ] |
| PHASE_6_3_1a_COMPLETION_SUMMARY.md updated | Yes | [ ] |
| Phase 5 docs updated | Yes | [ ] |
| Testing docs updated | Yes | [ ] |
| Performance baselines updated | Yes | [ ] |

**⚠️ DO NOT PROCEED to Phase R8 until all R7 tasks are complete.**

---

## Phase R8: Final Validation & Cleanup

**Purpose:** Complete final validation and cleanup.  
**Estimated Time:** 1-2 hours  
**Blocking:** Phase R7 complete

### R8.1 Run Full Test Suite

- [ ] **R8.1.1** Run all model tests
  ```bash
  docker compose exec etl pytest tests/models/ -v --tb=short
  ```
  - Target: All tests pass

- [ ] **R8.1.2** Run all integration tests
  ```bash
  docker compose exec etl pytest tests/integration/ -v --tb=short
  ```
  - Target: All tests pass

- [ ] **R8.1.3** Run all backtest tests
  ```bash
  docker compose exec etl pytest tests/backtests/ -v --tb=short
  ```
  - Target: All tests pass

### R8.2 Code Quality Check

- [ ] **R8.2.1** Run linting
  ```bash
  docker compose exec etl ruff check models_src/dfm/
  docker compose exec etl mypy models_src/dfm/ --ignore-missing-imports
  ```

- [ ] **R8.2.2** Verify no TODO comments left
  ```bash
  grep -r "TODO" models_src/dfm/
  ```

### R8.3 Cleanup

- [ ] **R8.3.1** Decide on state_space.py
  - [ ] Keep: If used elsewhere or for future extension
  - [ ] Deprecate: Mark as deprecated with warning
  - [ ] Delete: Remove if no longer needed

- [ ] **R8.3.2** Remove any backup/temporary files

- [ ] **R8.3.3** Update this plan with final status

### R8.4 Final Documentation

- [ ] **R8.4.1** Create completion summary
  
  Record final metrics:
  
  | Metric | Before | After |
  |--------|--------|-------|
  | DFM Tests Passing | 64/64 | ?/? |
  | Integration Tests | ?/? | ?/? |
  | Real Data Stability | 0% | ?% |
  | sMAPE | N/A | ?% |
  | In Production Ensemble | No | ?|

- [ ] **R8.4.2** Mark this plan as COMPLETE

### R8.5 Gate Check: Final

| Criterion | Required | Status |
|-----------|----------|--------|
| All model tests pass | Yes | [ ] |
| All integration tests pass | Yes | [ ] |
| All backtest tests pass | Yes | [ ] |
| Linting passes | Yes | [ ] |
| Cleanup complete | Yes | [ ] |
| Completion summary created | Yes | [ ] |

---

## Appendix A: Files Inventory

### Core Source Files

| File | Lines | Action |
|------|-------|--------|
| `models_src/dfm/dfm_model.py` | 612 | **REPLACE** |
| `models_src/dfm/state_space.py` | 437 | **EVALUATE** (keep/deprecate/delete) |
| `models_src/dfm/__init__.py` | 23 | **UPDATE** |

### Test Files

| File | Tests | Lines | Action |
|------|-------|-------|--------|
| `tests/models/test_dfm.py` | 25 | 508 | **UPDATE** |
| `tests/models/test_dfm_properties.py` | 13 | 493 | **UPDATE** |
| `tests/models/test_dfm_state_space.py` | 26 | 453 | **EVALUATE** |
| `tests/models/test_dfm_statsmodels.py` | NEW | NEW | **CREATE** |
| `tests/integration/test_complete_workflow.py` | ~6 | ~1351 | **UPDATE** DFM usage |
| `tests/integration/test_etl_features_models.py` | 1 | ~546 | **UPDATE** DFM usage |
| `tests/backtests/test_dfm_validation.py` | 5 | ~700 | **UPDATE** DFM usage |
| `tests/models/test_ensemble_pipeline.py` | - | ~957 | **REVIEW** docstrings |
| `tests/models/test_mlflow_logger.py` | - | - | **REVIEW** references |

### Pipeline Files

| File | Action |
|------|--------|
| `models_src/pipelines/ensemble_pipeline.py` | **REVIEW** docstrings |
| `models_src/pipelines/train_pipeline.py` | **REVIEW** examples |

### Configuration Files

| File | Action |
|------|--------|
| `tests/fixtures/performance_baselines.json` | **UPDATE** if needed |

### Documentation Files (29 files, 248 mentions)

Priority files to update:
1. `docs/planning/IMPLEMENTATION_STATUS.md` (45 mentions)
2. `docs/planning/PHASE_6_3_1a_COMPLETION_SUMMARY.md` (31 mentions)
3. `docs/planning/phase_5/PHASE_5_IMPLEMENTATION_PLAN.md` (43 mentions)
4. `docs/planning/phase_5/PHASE_5_13_2_COMPLETION_SUMMARY.md` (30 mentions)
5. `docs/planning/codex_analyses/codex_analysis_25.md` (30 mentions)

---

## Appendix B: Test Inventory

### Unit Tests (64 total)

**test_dfm.py (25 tests):**
- TestDFMInitialization (4 tests)
- TestDFMFit (3 tests)
- TestDFMPredict (4 tests)
- TestDFMSaveLoad (4 tests)
- TestDFMReproducibility (3 tests)
- TestDFMEdgeCases (4 tests)
- TestDFMMissingData (3 tests)

**test_dfm_properties.py (13 tests):**
- TestEMLikelihood (3 tests)
- TestKalmanProperties (4 tests)
- TestFactorProperties (3 tests)
- TestConvergence (3 tests)

**test_dfm_state_space.py (26 tests):**
- TestStateSpaceRepresentation (6 tests)
- TestBuildTransitionMatrix (7 tests)
- TestBuildObservationMatrix (7 tests)
- TestValidateDimensions (6 tests)

### Integration Tests Using DFM

| Test File | Test Name |
|-----------|-----------|
| test_etl_features_models.py | `test_complete_pipeline_with_dfm` |
| test_complete_workflow.py | Multiple tests create DFM instances |
| test_dfm_validation.py | All 5 tests use DFM |

---

## Appendix C: Rollback Plan

If the refactor causes issues that cannot be resolved:

### Immediate Rollback

```bash
# 1. Checkout backup branch
git checkout backup/dfm-from-scratch-implementation

# 2. Copy files back
cp models_src/dfm/dfm_model.py /tmp/dfm_statsmodels_backup.py
git checkout main
git checkout backup/dfm-from-scratch-implementation -- models_src/dfm/
```

### Partial Rollback

If only certain tests fail:

1. Keep new implementation
2. Add compatibility shim for failing tests
3. Document issues for future fix

### Decision Criteria for Rollback

| Scenario | Action |
|----------|--------|
| > 20% tests fail after 4 hours debugging | Rollback |
| Integration tests fundamentally broken | Rollback |
| Real data stability < 50% | Keep but exclude from ensemble |
| Documentation update incomplete | Continue, don't rollback |

---

## Change Log

| Date | Phase | Status | Notes |
|------|-------|--------|-------|
| 2025-12-03 | Plan Created | 📋 PLANNED | Initial comprehensive plan |

---

**End of DFM Refactor Plan**


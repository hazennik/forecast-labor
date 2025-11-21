# PHASE 5: MODEL DEVELOPMENT - IMPLEMENTATION PLAN

**Status:** Ready to Begin (Phases 1-4 Complete, Scope Updated 2025-11-19)  
**Duration Estimate:** 3.5-4.5 weeks (Week 5-8.5)  
**Approach:** TDD/Test-Alongside (established in Phase 4)  
**New Deliverables:** Feature Registry Database + X-13 Quality Enhancement

---

## 📋 HOW TO USE THIS PLAN

### Working Through The Checklist

1. **Start at the top** - Follow sections in order (dependencies matter)
2. **Check boxes as you complete** - Use `- [x]` syntax in this file
3. **Update IMPLEMENTATION_STATUS.md** - Mark corresponding items (see instructions below)
4. **Commit frequently** - Prompt the user to commit after each component is completed
5. **Run tests continuously** - Don't wait until the end

### Updating IMPLEMENTATION_STATUS.md

**After completing each major section (5.1-5.13), update the corresponding section in IMPLEMENTATION_STATUS.md:**

#### Location in IMPLEMENTATION_STATUS.md
Find the Phase 5 TODO section (starts around line 815):
- Core Models (lines 815-825)
- Model Infrastructure (lines 827-831)
- Feature Registry Enhancement (lines 833-842)
- Quality Gates Enhancement (lines 844-852)
- Testing (lines 854-865)
- Documentation (lines 867-872)

#### How to Mark Complete
Change `- [ ]` to `- [x]` for completed items:

```markdown
# Before
- [ ] Dynamic Factor Model (DFM)

# After
- [x] Dynamic Factor Model (DFM)
```

#### Update Phase Percentage
At the top of IMPLEMENTATION_STATUS.md (line 3), update the status:
```markdown
# Example progression
Last Updated: 2025-11-19 (Phase 5: 15% - Infrastructure Complete)
Last Updated: 2025-11-19 (Phase 5: 30% - Feature Registry DB Complete)
Last Updated: 2025-11-19 (Phase 5: 50% - Core Models Complete)
Last Updated: 2025-11-19 (Phase 5: 75% - Calibration & Reconciliation Complete)
Last Updated: 2025-11-19 (Phase 5: 100% - COMPLETE)
```

#### Mapping This Plan to IMPLEMENTATION_STATUS.md

| This Plan Section | IMPLEMENTATION_STATUS.md Line | Item to Mark |
|-------------------|-------------------------------|--------------|
| 5.1 Model Infrastructure | 827-831 | Model utilities (metrics, IO, MLflow loggers) |
| 5.2 Feature Registry DB | 834-842 | Database persistence for feature registry |
| 5.3 DFM | 816 | Dynamic Factor Model (DFM) |
| 5.4 MIDAS | 817 | MIDAS regression |
| 5.5 GBM | 818 | XGBoost quantile model |
| 5.6 Calibration | 820 | Calibration layer |
| 5.7 Revision Model | 819 | Revision model |
| 5.8 MinT/WLS | 821-825 | Hierarchical reconciliation (MinT/WLS) |
| 5.9 Training Pipelines | 828 | Training pipelines (Prefect workflows) |
| 5.10 Model Registry | 829-831 | Model registry integration + Artifact versioning |
| 5.11 X-13 Quality | 845-851 | Full X-13 seasonal diagnostics quality verification |
| 5.12 Integration Test | 864 | End-to-end integration test |
| 5.13 Documentation | 867-872 | All documentation items |

---

## 📋 PRE-FLIGHT CHECKLIST

### Before Starting Phase 5
- [x] **Read updated Phase 5 scope:** Review lines 815-878 in IMPLEMENTATION_STATUS.md
- [x] **Review PHASE_5_SCOPE_UPDATE.md:** Understand what was added and why
- [x] **Verify Phase 4 completion:** Ensure feature registry (in-memory) is working
- [x] **Verify test infrastructure:** Run `pytest` → 305/305 passing (100% pass rate) ✅
- [x] **Verify services:** Run `make up` and `python scripts/check_infrastructure_health.py`
- [x] **Check PostgreSQL availability:** Confirm database accessible for feature registry
- [x] **Check MLflow availability:** Confirm model tracking service operational
- [x] **Review accuracy targets:** Elite tier (sMAPE < 15%, RMSE < 50K)
- [x] **Fix test failures:** Fixed 3 vintage validator tests (logic reorder, parquet metadata, attrs handling)

**✅ COMPLETE:** Pre-flight checklist 100% - Ready for Phase 5.1 implementation

---

## 🏗️ PHASE 5 IMPLEMENTATION (Test-Alongside Approach)

### 5.1. Model Infrastructure & Utilities (Week 5, Days 1-2)

**Goal:** Build shared infrastructure before implementing individual models

**Update IMPLEMENTATION_STATUS.md:** Line 827-831 when complete

#### 5.1.1. Model Base Classes
- [x] **Create:** `models_src/utils/base_model.py`
  - [x] `BaseForecaster` abstract class (fit, predict, save, load methods)
  - [x] Type hints for all methods
  - [x] Docstrings (Google/NumPy style)
  - [x] Deterministic seed handling
  - [x] Vintage-aware training interface
- [x] **Test:** `tests/models/test_base_model.py`
  - [x] Mock implementation test
  - [x] Abstract method enforcement test
  - [x] Seed reproducibility test
  - [x] Vintage parameter validation

**✅ COMPLETE** (17 tests passing, 322/322 total)

#### 5.1.2. Metrics & Evaluation
- [x] **Create:** `models_src/utils/metrics.py`
  - [x] RMSE (Root Mean Squared Error)
  - [x] sMAPE (Symmetric Mean Absolute Percentage Error)
  - [x] CRPS (Continuous Ranked Probability Score)
  - [x] Turning point detection accuracy
  - [x] Prediction interval coverage (80%, 90%, 95%)
  - [x] Expected Calibration Error (ECE)
  - [x] All functions with type hints & docstrings
- [x] **Test:** `tests/models/test_metrics.py`
  - [x] Unit tests for each metric (known inputs → expected outputs)
  - [x] Edge case tests (zeros, negative values, NaNs)
  - [x] Interval coverage validation tests
  - [x] ECE calculation validation

**✅ COMPLETE** (33 tests passing, 355/355 total)

#### 5.1.3. Model I/O & Serialization
- [x] **Create:** `models_src/utils/io.py`
  - [x] Model save/load functions (pickle, joblib)
  - [x] Artifact versioning (SHA256 hashing)
  - [x] Model metadata (training date, features, hyperparams, vintage)
  - [x] Signature verification helpers
  - [x] Integration with feature registry (link models to features used)
- [x] **Test:** `tests/models/test_io.py`
  - [x] Save/load round-trip tests
  - [x] Metadata integrity tests
  - [x] Hash verification tests
  - [x] Feature registry integration test

#### 5.1.4. MLflow Integration
- [x] **Create:** `models_src/utils/mlflow_logger.py`
  - [x] Experiment tracking wrapper
  - [x] Hyperparameter logging
  - [x] Metric logging (train/val/test)
  - [x] Artifact logging (models, plots)
  - [x] Model registry integration
  - [x] Feature metadata logging
- [x] **Test:** `tests/models/test_mlflow_logger.py`
  - [x] Mock MLflow client tests
  - [x] Logging format validation
  - [x] Registry integration tests
  - [x] Feature metadata logging test

**✅ COMPLETE:** 33 tests passing
- All model utilities complete (metrics, IO, MLflow loggers)
- Phase 5 infrastructure foundation ready

---

### 5.2. Feature Registry Database Migration (Week 5, Days 3-4) ✨ NEW

**Goal:** Migrate feature registry from in-memory to PostgreSQL for production persistence

**Update IMPLEMENTATION_STATUS.md:** Lines 834-842 when complete

#### 5.2.1. Database Schema Design
- [ ] **Create:** `infra/postgres/feature_registry_schema.sql`
  - [ ] `features.feature_metadata` table
    - Columns: feature_id, name, source, frequency, vintage_date, created_at, version
  - [ ] `features.feature_transforms` table (lineage tracking)
    - Columns: feature_id, transform_type, transform_params, parent_feature_id
  - [ ] `features.feature_versions` table (versioning)
    - Columns: feature_id, version, checksum, deprecation_date
  - [ ] Indexes on feature_id, name, source, vintage_date, version
  - [ ] Foreign key constraints for referential integrity
- [ ] **Document:** Add schema diagram to `docs/DATABASE_SCHEMA.md`

#### 5.2.2. Feature Registry Database Backend
- [ ] **Update:** `features/registry.py`
  - [ ] Add `DatabaseBackend` class (PostgreSQL connection)
  - [ ] Implement `register_feature()` with database insert
  - [ ] Implement `get_feature()` with database query
  - [ ] Implement `list_features()` with filtering/pagination
  - [ ] Implement `update_feature()` and `delete_feature()`
  - [ ] Implement lineage tracking methods
  - [ ] Implement versioning methods (create_version, rollback)
  - [ ] Add `backend` parameter to FeatureRegistry (in-memory or database)
  - [ ] Maintain backward compatibility with in-memory mode
  - [ ] Type hints, docstrings, structured logging
- [ ] **Create:** Migration script `scripts/migrate_feature_registry.py`
  - [ ] Export features from in-memory registry
  - [ ] Import features to database
  - [ ] Validate migration (count, checksums)
  - [ ] Rollback capability

#### 5.2.3. Feature Registry Database Tests
- [ ] **Test:** `tests/features/test_registry_database.py`
  - [ ] Database connection tests (mock PostgreSQL)
  - [ ] Feature registration to database test
  - [ ] Feature retrieval from database test
  - [ ] Lineage tracking tests (parent-child relationships)
  - [ ] Versioning tests (create version, rollback)
  - [ ] Migration script tests (export/import)
  - [ ] Backward compatibility test (in-memory mode still works)
  - [ ] Concurrent access tests (multi-user safety)
  - [ ] Query performance tests

#### 5.2.4. Feature Registry Documentation
- [ ] **Create:** `docs/FEATURE_REGISTRY_DATABASE.md`
  - [ ] Database schema documentation
  - [ ] Usage examples (register, query, version)
  - [ ] Migration guide (in-memory → database)
  - [ ] Lineage tracking examples
  - [ ] Versioning workflow
  - [ ] Rollback procedures

**✅ WHEN COMPLETE:** 
- Mark ALL items in IMPLEMENTATION_STATUS.md lines 834-842 as `[x]`
- Update line 3 to "Phase 5: 30% - Feature Registry DB Complete"
- Update Scaffolding Coverage Matrix (line 1328) to show database portion complete

---

### 5.3. Dynamic Factor Model (DFM) (Week 5, Day 5 - Week 6, Day 1)

**Goal:** Implement DFM for mixed-frequency nowcasting

**Update IMPLEMENTATION_STATUS.md:** Line 816 when complete

#### 5.3.1. DFM Core Implementation
- [ ] **Create:** `models_src/dfm/dfm_model.py`
  - [ ] State-space DFM implementation
  - [ ] EM algorithm for parameter estimation
  - [ ] Kalman filter for nowcasting
  - [ ] Support for mixed frequencies (daily, weekly, monthly)
  - [ ] Missing data handling (ragged edge)
  - [ ] Inherits from `BaseForecaster`
  - [ ] Type hints, docstrings, logging
  - [ ] Feature registry integration (track features used)
- [ ] **Test:** `tests/models/test_dfm.py`
  - [ ] Fit test with synthetic data
  - [ ] Prediction shape validation
  - [ ] Reproducibility test (same seed → same output)
  - [ ] Missing data handling test
  - [ ] Parameter convergence test
  - [ ] Feature registry tracking test

#### 5.3.2. DFM Utilities
- [ ] **Create:** `models_src/dfm/state_space.py`
  - [ ] State-space representation helpers
  - [ ] Transition matrix construction
  - [ ] Observation matrix construction
- [ ] **Test:** `tests/models/test_dfm_state_space.py`
  - [ ] Matrix dimension validation
  - [ ] State-space consistency tests

**✅ WHEN COMPLETE:** 
- Mark `- [x] Dynamic Factor Model (DFM)` in IMPLEMENTATION_STATUS.md line 816
- Update line 3 to "Phase 5: 38% - DFM Complete"

---

### 5.4. MIDAS Regression (Week 6, Days 2-3)

**Goal:** Bridge-equation model for mixed-frequency regression

**Update IMPLEMENTATION_STATUS.md:** Line 817 when complete

#### 5.4.1. MIDAS Core Implementation
- [ ] **Create:** `models_src/midas/midas_model.py`
  - [ ] MIDAS regression with Almon polynomial weights
  - [ ] High-frequency lag selection
  - [ ] NLS (Nonlinear Least Squares) estimation
  - [ ] Direct forecasting (h-step ahead)
  - [ ] Inherits from `BaseForecaster`
  - [ ] Type hints, docstrings, logging
  - [ ] Feature registry integration
- [ ] **Test:** `tests/models/test_midas.py`
  - [ ] Fit test with mixed-frequency data
  - [ ] Weight constraint validation (sum to 1)
  - [ ] Reproducibility test
  - [ ] Multi-horizon forecasting test
  - [ ] Feature registry tracking test

#### 5.4.2. MIDAS Feature Integration
- [ ] **Verify:** Integration with Phase 4 MIDAS lag constructors
- [ ] **Test:** End-to-end test (feature generation → model training → prediction)

**✅ WHEN COMPLETE:** 
- Mark `- [x] MIDAS regression` in IMPLEMENTATION_STATUS.md line 817
- Update line 3 to "Phase 5: 45% - MIDAS Complete"

---

### 5.5. GBM Quantile Models (Week 6, Days 4-5)

**Goal:** XGBoost/LightGBM for probabilistic forecasting

**Update IMPLEMENTATION_STATUS.md:** Line 818 when complete

#### 5.5.1. XGBoost Quantile Implementation
- [ ] **Create:** `models_src/gbm_quantile/xgb_quantile.py`
  - [ ] XGBoost with quantile loss
  - [ ] Multi-quantile training (5%, 10%, 25%, 50%, 75%, 90%, 95%)
  - [ ] Feature importance tracking
  - [ ] Hyperparameter tuning support (basic grid search)
  - [ ] Inherits from `BaseForecaster`
  - [ ] Type hints, docstrings, logging
  - [ ] Feature registry integration
- [ ] **Test:** `tests/models/test_xgb_quantile.py`
  - [ ] Multi-quantile output validation
  - [ ] Quantile crossing prevention test
  - [ ] Feature importance test
  - [ ] Reproducibility test (fixed seed)
  - [ ] Feature registry tracking test

#### 5.5.2. LightGBM Quantile Implementation
- [ ] **Create:** `models_src/gbm_quantile/lgb_quantile.py`
  - [ ] LightGBM with quantile loss
  - [ ] Same interface as XGBoost version
  - [ ] Type hints, docstrings, logging
  - [ ] Feature registry integration
- [ ] **Test:** `tests/models/test_lgb_quantile.py`
  - [ ] Same test suite as XGBoost
  - [ ] Cross-model consistency tests

**✅ WHEN COMPLETE:** 
- Mark `- [x] XGBoost quantile model` in IMPLEMENTATION_STATUS.md line 818
- Update line 3 to "Phase 5: 52% - GBM Models Complete"

---

### 5.6. Calibration Layer (Week 7, Days 1-2)

**Goal:** Ensure probabilistic forecasts are well-calibrated

**Update IMPLEMENTATION_STATUS.md:** Line 820 when complete

#### 5.6.1. Isotonic Regression Calibration
- [ ] **Create:** `models_src/calibration/isotonic.py`
  - [ ] Isotonic regression calibrator
  - [ ] Fit on validation set predictions
  - [ ] Transform new predictions
  - [ ] Sklearn-compatible API
- [ ] **Test:** `tests/models/test_calibration_isotonic.py`
  - [ ] Calibration improvement test (before/after ECE)
  - [ ] Reliability diagram validation
  - [ ] Edge case tests

#### 5.6.2. Conformal Prediction
- [ ] **Create:** `models_src/calibration/conformal.py`
  - [ ] Split conformal prediction intervals
  - [ ] Coverage guarantee (nominal 90% → empirical 90%)
  - [ ] Adaptive intervals
- [ ] **Test:** `tests/models/test_conformal.py`
  - [ ] Coverage validation tests (85-95% target)
  - [ ] Interval width tests
  - [ ] Adaptivity tests

#### 5.6.3. Calibration Metrics
- [ ] **Create:** `models_src/calibration/metrics.py`
  - [ ] Expected Calibration Error (ECE)
  - [ ] Reliability diagram computation
  - [ ] Sharpness metrics
  - [ ] Integration with main metrics module
- [ ] **Test:** `tests/models/test_calibration_metrics.py`
  - [ ] ECE calculation tests
  - [ ] Perfect calibration test (ECE = 0)
  - [ ] Reliability diagram validation

**✅ WHEN COMPLETE:** 
- Mark `- [x] Calibration layer` in IMPLEMENTATION_STATUS.md line 820
- Update line 3 to "Phase 5: 60% - Calibration Complete"

---

### 5.7. Revision Model (Week 7, Day 3)

**Goal:** Forecast how preliminary NFP will be revised

**Update IMPLEMENTATION_STATUS.md:** Line 819 when complete

#### 5.7.1. Revision Forecasting Implementation
- [ ] **Create:** `models_src/revision/revision_model.py`
  - [ ] Regression model for revision prediction
  - [ ] Features: preliminary value, leading indicators, historical revisions
  - [ ] Output: expected revision magnitude & direction
  - [ ] Inherits from `BaseForecaster`
  - [ ] Type hints, docstrings, logging
  - [ ] Feature registry integration
- [ ] **Test:** `tests/models/test_revision.py`
  - [ ] Revision direction accuracy test
  - [ ] Revision magnitude RMSE test
  - [ ] Reproducibility test
  - [ ] Feature registry tracking test

**✅ WHEN COMPLETE:** 
- Mark `- [x] Revision model` in IMPLEMENTATION_STATUS.md line 819
- Update line 3 to "Phase 5: 65% - Revision Model Complete"

---

### 5.8. Hierarchical Reconciliation (MinT/WLS) (Week 7, Days 4-5)

**Goal:** Ensure state forecasts sum to national total (coherence)

**Update IMPLEMENTATION_STATUS.md:** Lines 821-825 when complete

#### 5.8.1. MinT Reconciliation
- [ ] **Create:** `recon/mint/mint_reconciler.py`
  - [ ] MinT (Minimum Trace) reconciliation
  - [ ] Shrinkage covariance estimation
  - [ ] OLS, WLS, MinT(Sample), MinT(Shrink) methods
  - [ ] Summing matrix integration (from Phase 4)
  - [ ] Type hints, docstrings, logging
- [ ] **Test:** `tests/models/test_mint_reconciler.py`
  - [ ] Coherence validation test (nation = Σstates within tolerance)
  - [ ] Forecast improvement test (reconciled vs base)
  - [ ] Method comparison tests
  - [ ] Coherence error < 100 jobs test

#### 5.8.2. WLS Utilities
- [ ] **Create:** `recon/mint/wls_utils.py`
  - [ ] Weighted Least Squares helpers
  - [ ] Variance weighting computation
  - [ ] Diagonal vs full covariance
- [ ] **Test:** `tests/models/test_wls_utils.py`
  - [ ] Weight computation tests
  - [ ] Covariance matrix validation

#### 5.8.3. Coherence Testing
- [ ] **Create:** `recon/tests/test_coherence.py`
  - [ ] Validate nation == Σstates (within tolerance)
  - [ ] Validate sector sums
  - [ ] Reconciliation error bounds

**✅ WHEN COMPLETE:** 
- Mark ALL items in IMPLEMENTATION_STATUS.md lines 821-825 as `[x]`
- Update line 3 to "Phase 5: 72% - MinT/WLS Complete"

---

### 5.9. Training Pipelines (Prefect) (Week 8, Days 1-2)

**Goal:** Orchestrate model training workflows

**Update IMPLEMENTATION_STATUS.md:** Line 828 when complete

#### 5.9.1. Training Pipeline Implementation
- [ ] **Create:** `models_src/pipelines/train_pipeline.py`
  - [ ] Prefect flow for model training
  - [ ] Load features from Phase 4 (via feature registry)
  - [ ] Train/val/test split (vintage-aware)
  - [ ] Model fitting
  - [ ] Evaluation & logging
  - [ ] MLflow experiment tracking
  - [ ] Model saving to registry
  - [ ] Feature metadata linkage
- [ ] **Test:** `tests/models/test_train_pipeline.py`
  - [ ] Mock Prefect flow test
  - [ ] Data leakage prevention test (no future data)
  - [ ] Pipeline end-to-end test
  - [ ] Feature registry integration test

#### 5.9.2. Cross-Validation Pipeline
- [ ] **Create:** `models_src/pipelines/cross_validation.py`
  - [ ] Time-series cross-validation
  - [ ] Expanding window (vintage-aware)
  - [ ] Metric aggregation across folds
- [ ] **Test:** `tests/models/test_cross_validation.py`
  - [ ] Fold generation tests
  - [ ] No data leakage tests
  - [ ] Vintage-aware split validation

**✅ WHEN COMPLETE:** 
- Mark `- [x] Training pipelines (Prefect workflows)` in IMPLEMENTATION_STATUS.md line 828
- Update line 3 to "Phase 5: 78% - Training Pipelines Complete"

---

### 5.10. Model Registry Integration (Week 8, Day 3)

**Goal:** Version and track trained models

**Update IMPLEMENTATION_STATUS.md:** Lines 829-831 when complete

#### 5.10.1. Registry Operations
- [ ] **Create:** `models_src/utils/registry.py`
  - [ ] Register model to MLflow registry
  - [ ] Link model to feature registry (features used)
  - [ ] Promote to staging/production
  - [ ] Retrieve latest model by name/stage
  - [ ] Model metadata queries
  - [ ] Feature lineage queries (which features does this model use?)
- [ ] **Test:** `tests/models/test_registry.py`
  - [ ] Registration tests (mock MLflow)
  - [ ] Feature linkage tests
  - [ ] Promotion tests
  - [ ] Retrieval tests
  - [ ] Lineage query tests

#### 5.10.2. Artifact Versioning & Signing
- [ ] **Create:** `models_src/utils/signing.py`
  - [ ] SHA256 artifact signing
  - [ ] Signature verification
  - [ ] Metadata embedding (including feature checksums)
  - [ ] Zone 1 → Zone 2 artifact preparation
- [ ] **Test:** `tests/models/test_signing.py`
  - [ ] Sign/verify round-trip tests
  - [ ] Tamper detection tests
  - [ ] Feature checksum validation

**✅ WHEN COMPLETE:** 
- Mark `- [x] Model registry integration` in IMPLEMENTATION_STATUS.md line 829
- Mark `- [x] Artifact versioning and signing` in IMPLEMENTATION_STATUS.md line 831
- Update line 3 to "Phase 5: 83% - Model Registry Complete"

---

### 5.11. X-13 Quality Enhancement (Week 8, Day 4) ✨ NEW

**Goal:** Upgrade seasonal diagnostics from structure-only to full quality verification

**Update IMPLEMENTATION_STATUS.md:** Lines 845-851 when complete

**⚠️ DECISION POINT:** Implement now OR defer to Phase 6? (Document decision in IMPLEMENTATION_STATUS.md line 852)

#### 5.11.1. Real M-Statistics Computation
- [ ] **Update:** `seasonal/diagnostics/m_statistics.py`
  - [ ] Compute real M1-M11 statistics (not placeholders)
  - [ ] Quality threshold validation (M7 < 1.0, M8 < 1.0, etc.)
  - [ ] Store diagnostics in database (not just JSON)
- [ ] **Test:** `tests/seasonal/test_m_statistics_real.py`
  - [ ] Real computation tests (compare to X-13 reference)
  - [ ] Threshold enforcement tests
  - [ ] Database storage tests

#### 5.11.2. Real Q-Statistics Computation
- [ ] **Update:** `seasonal/diagnostics/q_statistics.py`
  - [ ] Compute real Ljung-Box Q-statistics
  - [ ] Quality threshold validation (p-value > 0.05)
  - [ ] Store diagnostics in database
- [ ] **Test:** `tests/seasonal/test_q_statistics_real.py`
  - [ ] Real computation tests
  - [ ] Threshold enforcement tests
  - [ ] Database storage tests

#### 5.11.3. Golden Diagnostics Integration
- [ ] **Update:** `scripts/record_golden_diagnostics.py`
  - [ ] Use real X-13 outputs (not synthetic)
  - [ ] Store in database (not just JSON file)
  - [ ] Compute quality scores
  - [ ] Flag degraded series
- [ ] **Update:** CI workflow `.github/workflows/test.yml`
  - [ ] Add X-13 quality checks to CI
  - [ ] Compare current vs golden diagnostics
  - [ ] Fail build if quality degrades beyond tolerance
- [ ] **Test:** Integration test for golden diagnostics workflow

#### 5.11.4. Quality Degradation Alerts
- [ ] **Create:** `seasonal/diagnostics/quality_monitor.py`
  - [ ] Monitor M/Q statistics over time
  - [ ] Detect degradation trends
  - [ ] Generate alerts (log warnings)
  - [ ] Integration with ops monitoring (Phase 10)
- [ ] **Test:** `tests/seasonal/test_quality_monitor.py`
  - [ ] Degradation detection tests
  - [ ] Alert generation tests

**✅ WHEN COMPLETE (If Implemented):** 
- Mark ALL items in IMPLEMENTATION_STATUS.md lines 845-851 as `[x]`
- Update line 852 note: "Implemented in Phase 5"
- Update line 3 to "Phase 5: 90% - X-13 Quality Complete"

**✅ IF DEFERRED TO PHASE 6:**
- Update line 852 note: "Deferred to Phase 6 for end-to-end validation - [Decision: YYYY-MM-DD]"
- Skip to next section
- Update line 3 to "Phase 5: 90% - X-13 Quality Deferred"

---

### 5.12. End-to-End Integration Test (Week 8, Day 5)

**Goal:** Validate full pipeline from ETL to model predictions

**Update IMPLEMENTATION_STATUS.md:** Line 864 when complete

#### 5.12.1. Integration Test Suite
- [ ] **Create:** `tests/integration/test_etl_features_models.py`
  - [ ] Load vintage data (from Phase 1-2)
  - [ ] Generate features (Phase 4)
  - [ ] Register features to database
  - [ ] Train model (Phase 5)
  - [ ] Generate predictions
  - [ ] Validate prediction format
  - [ ] Verify feature lineage tracked
  - [ ] Verify model metadata stored
- [ ] **Test:** Run with synthetic data (deterministic)
- [ ] **Test:** Verify no data leakage (vintage-aware)
- [ ] **Test:** Verify reproducibility (same seed → same results)

**✅ WHEN COMPLETE:** 
- Mark `- [x] End-to-end integration test (ETL → features → models)` in IMPLEMENTATION_STATUS.md line 864
- Update line 3 to "Phase 5: 93% - Integration Tests Complete"

---

### 5.13. Documentation (Week 8, Day 5)

**Goal:** Complete all Phase 5 documentation requirements

**Update IMPLEMENTATION_STATUS.md:** Lines 867-872 when complete

#### 5.13.1. Model Training Guide
- [ ] **Create:** `docs/MODEL_TRAINING.md`
  - [ ] Training procedure overview
  - [ ] Feature requirements (how to use feature registry)
  - [ ] Evaluation metrics definitions
  - [ ] Model selection criteria (see 5.13.2 below)
  - [ ] Cross-validation strategy
  - [ ] MLflow experiment tracking guide
  - [ ] Hyperparameter tuning workflow
  - [ ] Troubleshooting common issues

#### 5.13.2. Model Selection Decision Tree
- [ ] **Add to:** `docs/MODEL_TRAINING.md`
  - [ ] When to use DFM (mixed-frequency, nowcasting)
  - [ ] When to use MIDAS (bridge equations, high-frequency data)
  - [ ] When to use GBM (non-linear, complex interactions)
  - [ ] When to use Revision model (post-release adjustments)
  - [ ] Performance vs accuracy tradeoffs
  - [ ] Data requirements for each model

#### 5.13.3. Hyperparameter Sensitivity
- [ ] **Add to:** `docs/MODEL_TRAINING.md`
  - [ ] Key hyperparameters for each model
  - [ ] Sensitivity analysis (which params matter most)
  - [ ] Recommended tuning ranges
  - [ ] Impact on accuracy/speed

#### 5.13.4. Feature Registry Documentation
- [ ] **Verify:** `docs/FEATURE_REGISTRY_DATABASE.md` complete (created in 5.2.4)
  - [ ] Complete usage examples
  - [ ] Best practices for feature naming
  - [ ] Lineage tracking examples
  - [ ] Versioning workflows

#### 5.13.5. Forecasting Capabilities Update
- [ ] **Update:** `docs/FORECASTING_CAPABILITIES.md`
  - [ ] Add model descriptions (DFM, MIDAS, GBM, Revision)
  - [ ] Add calibration capabilities
  - [ ] Add hierarchical reconciliation
  - [ ] Add feature registry capabilities
  - [ ] Update accuracy expectations with model details

**✅ WHEN COMPLETE:** 
- Mark ALL items in IMPLEMENTATION_STATUS.md lines 867-872 as `[x]`
- Update line 3 to "Phase 5: 100% - COMPLETE"

---

## 🧪 TESTING REQUIREMENTS (Continuous)

### Test Coverage Targets
- [ ] **Unit tests:** 100% for each model class
- [ ] **Integration tests:** Model training end-to-end
- [ ] **Reproducibility tests:** Same seed → same output (all models)
- [ ] **No-leakage tests:** Validate no future data in training
- [ ] **Cross-validation tests:** Proper fold generation
- [ ] **Calibration tests:** ECE < 0.05, coverage 85-95%
- [ ] **Coherence tests:** MinT reconciliation (error < 100 jobs)
- [ ] **Performance tests:** Training time benchmarks
- [ ] **Feature registry tests:** Database operations, lineage tracking
- [ ] **X-13 quality tests:** Real M/Q statistics validation (if implemented)
- [ ] **Coverage goal:** 80%+ for all Phase 5 code

### Running Tests Throughout Phase 5

```bash
# Run all tests
pytest

# Run only model tests
pytest tests/models/

# Run with coverage
pytest --cov=models_src --cov=recon --cov=features/registry.py --cov-report=html

# Run specific test file
pytest tests/models/test_dfm.py -v

# Run integration tests only
pytest tests/integration/ -v
```

### Test Data & Fixtures
- [ ] **Create:** `tests/fixtures/model_fixtures.py`
  - [ ] Sample time series data
  - [ ] Mixed-frequency datasets
  - [ ] Mock MLflow client
  - [ ] Mock PostgreSQL connection
  - [ ] Trained model artifacts (small)
  - [ ] Feature metadata samples

---

## 🚦 GO/NO-GO GATES

### Phase 5 Completion Criteria (ALL MUST PASS)

**Before declaring Phase 5 complete, verify ALL of the following:**

#### Core Models ✅
- [ ] **All models implemented:** DFM, MIDAS, GBM (XGBoost + LightGBM), Revision, Calibration, MinT
- [ ] All models inherit from `BaseForecaster`
- [ ] All models integrate with feature registry
- [ ] All models log to MLflow

#### New Deliverables (Phase 5+ Requirements) ✅
- [ ] **Feature Registry Database:** Migrated to PostgreSQL, backward compatible
- [ ] **X-13 Quality Enhancement:** Real M/Q statistics OR documented deferral to Phase 6

#### Testing ✅
- [ ] **All tests passing:** 200+ new tests for Phase 5
- [ ] **Total test count:** ~487+ tests (287 existing + 200 new)
- [ ] **Test coverage:** 80%+ for `models_src/`, `recon/`, updated `features/registry.py`
- [ ] **No linting errors:** `make lint` passes (ruff, mypy, black)

#### Quality Validation ✅
- [ ] **Reproducibility verified:** Deterministic output with fixed seed
- [ ] **No data leakage:** All tests verify vintage-aware splits
- [ ] **MLflow integration:** All models log to MLflow
- [ ] **Calibration validated:** ECE < 0.05 on validation set
- [ ] **Coherence validated:** MinT reconciliation working (nation = Σstates, error < 100)
- [ ] **Feature registry working:** Database persistence operational
- [ ] **End-to-end test passing:** ETL → features → models pipeline

#### Accuracy Targets (Validation Set) ✅
- [ ] **sMAPE < 20%** (hard blocker)
- [ ] **90% PI coverage:** 85-95% (hard blocker)
- [ ] **Probability coherence:** Sum = 1.0 ± 0.001
- [ ] **Calibration ECE < 0.05**
- [ ] **MinT coherence error < 100 jobs**
- [ ] **Training time < 30 minutes** for full pipeline

#### Documentation ✅
- [ ] **Documentation complete:** All models, feature registry DB, model selection guide
- [ ] **API documentation:** All public functions documented
- [ ] **Usage examples:** Provided for all major components

### Final Checklist Before Moving to Phase 6

```bash
# 1. Run full test suite
pytest

# 2. Check coverage
pytest --cov=models_src --cov=recon --cov=features/registry.py --cov-report=term-missing

# 3. Run linting
make lint

# 4. Verify services
python scripts/check_infrastructure_health.py

# 5. Run integration test
pytest tests/integration/test_etl_features_models.py -v

# 6. Review IMPLEMENTATION_STATUS.md
# Ensure all Phase 5 items marked [x]
```

**✅ ALL GATES PASSED:** Update IMPLEMENTATION_STATUS.md:
- Line 3: "Last Updated: YYYY-MM-DD (Phase 5 COMPLETE - Ready for Phase 6 Backtesting)"
- Move Phase 5 from "TODO" to "COMPLETED" section

---

## 📊 PROGRESS TRACKING

### Daily Progress Updates

**At the end of each day:**
1. Update this checklist (mark completed items)
2. Update IMPLEMENTATION_STATUS.md (mark corresponding items)
3. Update phase percentage (line 3)
4. Commit changes with message: "Phase 5: [Component] - [Status]"

### Weekly Milestones

**Week 5 End (Expected):**
- [ ] Infrastructure complete (5.1)
- [ ] Feature Registry DB complete (5.2)
- [ ] DFM implementation started (5.3)
- [ ] Tests: ~60 new tests

**Week 6 End (Expected):**
- [ ] DFM complete (5.3)
- [ ] MIDAS complete (5.4)
- [ ] GBM complete (5.5)
- [ ] Tests: ~120 new tests

**Week 7 End (Expected):**
- [ ] Calibration complete (5.6)
- [ ] Revision model complete (5.7)
- [ ] MinT/WLS complete (5.8)
- [ ] Tests: ~170 new tests

**Week 8 End (Expected):**
- [ ] Training pipelines complete (5.9)
- [ ] Model registry complete (5.10)
- [ ] X-13 quality complete or deferred (5.11)
- [ ] Integration tests complete (5.12)
- [ ] Documentation complete (5.13)
- [ ] Tests: ~200+ new tests
- [ ] Phase 5 COMPLETE

### Progress Percentage Calculation

Total major components: 13 sections (5.1 - 5.13)

| Components Complete | Percentage |
|---------------------|------------|
| 0 (Pre-flight) | 5% |
| 1-2 (Infrastructure + Registry DB) | 15-30% |
| 3-5 (Core Models: DFM, MIDAS, GBM) | 38-52% |
| 6-8 (Calibration, Revision, MinT) | 60-72% |
| 9-10 (Pipelines, Registry) | 78-83% |
| 11 (X-13 Quality) | 90% |
| 12 (Integration Tests) | 93% |
| 13 (Documentation) | 100% |

---

## 🎯 SUCCESS METRICS

### Phase 5 Success Criteria

**Quantitative Metrics:**
- [ ] **sMAPE < 20%** on validation set (hard blocker)
- [ ] **90% PI coverage:** 85-95% (hard blocker)
- [ ] **Probability coherence:** Sum = 1.0 ± 0.001
- [ ] **Calibration ECE < 0.05**
- [ ] **MinT coherence error < 100 jobs** (nation vs Σstates)
- [ ] **Training time < 30 minutes** for full pipeline
- [ ] **Test coverage:** 80%+ for all Phase 5 code

**Qualitative Metrics:**
- [ ] **Feature registry:** All features tracked in database
- [ ] **All tests pass:** 100% pass rate maintained (487+ tests total)
- [ ] **X-13 quality:** Real diagnostics computed OR deferral documented
- [ ] **Code quality:** No linting errors, all docstrings complete
- [ ] **Documentation:** All guides complete and reviewed

---

## 🔄 WORKFLOW PATTERN (Repeat for Each Component)

### Standard Development Cycle

1. **Design** (15 min)
   - Review requirements
   - Sketch class structure
   - Identify dependencies

2. **Write Test First** (30 min)
   - Create test file
   - Write test cases for expected behavior
   - Run test (should fail)

3. **Implement** (2-4 hours)
   - Write production code
   - Make tests pass
   - Add type hints & docstrings

4. **Verify Quality** (15 min)
   - Check type hints complete
   - Check docstrings present
   - Add structured logging

5. **Run Tests** (5 min)
   ```bash
   pytest tests/models/test_{component}.py -v
   ```

6. **Fix Linting** (5 min)
   ```bash
   make lint
   ```

7. **Integration Check** (10 min)
   - Verify component works with existing code
   - Run related integration tests

8. **Update Documentation** (10 min)
   - Mark checklist items complete (this file)
   - Update IMPLEMENTATION_STATUS.md
   - Update progress percentage

9. **Commit** (5 min)
   ```bash
   git add .
   git commit -m "Phase 5: [Component] - [Description]"
   ```

**Total cycle time per component:** 3-5 hours

---

## 🚨 CRITICAL DECISION POINTS

### Decision 1: X-13 Quality Enhancement Timing

**When:** Week 8, Day 4 (section 5.11)

**Options:**
- **A:** Implement in Phase 5 (Week 8, Day 4) - Full quality gates before models deployed
- **B:** Defer to Phase 6 (Backtesting) - Validate quality during end-to-end backtesting

**Recommendation:** Implement basic quality checks in Phase 5 (A), enhance during Phase 6

**Rationale:** Need production-quality gates before model deployment, but comprehensive validation better suited for backtesting phase

**How to Document:**
- Update IMPLEMENTATION_STATUS.md line 852 with decision
- If deferring, add note: "Deferred to Phase 6 for end-to-end validation - [Decision: YYYY-MM-DD, Reason: {reason}]"

### Decision 2: Feature Registry Migration Strategy

**When:** Week 5, Day 3 (section 5.2)

**Options:**
- **A:** Hard cutover to database (deprecate in-memory)
- **B:** Dual mode (in-memory for dev, database for production)

**Recommendation:** Dual mode (B) with backward compatibility

**Rationale:** Maintains flexibility for local development, allows gradual rollout

**Implementation:** Add `backend` parameter to FeatureRegistry constructor

---

## 📅 ESTIMATED TIMELINE

**Total Duration:** 3.5-4.5 weeks (Week 5-8.5)

### Week-by-Week Breakdown

**Week 5 (5 days):**
- Days 1-2: Model infrastructure & utilities (5.1)
- Days 3-4: Feature Registry Database migration (5.2) ✨ NEW
- Day 5: DFM implementation start (5.3)

**Week 6 (5 days):**
- Day 1: DFM completion (5.3)
- Days 2-3: MIDAS regression (5.4)
- Days 4-5: GBM quantile models (5.5)

**Week 7 (5 days):**
- Days 1-2: Calibration layer (5.6)
- Day 3: Revision model (5.7)
- Days 4-5: Hierarchical reconciliation (5.8)

**Week 8 (5 days):**
- Days 1-2: Training pipelines (5.9)
- Day 3: Model registry integration (5.10)
- Day 4: X-13 quality enhancement (5.11) ✨ NEW (or defer decision)
- Day 5: End-to-end integration test + documentation (5.12, 5.13)

**Buffer:** +0.5 weeks for unexpected issues

---

## 🎓 LESSONS FROM PHASE 4

### Apply These Best Practices ✅

- **TDD approach worked well** - Write tests alongside code, catch errors early
- **Structured logging** - All operations logged with context, easy debugging
- **Type hints everywhere** - Caught many errors before runtime
- **Comprehensive fixtures** - Made testing efficient and maintainable
- **Determinism validation** - Same seed → same output, reproducibility guaranteed

### Watch Out For ⚠️

- **Integration complexity** - Test component interactions early, don't wait
- **Database connection overhead** - Mock PostgreSQL in tests, use fixtures
- **MLflow initialization** - Ensure service available before tests, graceful fallback
- **Feature registry coordination** - Ensure models properly link to features used

---

## 📖 QUICK REFERENCE

### Key Files to Update

| File | Purpose | Update When |
|------|---------|-------------|
| `IMPLEMENTATION_STATUS.md` | Project status | After each major section |
| `PHASE_5_IMPLEMENTATION_PLAN.md` (this file) | Detailed checklist | Daily progress updates |
| `docs/MODEL_TRAINING.md` | Model usage guide | Section 5.13 |
| `docs/FEATURE_REGISTRY_DATABASE.md` | Registry documentation | Section 5.2 |
| `docs/FORECASTING_CAPABILITIES.md` | System capabilities | Section 5.13 |

### Key Commands

```bash
# Start services
make up

# Run all tests
pytest

# Run with coverage
pytest --cov=models_src --cov=recon --cov-report=html

# Lint code
make lint

# Format code
make format

# Check infrastructure
python scripts/check_infrastructure_health.py

# Run integration tests only
pytest tests/integration/ -v
```

### Key Directories

```
models_src/           # All model implementations
├── utils/            # 5.1: Base classes, metrics, I/O, MLflow
├── dfm/              # 5.3: Dynamic Factor Model
├── midas/            # 5.4: MIDAS regression
├── gbm_quantile/     # 5.5: XGBoost & LightGBM
├── calibration/      # 5.6: Isotonic & Conformal
├── revision/         # 5.7: Revision forecasting
└── pipelines/        # 5.9: Prefect workflows

recon/                # Hierarchical reconciliation
└── mint/             # 5.8: MinT/WLS

features/
└── registry.py       # 5.2: Database migration

tests/models/         # All model tests
tests/integration/    # 5.12: End-to-end tests
```

---

## ✅ FINAL SIGN-OFF

**Before declaring Phase 5 complete:**

1. [ ] All sections 5.1-5.13 checked off
2. [ ] All Go/No-Go gates passed
3. [ ] All tests passing (487+ total)
4. [ ] Test coverage ≥ 80% for Phase 5 code
5. [ ] No linting errors
6. [ ] All accuracy targets met
7. [ ] All documentation complete
8. [ ] IMPLEMENTATION_STATUS.md fully updated
9. [ ] Integration test passing
10. [ ] Ready for Phase 6 (Backtesting)

**Sign-off:** Update IMPLEMENTATION_STATUS.md line 3:
```markdown
Last Updated: YYYY-MM-DD (Phase 5 COMPLETE - Ready for Phase 6 Backtesting)
```

---

**Document Version:** 1.0  
**Created:** 2025-11-19  
**Status:** Ready for Phase 5 Implementation  
**Next Phase:** Phase 6 (Backtesting)


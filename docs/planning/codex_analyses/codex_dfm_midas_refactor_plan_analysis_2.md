# DFM + MIDAS Refactor Plan Analysis (docs/planning/DFM_MIDAS_REFACTOR_PLAN.md)

## Fit Against Capability/Accuracy Docs
- `docs/FORECASTING_CAPABILITIES.md` and `docs/ACCURACY_DESCRIPTION.md` promise daily/weekly nowcasts, mixed-frequency fusion, calibrated probability vectors, revision modeling, and state/sector reconciliation; the plan tackles only the mixed-frequency gap (MIDAS bridge + stable DFM) and explicitly leaves calibration, revision, and reconciliation untouched, so it cannot by itself deliver the probability/coverage targets in `docs/ACCURACY_MAP.md` (e.g., 74–86% interval coverage, low-noise vectors) or the state/sector stability promises.  
- `docs/ACCURACY_MAP.md` Section 8 calls out intra-month nowcasts (T-48h→T-2h) powered by high-frequency data; the plan builds the bridge needed to ingest that data, but no orchestration/tests are listed to exercise intra-month updates or interval calibration, so the top-tier accuracy ranges remain dependent on existing pipelines rather than this refactor.  
- Net: the refactor is necessary for mixed-frequency capability alignment but insufficient to close probabilistic/coverage/reconciliation expectations articulated in the accuracy docs.

## Current Implementation Reality (forecast-labor)
- DFM is still the custom EM/Kalman implementation in `models_src/dfm/dfm_model.py` with supporting utilities/tests in `models_src/dfm/state_space.py` and `tests/models/test_dfm_state_space.py`; no statsmodels usage exists despite `requirements.txt` listing `statsmodels==0.14.0`.  
- Backtests and integration paths (`tests/backtests/test_dfm_validation.py`, `tests/integration/test_complete_workflow.py`, `tests/integration/test_etl_features_models.py`) consume pre-built monthly CES features only; they never ingest raw daily/weekly data or exercise ragged-edge handling.  
- MIDAS feature engineering is offline and artifact-driven: `features/midas/lag_constructor.py` builds lags, and `scripts/build_features.py` materializes monthly MIDAS lag parquet (`treasury_midas_lags`, `claims_midas_lags`). The runtime model `models_src/midas/midas_model.py` expects those pre-aggregated matrices, not raw sources.  
- Ensemble/pipeline code (`models_src/pipelines/ensemble_pipeline.py`) still assumes `BaseForecaster.fit(X, y, vintage_date)` with matrix inputs; there is no `MIDASBridge`, no `MIDASBridgedRegression`, and no mixed-frequency pipeline runner.  
- Existing serialization and registry flows (e.g., `DynamicFactorModel.save/load` in `models_src/dfm/dfm_model.py`, feature registration inside `scripts/build_features.py`) are tightly coupled to numpy/pandas artifacts and would not accept statsmodels result objects or bridge-produced metadata without adapters.

## Plan Blind Spots / Risks
- Interface shift: the plan’s `MIDASBridge`/`MIDASBridgedRegression` raw-data signatures conflict with current pipelines/tests built around matrix inputs; no migration path is defined for the integration/backtest tests that hard-code `fit(X, y, vintage_date)`.  
- State-space and EM-specific tests/utilities (`tests/models/test_dfm_state_space.py`, `models_src/dfm/state_space.py`) will be orphaned if DFM is swapped for statsmodels without a compatibility shim.  
- Feature/version drift: the plan proposes on-demand bridge features while `scripts/build_features.py` already persists MIDAS lags; without registry/version rules, stored artifacts and runtime bridge outputs can diverge, invalidating trained models and hashes referenced in `docs/planning/IMPLEMENTATION_STATUS.md` and existing pipelines.  
- Backtest expectations: `tests/backtests/test_dfm_validation.py` targets monthly CES-only features and current DFM attributes; swapping implementations without revising test fixtures/thresholds will fail validation before stability gains can be measured.  
- Calibration and coverage gaps stay unaddressed; accuracy docs expect calibrated bins/intervals, but the plan adds no conformal/isotonic steps or evaluation hooks to ensure the new mixed-frequency flow meets the 74–86% coverage and low-noise vector requirements.

## Potential Breaking Changes
- Replacing `models_src/dfm/dfm_model.py` with statsmodels will break save/load consumers that expect numpy-friendly artifacts and may invalidate `DynamicFactorModel` attributes referenced across integration tests and pipelines.  
- Introducing bridge-driven feature names (`{source}_bridge_lag_*`) without synchronizing `scripts/build_features.py` outputs and registry metadata will break downstream training and ensemble assembly that rely on existing names (`treasury_midas_lags`, `claims_midas_lags`).  
- Base class contract risk: `BaseForecaster` consumers in pipelines and tests assume deterministic numpy arrays; statsmodels results objects and raw-source ingestion need deterministic seeding and adapter layers to avoid reproducibility regressions highlighted in `docs/planning/IMPLEMENTATION_STATUS.md`.

## Readiness Verdict
- The plan directly targets the mixed-frequency and DFM stability gaps blocking Phase 6.3.1 re-validation, but because current code/tests are tightly coupled to pre-aggregated monthly matrices and custom DFM internals, the refactor will require substantial compatibility work before any accuracy gains can be measured.  
- Alignment confidence that the plan alone brings the codebase to the accuracy/coverage expectations of `docs/ACCURACY_MAP.md` and the high-frequency promises in `docs/FORECASTING_CAPABILITIES.md` is **~55/100**; success depends on adding compatibility shims, feature versioning, and calibration hooks not currently scoped.

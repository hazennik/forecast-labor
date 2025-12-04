# DFM + MIDAS Refactor Plan Analysis

## Fit Against Capabilities & Accuracy Docs
- The plan targets the biggest gaps vs `docs/FORECASTING_CAPABILITIES.md` (mixed-frequency nowcasts, ragged-edge handling) and `docs/ACCURACY_MAP.md` (stability needed for elite-tier sMAPE/coverage), but it only touches the DFM/MIDAS slice; it does not materially advance probability vectors, revision modeling, or state/sector reconciliation that those docs also classify as core capabilities.  
- `ACCURACY_DESCRIPTION.md` stresses elite-turning-point and calibration strengths; the plan adds no calibration/probabilistic work, so those strengths remain dependent on existing pipelines rather than this refactor.  
- Conclusion: the refactor is necessary for mixed-frequency alignment and stability, but it is insufficient by itself to “align the entire project’s models” with the full capability/accuracy expectations.

## Current Code Reality vs Plan
- DFM is still a custom EM/Kalman implementation (`models_src/dfm/dfm_model.py`) with no statsmodels dependency in the model code, and tests/backtests consume monthly CES-only features (`tests/backtests/test_dfm_validation.py`), so mixed-frequency is not actually exercised.  
- MIDAS lagging exists as a standalone constructor (`features/midas/lag_constructor.py`) and the regression model (`models_src/midas/midas_model.py`) consumes pre-built monthly lags; there is no bridge class or raw high-frequency ingestion.  
- Feature generation already builds monthly MIDAS lags from daily/weekly data (`scripts/build_features.py`), but output is pre-aggregated artifacts—there is no runtime bridge to models or the ensemble.  
- Ensemble/pipeline code (`models_src/pipelines/ensemble_pipeline.py`) assumes models accept pre-built feature matrices; nothing in the runtime supports raw D/W ingestion or bridge-driven pipelines described in the plan.

## Bottlenecks / Unaccounted Risks
- Interface mismatch: proposed `MIDASBridge`/`MIDASBridgedRegression` signatures (raw_sources, vintage_date) conflict with `BaseForecaster.fit(X, y, vintage_date)` and all existing pipelines/tests built around matrix inputs; large refactors to base classes/tests are required but not budgeted.  
- State-space utilities/tests (`models_src/dfm/state_space.py`, `tests/models/test_dfm_state_space.py`) assume the custom EM DFM; replacing with statsmodels will orphan or force heavy rewrites of these modules.  
- Serialization/logging: existing save/load paths and registry integration expect numpy arrays and simple dicts; statsmodels results objects are heavier and will break `DynamicFactorModel.save/load` consumers unless adapters are added (not specified in the plan).  
- Feature duplication: `scripts/build_features.py` already emits monthly MIDAS lags; introducing a bridge that recomputes lags at prediction time risks divergence between stored feature artifacts and model-time features unless registry/versioning rules are clarified.  
- Test blast radius: plan adds ~700–1,200 new tests but also forces rewrites of all DFM/MIDAS integration tests; runtime cost and CI timeouts are likely bottlenecks not addressed.  
- Real-data dependency: Phase R7 assumes stable vintage availability and statsmodels performance on BLS CES vintages; prior failures (0% stability noted in plan) suggest more data cleaning/normalization may be needed but is not scoped.

## Potential Breaking Changes Not Accounted For
- Backward compatibility with `DynamicFactorModel` API used in existing integration tests (`tests/integration/test_complete_workflow.py`, `tests/integration/test_etl_features_models.py`) is unspecified; replacing the class will break these unless shims are provided.  
- Any change to feature naming/ordering from the bridge will invalidate trained artifacts and feature-registry hashes referenced in Phase 5 documentation and pipelines.  
- Introducing a mixed-frequency pipeline will require updates to CLI/scripts (e.g., `scripts/build_features.py`, Prefect/ensemble pipelines) beyond what is listed, otherwise automation paths will fail.  
- Base class expectations (numpy arrays, deterministic seeding) must be enforced in statsmodels wrappers; otherwise reproducibility requirements cited in `IMPLEMENTATION_STATUS.md` regress.

## Alignment Verdict
- The plan directly addresses the core misalignment for mixed-frequency capability (true D/W→M bridging and stable DFM), which is necessary to meet the “Short-Term Nowcasts” and “Mixed-frequency fusion” promises in `FORECASTING_CAPABILITIES.md`.  
- However, because it omits calibration/probability updates, revision modeling, and state/sector reconciliation touchpoints, it only partially realigns the project to `ACCURACY_MAP.md` and `ACCURACY_DESCRIPTION.md`. These documents expect end-to-end probabilistic, calibrated, and reconciled outputs; the plan fixes stability but not the full stack.

## Phase 6.3 Backtesting Readiness Estimate
- Given the interface churn, serialization risk, and dependency on unproven statsmodels integration, likelihood that this refactor alone places the codebase in a ready state to resume Phase 6.3 backtesting without redoing earlier Phase 5 pieces is **~58/100**.  
- It is likely that portions of Phase 5 (DFM tests, state_space utilities, feature registry entries tied to DFM) will need rework to accommodate the new architecture, but a full reimplementation of Phases 1–5 is not indicated.  
- Risk reduction actions before backtesting: design compatibility layer for `BaseForecaster`/pipelines, define feature naming/versioning rules for bridge outputs, and prototype statsmodels serialization plus ragged-edge handling on a small vintage subset.

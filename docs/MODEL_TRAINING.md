# Model Training Guide

This guide covers the Phase 5 model stack: training workflow, model selection,
hyperparameter tuning, calibration, reconciliation, artifact handling, and the
current production-readiness decision.

## Current Production Decision

The production ensemble candidates are MIDAS, XGBoost, and LightGBM. DFM is
implemented and numerically stable, but it remains a research and diagnostic
component until true pre-release public signals pass vintage-honest accuracy
gates.

Current DFM validation status:

- Real CES vintage stability: 17/17 stable.
- Corrected pre-release CES-only DFM sMAPE: 103.61%.
- DFM is excluded from production ensemble composition until Phase 6 validation
  adds true pre-release signals such as claims, Treasury withholdings, business
  formations, strikes/weather controls, and prior CES releases.

Do not use same-release CES sector components to forecast same-month NFP before
the NFP release. Feature timing is a data-leakage boundary, not a tuning detail.

## Post-Phase 6 Training Baseline

This section records the Phase 6 validation evidence that should guide training
runs after the infrastructure, reporting, scenario, lineage, and quality-gate
phases were completed.

Current production training scope:

- Train and evaluate MIDAS, XGBoost, and LightGBM as the production candidate
  ensemble.
- Include the revision model for first-to-final revision workflows after the
  first BLS print is available.
- Keep DFM in diagnostic and research runs only. It is stable on real CES
  vintages, but the corrected pre-release CES-only sMAPE remains far outside the
  production accuracy gate.
- Treat MinT reconciliation as a post-model coherence step for state, sector, or
  other hierarchical outputs. Reconciliation must not materially degrade base
  forecast accuracy.

Validated Phase 6 runtime baselines from `tests/fixtures/performance_baselines.json`:

- DFM: training 0.156561 seconds, prediction 0.002809 seconds, memory 11.664 MB,
  production inclusion `false`.
- MIDAS: training 0.120821 seconds, prediction 0.000244 seconds, memory 0.125 MB.
- XGBoost: training 0.234230 seconds, prediction 0.011881 seconds, memory 6.965 MB.
- LightGBM: training 0.203134 seconds, prediction 0.016490 seconds, memory 8.910 MB.
- Revision: training 0.007708 seconds, prediction 0.001038 seconds, memory 0.001 MB.
- Full production candidate pipeline: training 0.565893 seconds, prediction
  0.029653 seconds, memory 16.001 MB.

These baselines are regression-detection targets for deterministic real model
classes, not a substitute for vintage-honest accuracy evaluation. A production
promotion still requires the accuracy, calibration, coherence, revision, and
stability gates listed below.

Before promoting a trained bundle, run the Phase 6 validation tools with the
candidate payloads produced by the training job:

```bash
docker compose exec etl python scripts/validate_accuracy_gates.py --input-file <candidate_scores.json>
docker compose exec etl python scripts/validate_performance_baselines.py --baseline tests/fixtures/performance_baselines.json
docker compose exec etl python scripts/validate_feature_lineage.py --input-file <model_lineage.json>
docker compose exec etl python scripts/run_scenario_tests.py --input-file <scenario_payload.json>
```

The guide intentionally separates two decisions:

- Runtime readiness: the Phase 6 performance baseline shows the current model
  stack is well inside local SLA limits.
- Forecast readiness: production selection still depends on vintage-honest
  accuracy gates and calibrated probability output for the specific release
  window.

## Training Workflow

1. Generate or load a vintage-honest feature set.
   - Use immutable vintage inputs from `data/vintages/`.
   - Register generated feature metadata in `features.registry`.
   - Use `FEATURE_REGISTRY_BACKEND=database` when PostgreSQL lineage is needed.

2. Create chronological splits.
   - Use `TrainingConfig` and `create_time_series_splits()` from
     `models_src/pipelines/train_pipeline.py`.
   - Train, validation, and test windows must be strictly ordered.
   - Set `vintage_date` so rows after that date are excluded.

3. Train candidate models.
   - MIDAS for bridge equations and mixed-frequency lag structures.
   - XGBoost and LightGBM quantile models for nonlinear point and interval
     forecasts.
   - DFM only for diagnostics or research runs until pre-release accuracy gates
     pass.

4. Validate probabilistic outputs.
   - Use quantile model intervals, conformal intervals, and calibration metrics.
   - Required gates before production deployment include 90% PI coverage in the
     85-95% range and ECE below the configured threshold.

5. Reconcile hierarchy outputs when state or sector forecasts are present.
   - Use `MinTReconciler(method="mint_shrink")` as the default.
   - Validate coherence after reconciliation.

6. Save artifacts with metadata.
   - Use `save_model_with_metadata()` from `models_src/utils/io.py`.
   - Include feature names, vintage date, training window, hyperparameters, and
     registry references.
   - Sign artifacts before crossing the Zone 1 to Zone 2 boundary.

7. Track experiments.
   - Use `MLflowLogger` for hyperparameters, metrics, artifacts, and feature
     metadata.
   - Log the exact split windows and vintage date for reproducibility.

## Model Selection Decision Tree

Use this decision tree before training or selecting a model for a forecast path.

**Need a production NFP candidate today?**
Use MIDAS plus XGBoost and/or LightGBM. Calibrate intervals and evaluate with
expanding-window validation.

**Need mixed-frequency daily or weekly signals?**
Use `MIDASBridge` to align raw sources to monthly targets. Then train
`MIDASBridgedRegression` or the `MixedFrequencyPipeline`.

**Need smooth bridge equations with interpretable lag decay?**
Use `MIDASRegression` or `MIDASBridgedRegression`. Prefer this when signal timing
and lag weights matter more than nonlinear interactions.

**Need nonlinear interactions or quantile intervals?**
Use `XGBoostQuantile` or `LightGBMQuantile`. These are the strongest Phase 5
production candidates for flexible public-signal nowcasting and probability
interval construction.

**Need latent factor diagnostics?**
Use `DynamicFactorModel` only as a diagnostic or research model until Phase 6
pre-release validation passes. The class is stable, but current CES-only
pre-release accuracy is below the production gate.

**Need revision forecasts?**
Use `RevisionForecaster` after the first BLS print is available. Revision targets
are `final_value - preliminary_value`; positive predictions indicate expected
upward revisions.

**Need state-to-national or sector-to-total coherence?**
Use `MinTReconciler`. Default to `mint_shrink` for noisy forecast-error
covariances, and verify coherence error remains below the gate.

## Cross-Validation Strategy

Use expanding-window validation from `models_src/pipelines/cross_validation.py`.
This reflects production forecasting because the training set grows as time
passes while the test window moves forward.

Recommended defaults for Phase 6 backtesting:

- `n_folds`: 5 or more when data permits.
- `initial_train_size`: enough months for each model to estimate stable
  parameters.
- `forecast_horizon`: 1 for monthly NFP nowcasts unless explicitly testing
  multi-step forecasts.
- `gap_size`: use when feature publication timing requires a release lag.
- `max_time_per_fold_seconds`: set for expensive DFM or GBM tuning runs.
- `total_max_time_seconds`: set in CI or long backtest jobs to prevent hangs.

Never use shuffled k-fold validation for production forecast selection.

## Hyperparameter Sensitivity

### MIDAS

Key parameters:

- `n_lags`: High impact. Too few lags miss delayed high-frequency effects; too
  many lags increase noise and optimization difficulty.
- `almon_degree`: Medium impact. Degree 2 is the default starting point; higher
  degrees add flexibility but can overfit small samples.
- `horizon`: High impact. Use horizon 1 for nowcasting unless the target is
  explicitly multi-step.
- `optimization_method`: Medium impact. `L-BFGS-B` is preferred for bridged
  models when constraints and convergence are important.

Recommended ranges:

- `n_lags`: 4-12 for weekly inputs, 20-65 for daily inputs depending on the
  source window.
- `almon_degree`: 1-3.
- `optimization_method`: `L-BFGS-B`, then `BFGS` or `Powell` if convergence
  fails.

Watch for optimization failures and unstable lag weights.

### XGBoost and LightGBM Quantile Models

Key parameters:

- `n_estimators`: High impact on fit and runtime. More trees can improve accuracy
  until validation error plateaus.
- `max_depth`: High impact. Deeper trees capture interactions but overfit short
  macro samples.
- `learning_rate`: High impact. Lower rates need more trees and usually improve
  stability.
- `subsample` and `colsample_bytree`: Medium impact. Values below 1.0 reduce
  variance.
- `num_leaves`: High impact for LightGBM. Keep it consistent with sample size and
  max depth.
- `quantiles`: High impact for interval quality. Include at least lower, median,
  and upper quantiles needed by downstream calibration.
- `prevent_crossing`: Keep enabled unless debugging raw quantile behavior.

Recommended ranges:

- `n_estimators`: 50-500.
- `max_depth`: 2-6 for macro samples.
- `learning_rate`: 0.01-0.10.
- `subsample`: 0.6-1.0.
- `colsample_bytree`: 0.6-1.0.
- `num_leaves`: 7-63 for LightGBM.

Tune against sMAPE/RMSE and interval coverage together. A model with slightly
worse point accuracy but materially better calibrated intervals may be superior
for subnet scoring.

### Dynamic Factor Model

Key parameters:

- `n_factors`: High impact. Too few factors underfit broad conditions; too many
  factors destabilize short samples.
- `ridge_alphas`: High impact for the supervised nowcast head.
- `include_direct_features`: High impact. Including direct bridge features can
  improve point forecasts but must respect release timing.
- `max_iter` and `tol`: Medium impact on convergence and runtime.

Recommended ranges:

- `n_factors`: 1-3 until Phase 6 proves larger factor structures are useful.
- `ridge_alphas`: `(0.1, 1.0, 10.0, 100.0)` as a conservative default.
- `max_iter`: 50-200.
- `tol`: `1e-3` to `1e-5`.

Use DFM validation results as diagnostics until the pre-release accuracy gate is
met.

### Calibration

Key parameters:

- `confidence_levels`: High impact. Match downstream scoring needs: 80%, 90%,
  and 95% intervals are standard.
- `adaptive`: Medium impact. Adaptive conformal intervals can help when residual
  size varies with forecast magnitude.
- `adaptive_gamma`: Medium impact. Higher values make intervals more adaptive but
  can become noisy.
- `out_of_bounds`: Use `clip` for isotonic calibration in production.

Recommended ranges:

- `confidence_levels`: `[0.8, 0.9, 0.95]`.
- `adaptive_gamma`: 0.05-0.25 when adaptive intervals are enabled.

Gate on empirical interval coverage, not only average interval width.

### Revision Forecaster

Key parameters:

- `alpha`: High impact. Higher values smooth noisy revision patterns.
- `fit_intercept`: Keep enabled unless there is strong evidence of zero-mean
  revision residuals after feature construction.

Recommended ranges:

- `alpha`: 0.1-100.0 on a log grid.

Evaluate revision MAE and direction accuracy separately.

### MinT Reconciliation

Key parameters:

- `method`: High impact. `mint_shrink` is the default for noisy covariance
  estimates; `ols` is a simple baseline.
- `forecast_errors`: High impact. Use real historical forecast errors whenever
  available.

Recommended method order:

1. `mint_shrink` for production candidates.
2. `wls` when only variance estimates are reliable.
3. `ols` as a coherence baseline.
4. `mint_sample` only when enough error history exists for a stable covariance
   estimate.

Reject reconciliation settings that improve coherence but materially degrade
forecast accuracy.

## Metrics And Gates

Track at least:

- RMSE for absolute forecast error.
- sMAPE for scale-normalized accuracy.
- CRPS when full distributions are available.
- Prediction interval coverage for 80%, 90%, and 95% intervals.
- ECE for probabilistic calibration.
- Turning point accuracy for cycle transitions.
- Coherence error after reconciliation.

Hard Phase 6 deployment blockers include:

- NFP sMAPE below 20% for at least one production candidate.
- 90% prediction interval coverage between 85% and 95%.
- No forecasts with absolute magnitude above 2 million jobs.
- MinT reconciliation improves or maintains base forecast accuracy.
- Mathematical property tests continue to pass after tuning.

## Troubleshooting

**DFM is stable but inaccurate.**
Check feature timing before tuning. Same-release CES components are not valid
pre-release NFP signals.

**MIDAS optimization fails.**
Reduce lag count, lower Almon degree, try `L-BFGS-B`, and check feature scaling.

**Quantile intervals cross.**
Keep `prevent_crossing=True` and verify quantile outputs before calibration.

**Intervals are too wide.**
Check conformal calibration residuals, GBM quantile spread, and whether the
validation set is too small or distributionally different.

**Feature registry metadata is missing from artifacts.**
Set `include_feature_info=True`, verify `FEATURE_REGISTRY_BACKEND`, and ensure
features were registered before saving model artifacts.

**Backtest accuracy is unexpectedly good.**
Audit release timing and vintage constraints first. Leakage is more likely than
a sudden model breakthrough.

## Required Tests

Before declaring a model or ensemble production-ready, run the relevant tests in
Docker:

```bash
docker compose exec etl pytest tests/models/ -v --tb=short
docker compose exec etl pytest tests/features/ -v --tb=short
docker compose exec etl pytest tests/integration/ -v --tb=short
docker compose exec etl pytest tests/backtests/ -v --tb=short
docker compose exec etl pytest -q
```

For code changes under model modules, also run targeted lint/type gates:

```bash
docker compose exec etl ruff check models_src/ features/midas/ recon/
docker compose exec etl mypy models_src/ features/midas/ --ignore-missing-imports
```

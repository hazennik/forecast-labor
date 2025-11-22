# Forecast-Labor Review (Phases 1–5.8.3) — Codex Analysis 18

Purpose: Re-evaluate Phases 1–5.8.3 using the current codebase and planning docs, leveraging prior findings from Codex Analysis 17 to spot remaining risks and dependencies on future phases.

## Inputs Reviewed
- Current planning artifacts: `docs/planning/IMPLEMENTATION_STATUS.md` (Phase 5+, quality gates at lines 1014-1022; live-data automation at lines 199-240) and `docs/planning/PHASE_5_IMPLEMENTATION_PLAN.md` (Phase 5.8 scope at lines 486-559).
- Phase completion notes: `docs/planning/PHASE_5_7_1_REVISION_MODEL_COMPLETE.md`, `docs/planning/PHASE_5_8_2_WLS_UTILITIES_COMPLETE.md`, `docs/planning/PHASE_5_8_3_COHERENCE_TESTING_COMPLETE.md`.
- Source/tests across ETL, seasonal, features, reconcilers, and models (`scripts/*`, `seasonal/*`, `features/*`, `recon/*`, `models_src/*`, `tests/*`).
- CI configuration: `.github/workflows/test.yml` (Postgres service, synthetic data seeding).

## Phase Snapshot (1–5.8.3)
- **Phases 1–4 (ETL, seasonal scaffolding, validators, features):** Deterministic synthetic vintages and provenance guards remain; seasonal diagnostics gate is unchanged (structure-only). CI still seeds synthetic vintages/diagnostics (`scripts/setup_test_data.py:1-72`).
- **Phase 5.1–5.6 (model infra, registry, DFM/MIDAS/GBM, calibration):** Registry DB path now validated in CI with a Postgres service (`.github/workflows/test.yml:35-134`), addressing the Codex 17 Finding 3 gap documented in `docs/planning/CODEX_ANALYSIS_17_FINDING_3_RESOLUTION.md`.
- **Phase 5.7 (Revision model):** Ridge-based revision forecaster and comprehensive tests are present (`models_src/revision/revision_model.py`, `tests/models/test_revision.py`), matching the completion memo.
- **Phase 5.8 (MinT/WLS/Coherence):** WLS utilities and coherence tests exist (`recon/mint/wls_utils.py`, `recon/tests/test_coherence.py`). The `MinTReconciler` enforces coherence but does not implement the documented MinT formula (see Findings).

## Findings (ordered by impact)
1) **Seasonal diagnostics gate remains structure-only; X-13 quality verification still deferred.** The `--verify` path explicitly logs that it does not run X-13 or compare M/Q stats (`scripts/record_golden_diagnostics.py:400-417`), and the bundled baseline is flagged as placeholder test data (`tests/fixtures/golden_baselines/golden_seasonal_diagnostics.json:1-18`). IMPLEMENTATION_STATUS keeps real diagnostics under the “Quality Gates Enhancement” backlog (`docs/planning/IMPLEMENTATION_STATUS.md:1014-1022`). Impact: seasonal quality regressions will pass CI; production deployments still require manual X-13 runs and baseline recording until the Phase 5+/6 quality-gate work lands.

2) **CI and determinism checks are still tied to synthetic data; live ETL remains unvalidated.** CI seeds only synthetic vintages/diagnostics via `scripts/setup_test_data.py` (`scripts/setup_test_data.py:1-72`, `.github/workflows/test.yml:65-135`). No pipeline exercises real API pulls or real seasonal diagnostics in automation. IMPLEMENTATION_STATUS defers automated live-data validation to Phase 10 (`docs/planning/IMPLEMENTATION_STATUS.md:199-240`). Impact: schema/API drift or real-data quality issues won’t be caught by CI; production runs must still execute `make seed` and regenerate real diagnostics out-of-band.

3) **MinT reconciliation implementation diverges from the planned MinT/WLS specification.** The reconciler computes weight matrices for OLS/WLS/MinT but then applies a proportional adjustment to the bottom series, ignoring the stated `S (S' W^-1 S)^-1 S' W^-1 y` formulation (`recon/mint/mint_reconciler.py:200-338`). When `forecast_errors` are absent it also derives weights from forecast levels instead of error covariance. PHASE_5_IMPLEMENTATION_PLAN describes a full MinT reconciliation with covariance-based weights and summing-matrix application (`docs/planning/PHASE_5_IMPLEMENTATION_PLAN.md:486-559`). Impact: all methods reduce to a simple coherence fix rather than minimum-trace or variance-aware reconciliation; WLS/MinT options are mislabeled and may underperform on real hierarchies. No follow-on phase is planned to correct this, so the gap needs remediation within Phase 5.8 scope.

## Verdict
- **Phase coverage:** Artifacts for Phases 1–5.8.3 exist with passing tests, and the registry Postgres path now runs in CI. 
- **Readiness:** Blocked for production-quality seasonal validation and live-data assurance (Findings 1–2). Additionally, the MinT reconciler does not meet its own Phase 5.8 design intent (Finding 3), leaving hierarchical reconciliation mathematically incomplete. Address these before treating Phase 5.8 as production-ready.

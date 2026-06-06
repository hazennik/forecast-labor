# Forecast-Labor Deployment Gates

Last updated: 2026-06-06

This document defines the hard blockers that must pass before a signed model bundle is promoted
from Zone 1 into the Zone 2 forecast-serving API.

## Gate Summary

Deployment is blocked unless all three gate groups pass:

1. Model quality gates pass in Zone 1.
2. Signed artifact and isolation gates pass at the Zone 1 to Zone 2 boundary.
3. Phase 6A API operational gates pass in Zone 2.

Do not bypass these gates for a subnet submission window. If a gate fails, keep the previous signed
bundle active and investigate in Zone 1.

## Model Quality Gates

The promoted production candidate must satisfy these current hard blockers:

- `GATE_SMAPE_MAX`: NFP sMAPE must be below the configured threshold.
- `GATE_COVERAGE_MIN` and `GATE_COVERAGE_MAX`: interval coverage must remain inside the configured
  bounds for the target interval.
- `GATE_COHERENCE_ERROR_MAX`: reconciled probability and hierarchy outputs must remain coherent.
- Calibration ECE must remain below `0.05`.
- Revision error must remain below `30K` jobs for revision-aware artifacts.

The current production candidate set remains MIDAS, XGBoost, and LightGBM. DFM is diagnostic-only
until true pre-release signals pass vintage-honest gates.

## Artifact Boundary Gates

The bundle crossing into Zone 2 must be signed and verified with the existing signing utilities.
Zone 2 must receive only the signed artifact bundle and verification material.

Required checks:

```bash
docker compose exec etl pytest tests/test_phase_6a_api.py -q
docker compose exec etl pytest tests/test_phase_6a_deployment.py -q
```

Promotion is blocked if:

- No verified signed model artifact is active.
- `ACTIVE_MODEL_BUNDLE` points to an unsigned or missing bundle.
- `ZONE2_ARTIFACT_DIR`, `ZONE2_EXTRACT_DIR`, or `ACTIVE_MODEL_BUNDLE` points inside `data`, `zone1`,
  `etl`, `features`, `models_src`, `backtests`, or `scripts`.
- Protected artifact endpoints are reachable without `ZONE2_API_KEY`.

## API Operational Gates

Before opening a deployment to subnet-facing traffic, validate the API profile and smoke checks:

```bash
docker compose --profile api config
docker compose --profile api up -d api
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
curl -fsS http://localhost:8000/status
curl -fsS http://localhost:8000/metrics
```

Required API behavior:

- `/health` returns liveness without requiring an active artifact.
- `/ready` reports `ready=true` only when a verified signed artifact is active and Zone 2 isolation
  checks pass.
- `/forecast` fails closed with `503` when no verified artifact is active.
- `/forecast` fails closed with `429` and `Retry-After` when rate limits are exceeded.
- `/metrics` exposes request counts, status counts, and latency aggregates.
- Every response includes `X-Request-ID`, preserving caller-provided IDs.

## Full Validation Gate

Run the full Docker suite before promotion:

```bash
docker compose exec etl pytest -q
```

The run must complete without failures. Skips and warnings are acceptable only when they match the
current recorded baseline in `docs/planning/IMPLEMENTATION_STATUS.md`.

## Rollback Gate

If any gate fails after promotion, roll back to the previous signed bundle:

```bash
ACTIVE_MODEL_BUNDLE=zone2/runner/artifacts/previous_bundle.zip docker compose --profile api up -d --force-recreate api
curl -fsS http://localhost:8000/ready
```

Never copy raw data or Zone 1 training materials into Zone 2 to debug a deployment failure.

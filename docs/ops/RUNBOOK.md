# Forecast-Labor Operations Runbook

Last updated: 2026-06-06

This runbook covers the Phase 6A Zone 2 forecast-serving API. It assumes model training,
artifact signing, and accuracy-gate promotion happen in Zone 1 before any bundle is copied into
Zone 2.

## Scope

Zone 2 must serve forecasts from signed artifacts only. It must not mount raw data, Zone 1
training artifacts, ETL code, feature code, model-source training code, backtests, or operational
scripts into the API container.

## Preflight

Before starting the API profile, verify the static deployment contract:

```bash
docker compose --profile api config
docker compose exec etl pytest tests/test_phase_6a_deployment.py -q
docker compose exec etl pytest tests/test_phase_6a_api.py -q
```

Required runtime settings:

- `ZONE2_ARTIFACT_DIR`: directory containing signed model bundles.
- `ZONE2_EXTRACT_DIR`: directory for extracted verified bundles.
- `ACTIVE_MODEL_BUNDLE`: optional explicit signed bundle path.
- `ZONE2_API_KEY`: required before using protected artifact endpoints.
- `API_RATE_LIMIT_ENABLED`: keep enabled unless a stricter gateway limit is enforced.
- `API_RATE_LIMIT_REQUESTS_PER_MINUTE`: per-client forecast request limit.

## Start Zone 2 API

Start only the API profile for local Zone 2 serving checks:

```bash
docker compose --profile api up -d api
docker compose ps api
```

Do not use the full training stack as a substitute for a Zone 2 runtime check. The API profile is
expected to mount only `zone2/runner/artifacts` and `zone2/runner/extracted`.

## Smoke Checks

Run these checks after startup and after every artifact promotion:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
curl -fsS http://localhost:8000/status
curl -fsS http://localhost:8000/metrics
```

For protected artifact endpoints, include the configured API key:

```bash
curl -fsS -H "X-API-Key: ${ZONE2_API_KEY}" http://localhost:8000/artifacts/active
curl -fsS -H "X-API-Key: ${ZONE2_API_KEY}" http://localhost:8000/artifacts/active/export --output active_bundle.zip
```

Every response should include `X-Request-ID`. Pass a caller-supplied request ID when tracing an
incident:

```bash
curl -fsS -H "X-Request-ID: deploy-smoke-$(date +%s)" http://localhost:8000/health
```

## Expected Failure Modes

`/ready` returns `ready=false` when no verified signed model bundle is active. This is a deployment
blocker, not a liveness failure.

`/forecast` returns `503` when no verified signed model bundle is active or when Zone 2 paths point
inside forbidden project roots such as `data`, `zone1`, `etl`, `features`, `models_src`,
`backtests`, or `scripts`.

`/forecast` returns `429` with `Retry-After` when the in-process forecast request limit is exceeded.

`/artifacts/active` and `/artifacts/active/export` return `503` when `ZONE2_API_KEY` is unset, and
`401` when the supplied API key is missing or invalid.

## Observability

Use `/metrics` for lightweight deployment dashboards. The endpoint reports total request counts,
per-method/path status counts, average latency, max latency, and last status code.

Use `X-Request-ID` to join client-side smoke checks with API responses and logs. During incidents,
capture the request ID, endpoint, response status, and readiness blockers before restarting services.

## Rollback

Roll back by pointing `ACTIVE_MODEL_BUNDLE` at the previous signed bundle and recreating the API
container:

```bash
ACTIVE_MODEL_BUNDLE=zone2/runner/artifacts/previous_bundle.zip docker compose --profile api up -d --force-recreate api
curl -fsS http://localhost:8000/ready
```

If the active bundle path was changed through environment configuration, restore the previous value
in the deployment environment and rerun the smoke checks above. Never copy raw Zone 1 data into Zone
2 to debug a rollback.

## Stop

```bash
docker compose --profile api stop api
```

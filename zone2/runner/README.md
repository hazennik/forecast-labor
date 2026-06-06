# Zone 2 Inference Runner

Zone 2 is the subnet-facing inference boundary. It must load signed model bundles only and must not retrain models or access raw training data.

Expected runtime inputs:

- `ZONE2_ARTIFACT_DIR`: directory containing signed model bundles.
- `ACTIVE_MODEL_BUNDLE`: optional explicit path to the active signed bundle.
- `ACTIVE_SUBNET`: subnet adapter target, defaulting to `sn41` until Phase 7 expands adapter support.
- `ZONE2_API_KEY`: required API key for protected artifact status and export endpoints.
- `API_RATE_LIMIT_ENABLED`: enables forecast request rate limiting, defaulting to `true`.
- `API_RATE_LIMIT_REQUESTS_PER_MINUTE`: per-client forecast request limit, defaulting to `60`.

The Phase 6A API exposes health, readiness, metrics, artifact status, artifact export, and forecast endpoints. Forecast responses are served only after a verified signed artifact loader can extract the active bundle and load the model.

Protected endpoints require the key in the `X-API-Key` request header. Health and readiness endpoints remain unauthenticated for deployment probes.

Local deployment:

```bash
docker compose --profile api up -d api
```

The `api` Compose profile uses `infra/api/Dockerfile` and mounts only `zone2/runner/artifacts` and `zone2/runner/extracted`. It does not mount raw data, Zone 1, ETL, feature, model-source, backtest, or script directories.

Deployment isolation checks fail readiness and forecast serving if Zone 2 artifact paths are configured inside raw data, Zone 1, training code, backtest, feature, ETL, model-source, or script directories. Runtime artifacts should remain under the Zone 2 runner artifact and extraction directories.

Forecast requests are rate limited per client and endpoint before model inference runs. When the limit is exceeded, `/forecast` returns `429` with a `Retry-After` header.

Operational request metrics are available at `/metrics`. The response includes total request counts plus per-method/path status counts and latency aggregates for lightweight deployment dashboards.

Every API response includes `X-Request-ID` for operational correlation. If callers provide `X-Request-ID`, the API echoes it; otherwise, the API generates a UUID for the response.


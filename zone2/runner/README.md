# Zone 2 Inference Runner

Zone 2 is the subnet-facing inference boundary. It must load signed model bundles only and must not retrain models or access raw training data.

Expected runtime inputs:

- `ZONE2_ARTIFACT_DIR`: directory containing signed model bundles.
- `ACTIVE_MODEL_BUNDLE`: optional explicit path to the active signed bundle.
- `ACTIVE_SUBNET`: subnet adapter target, defaulting to `sn41` until Phase 7 expands adapter support.

The Phase 6A API exposes health, readiness, artifact status, and forecast endpoints. Forecast responses remain unavailable until a verified signed artifact loader is wired into the runner.


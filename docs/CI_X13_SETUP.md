# CI X-13 Service Setup Guide

**Version:** 1.1  
**Last Updated:** 2026-05-08  
**Status:** Phase 6.5 - X-13 CI quality gate enabled

---

## Overview

This document describes the X-13ARIMA-SEATS seasonal adjustment quality gate in CI/CD.
The test workflow now builds the X-13 Docker image, runs a real X-13 binary check, and
executes the golden diagnostics verification inside that image.

**Current State (Phase 6.5):**
- ✅ X-13 service code and Dockerfile exist (`infra/x13/`)
- ✅ CI builds the X-13 image on every test run before the quality gate
- ✅ `scripts/record_golden_diagnostics.py --verify` computes fresh M/Q diagnostics
- ✅ Golden diagnostics quality gate validates M-statistics and Q-statistics against
  `tests/fixtures/golden_baselines/golden_seasonal_diagnostics_ci.json`
- ✅ `publish-x13-image.yml` publishes release images to GitHub Container Registry

---

## Architecture

### Full CI Gate

```
CI Test Run
  ├─ Build X-13 Docker image from infra/x13/Dockerfile
  ├─ Verify x13as binary inside the image
  └─ Golden diagnostics validation
      ├─ Run real X-13ARIMA-SEATS inside the image
      ├─ Compute fresh M1-M11 and Ljung-Box Q-statistics
      └─ Compare fresh diagnostics with committed baselines
```

---

## Implementation Steps

### Step 1: Build and Test X-13 Docker Image Locally

```bash
# Build X-13 Docker image
docker build -t forecast-x13:latest -f infra/x13/Dockerfile infra/x13/

# Test image locally
docker run -d --name test-x13 -p 5000:5000 forecast-x13:latest

# Verify service
curl http://localhost:5000/health

# Expected response: {"status": "healthy", "service": "x13-arima-seats"}

# Clean up
docker stop test-x13
docker rm test-x13
```

### Step 2: Publish Image to GitHub Container Registry

Use the `Publish X-13 Image` GitHub Actions workflow. It runs on manual dispatch and on
changes to X-13-related files on `main`, then publishes:

- `ghcr.io/<owner>/<repo>/x13:latest`
- `ghcr.io/<owner>/<repo>/x13:<commit-sha>`

### Step 3: Update GitHub Actions Workflow

**File:** `.github/workflows/test.yml`

The main test workflow builds the X-13 image locally for each run and executes the gate
inside the image:

```yaml
- name: Build X-13 CI image
  run: docker build -t "${X13_CI_IMAGE}" -f infra/x13/Dockerfile infra/x13/

- name: Check golden diagnostics (X-13 Quality Gate)
  run: |
    docker run --rm \
      -v "${{ github.workspace }}:/app" \
      -w /app \
      -e PYTHONPATH=/app \
      "${X13_CI_IMAGE}" \
      python3 scripts/record_golden_diagnostics.py \
        --vintage-date 2024-01-15 \
        --verify \
        --force-synthetic \
        --output-file tests/fixtures/golden_baselines/golden_seasonal_diagnostics_ci.json
```

### Step 4: Verification Behavior

`--verify` now records current diagnostics into a temporary file, extracts current
M-statistics and Q-statistics, and compares them against the committed golden baseline.
The command exits non-zero if the baseline is missing, current diagnostics cannot be
computed, or any hard M-statistic/Q-statistic gate fails.

CI intentionally uses `--force-synthetic` with the deterministic CI baseline
`golden_seasonal_diagnostics_ci.json` because production vintages under `data/` are
gitignored and unavailable in GitHub Actions. This still runs real X-13 and compares
fresh M/Q diagnostics. The production baseline remains
`golden_seasonal_diagnostics.json` and should be verified locally or in a production-like
environment with the 2025-11-29 vintage available.

---

## Troubleshooting

### Q: Why is X-13 not deployed in CI yet?

**A:** Phase 5 focused on establishing quality gates and testing infrastructure. Deploying X-13 as a persistent CI service requires:

1. Publishing Docker image to container registry (requires permissions)
2. Ensuring X-13 service stability (health checks, startup time)
3. Managing CI build time increase (~2-3 minutes for X-13 startup)
4. Handling potential X-13 failures gracefully

These are deferred to Phase 6 when full backtesting begins and X-13 reliability is critical.

### Q: How do I test X-13 integration locally?

**A:** Use Docker Compose:

```bash
# Start all services including X-13
make up

# Verify X-13 service
curl http://localhost:5000/health

# Run tests with real X-13
export X13_SERVICE_URL=http://localhost:5000
pytest tests/seasonal/ -v

# Run golden diagnostics verification
python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --verify
```

### Q: What if X-13 service fails in CI?

**A:** Current Phase 6.5 behavior:

- Build fails immediately if X-13 unavailable
- The golden diagnostics gate does not fall back to structure-only validation
- Ensures production quality gates are enforced

### Q: How long does X-13 add to CI runtime?

**A:** Estimated breakdown:

- Pull image: ~30 seconds (first time, cached after)
- Start service: ~10-15 seconds
- Health check wait: ~5 seconds
- Run tests: +2-3 minutes (real X-13 computation vs instant mock)
- **Total:** ~3-4 minutes additional CI time

For frequent CI runs, this is acceptable. For PR checks, may want to:
- Cache X-13 results per vintage
- Run X-13 tests only on main branch (not PRs)
- Use pre-computed golden baselines (no re-computation)

---

## Security Considerations

### Container Registry Access

**Public Image (Recommended for Open Source):**

```yaml
services:
  x13:
    image: ghcr.io/USERNAME/forecast-labor/x13:latest
    # No credentials needed for public images
```

**Private Image (Recommended for Enterprise):**

```yaml
services:
  x13:
    image: ghcr.io/USERNAME/forecast-labor/x13:latest
    credentials:
      username: ${{ github.actor }}
      password: ${{ secrets.GITHUB_TOKEN }}
```

### Dockerfile Security

The X-13 Dockerfile should:
- ✅ Use official base images (e.g., `python:3.11-slim`)
- ✅ Run as non-root user
- ✅ No secrets embedded in image
- ✅ Minimal attack surface (only X-13 binaries and service)

**File:** `infra/x13/Dockerfile`

```dockerfile
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 x13user

# Install X-13
COPY install_x13.py /tmp/
RUN python /tmp/install_x13.py

# Copy service code
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Switch to non-root
USER x13user

EXPOSE 5000
CMD ["/app/entrypoint.sh"]
```

---

## Monitoring and Alerts

### Health Checks

X-13 service should expose health endpoint:

```bash
# Health check endpoint
curl http://localhost:5000/health

# Response
{
  "status": "healthy",
  "service": "x13-arima-seats",
  "version": "1.1.0",
  "uptime_seconds": 123
}
```

### CI Metrics to Track

Once X-13 fully deployed:

- **X-13 startup time:** Target < 15 seconds
- **X-13 computation time:** Target < 2 minutes per test suite
- **X-13 failure rate:** Target < 1% (very stable)
- **Golden diagnostics match rate:** Target 100% (or known deviations documented)

---

## Migration Checklist

### Phase 6 Deployment

- [x] Build and test X-13 Docker image in CI
- [x] Add GitHub Container Registry publishing workflow
- [x] Update `.github/workflows/test.yml` with X-13-backed quality gate
- [x] Run golden diagnostics verification with full M/Q comparison
- [x] Update documentation to reflect X-13 now required
- [x] Remove structure-only verification fallback
- [ ] Monitor CI runtime impact (target: < 5 minutes increase)

---

## References

### Related Files

- **X-13 Dockerfile:** `infra/x13/Dockerfile`
- **X-13 Install Script:** `infra/x13/install_x13.py`
- **X-13 Service Entrypoint:** `infra/x13/entrypoint.sh`
- **CI Workflow:** `.github/workflows/test.yml`
- **Golden Diagnostics Script:** `scripts/record_golden_diagnostics.py`
- **Seasonal Pipeline:** `seasonal/pipeline.py`

### External Resources

- [X-13ARIMA-SEATS Official Documentation](https://www.census.gov/srd/www/x13as/)
- [GitHub Container Registry Documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub Actions Services](https://docs.github.com/en/actions/using-containerized-services/about-service-containers)

---

**Document Revision History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-24 | System | Initial documentation (Phase 5.9.2 Quality Gap Resolution) |
| 1.1 | 2026-05-08 | AI Assistant | Phase 6.5 X-13 CI quality gate enabled |

---

**Next Steps:** Monitor CI runtime and update the golden baseline only after reviewed,
intentional seasonal adjustment changes.


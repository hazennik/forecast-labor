# CI X-13 Service Setup Guide

**Version:** 1.0  
**Last Updated:** 2025-11-24  
**Status:** Phase 5.9.2 - Configuration Prepared, Full Deployment Deferred to Phase 6+

---

## Overview

This document describes how to enable full X-13ARIMA-SEATS seasonal adjustment testing in CI/CD. Currently, tests use graceful fallback when X-13 is unavailable. This guide explains how to enable the full service.

**Current State (Phase 5.9.2):**
- ✅ X-13 service code and Dockerfile exist (`infra/x13/`)
- ✅ Tests support graceful fallback to mock service
- ✅ CI workflow configured with fallback logic
- ⏳ X-13 Docker image not yet published to container registry
- ⏳ GitHub Actions `services:` configuration prepared but not active

**Target State (Phase 6+):**
- ✅ X-13 Docker image published to GitHub Container Registry
- ✅ CI workflow pulls pre-built image
- ✅ Full X-13 seasonal adjustment runs in every CI build
- ✅ Golden diagnostics quality gate validates M-statistics and Q-statistics

---

## Architecture

### Current Fallback Mechanism

```
CI Test Run
  ├─ Check X-13 service availability
  │   └─ If unavailable: Use mock service (tests pass with warning)
  ├─ Run seasonal adjustment tests
  │   └─ Mock returns synthetic M/Q statistics
  └─ Golden diagnostics validation
      └─ JSON structure validation only (no real X-13 comparison)
```

### Target Full Service

```
CI Test Run
  ├─ Pull X-13 Docker image from GitHub Container Registry
  ├─ Start X-13 service (GitHub Actions services:)
  ├─ Run seasonal adjustment tests
  │   └─ Real X-13ARIMA-SEATS computation
  └─ Golden diagnostics validation
      └─ Full M1-M11 and Q-statistics comparison with baselines
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

```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Tag image for GitHub Container Registry
docker tag forecast-x13:latest ghcr.io/USERNAME/forecast-labor/x13:latest
docker tag forecast-x13:latest ghcr.io/USERNAME/forecast-labor/x13:v1.0.0

# Push to registry
docker push ghcr.io/USERNAME/forecast-labor/x13:latest
docker push ghcr.io/USERNAME/forecast-labor/x13:v1.0.0

# Verify in GitHub
# Navigate to: https://github.com/USERNAME/forecast-labor/packages
```

### Step 3: Update GitHub Actions Workflow

**File:** `.github/workflows/test.yml`

Uncomment and configure the X-13 service:

```yaml
services:
  postgres:
    image: postgres:15
    # ... (existing PostgreSQL config)
  
  x13:
    image: ghcr.io/USERNAME/forecast-labor/x13:latest
    credentials:
      username: ${{ github.actor }}
      password: ${{ secrets.GITHUB_TOKEN }}
    options: >-
      --health-cmd "curl -f http://localhost:5000/health || exit 1"
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
    ports:
      - 5000:5000

env:
  # Add X-13 service URL
  X13_SERVICE_URL: http://localhost:5000
  X13_SERVICE_TIMEOUT: 60
```

### Step 4: Remove Fallback Logic (Optional)

Once X-13 service is reliably available, remove fallback:

**File:** `scripts/record_golden_diagnostics.py`

```python
# Remove --skip-x13 flag support
# Require X-13 service for all verification

def verify_diagnostics(require_x13: bool = True):
    if require_x13 and not x13_service_available():
        raise RuntimeError("X-13 service required but unavailable")
    # ... rest of verification
```

**File:** `.github/workflows/test.yml`

```yaml
# Remove conditional logic
- name: Check golden diagnostics (X-13 Quality Gate)
  run: |
    python scripts/record_golden_diagnostics.py --vintage-date 2024-01-15 --verify
  # Now fails build if X-13 unavailable (no more fallback)
```

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

**A:** Current fallback behavior:

- Tests log warning: "X-13 service unavailable, using mock"
- Tests continue with mock service (synthetic M/Q statistics)
- Golden diagnostics validates JSON structure only
- Build passes (no blocking)

Future behavior (after full deployment):

- Build fails immediately if X-13 unavailable
- No mock fallback
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

### Phase 6 Deployment (When Ready)

- [ ] Build and test X-13 Docker image locally
- [ ] Publish image to GitHub Container Registry (ghcr.io)
- [ ] Verify image pull works in CI (test with docker pull)
- [ ] Update `.github/workflows/test.yml` with X-13 service
- [ ] Add X13_SERVICE_URL environment variable
- [ ] Run CI build and verify X-13 service starts
- [ ] Run golden diagnostics verification (full, not fallback)
- [ ] Monitor CI runtime impact (target: < 5 minutes increase)
- [ ] Update documentation to reflect X-13 now required
- [ ] Remove mock service fallback (enforce X-13 availability)
- [ ] Add CI alerts for X-13 service failures

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

---

**Next Steps:** Defer full X-13 CI deployment to Phase 6 when backtesting begins. Current fallback mechanism is sufficient for Phase 5 completion.


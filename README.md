# forecast-labor
This repository contains a purpose-built macroeconomic forecasting system optimized for extremely accurate U.S. job-market predictions. It ingests high-frequency public data (UI claims, Treasury withholdings, CES/LAUS vintages, weather, strikes) and optional private microdata, processes them with X-13 seasonal adjustment, constructs mixed-frequency features, and trains a hybrid forecasting architecture (Dynamic Factor Model + MIDAS + XGBoost quantile + revision model). The system outputs calibrated probability distributions, reconciled state/national forecasts, and interpretable diagnostics suitable for institutional use. A built-in SN41 miner adapter converts each forecast into validated, low-noise probability vectors for top-tier mining performance. Designed for portability—runs locally on macOS and deploys seamlessly to a dedicated server.

# Labor Market Forecasting Engine + SN41 Miner

An elite, real-time U.S. labor-market forecasting system designed for institutional-grade accuracy and top-tier SN41 mining performance. The system ingests high-frequency public and private labor data, applies X-13 seasonal adjustment, constructs mixed-frequency features, and trains a hybrid forecasting architecture (DFM + MIDAS + GBM quantile + revision model). Outputs include calibrated probability distributions, state/national reconciled forecasts, and SN41-ready probability vectors.

---

## ✅ Features
- Real-time ingestion of labor-market signals  
- X-13 seasonal adjustment (Dockerized)  
- Mixed-frequency feature engineering (daily/weekly → monthly)  
- Dynamic Factor, MIDAS, and Quantile ML models  
- First-to-final revision prediction engine  
- Probability calibration for SN41 Brier/log-loss optimization  
- Portable Docker-based pipeline (Mac → server)  
- SN41 miner adapter for live submissions  
- Backtesting engine using real-time vintages  
- Institutional-quality dashboards & diagnostics  

---

## ✅ Repo Structure
/infra/          # docker images, containers, deployment
/app/            # API endpoints for forecasting & miner
/etl/            # data ingestion & validation
/seasonal/       # X-13 specs, regressors
/features/       # engineered features (MIDAS, DFM inputs, etc.)
/models_src/     # model training + inference code
/backtests/      # vintage-honest backtesting
/recon/          # state/national reconciliation
/sn41/           # miner integration logic
/agents_src/     # optional AI assistants & automation
/dashboards_src/ # Streamlit or Metabase docs
/data/           # local only (ignored)

---

## ✅ Quick Start (Local)

### First Time Setup
```bash
# Clone repository
git clone <repo-url>
cd forecast-labor

# Generate test data (vintages are gitignored, baselines are frozen in git)
make setup-test-data

# Start Docker services
make up

# Seed production data (requires API keys in .env)
make seed

# Run pipeline
make seasonal
make features
make train
make backtest
```

**Note:** Vintage data is NOT in the repository (gitignored). Run `make setup-test-data` to generate synthetic test vintages for development, or `make seed` with production API keys for real data.

### Testing
```bash
# Run full test suite (287 tests)
make test

# Test suite automatically uses synthetic test vintages
# No real API calls made during testing
```

## ✅ Deployment (Server)
1. Clone repo.
2. Create `.env.server` with production API keys.
3. Generate test data: `make setup-test-data` (or run real ETL)
4. Run `docker compose up -d`.
5. Run ETL → seasonal → train pipeline.
6. Enable miner service.

⸻

✅ License

All rights reserved. Unauthorized use prohibited.

⸻

✅ Contact

For private licensing or institutional access, contact the repository owner.

# ✅ Versioned Roadmap (Clear + Achievable)**

```markdown
# Roadmap

## ✅ Phase 1 — Foundation (Weeks 1–2)
- Repository scaffold
- Dockerized infra stack (MinIO, Postgres, MLflow, Prefect)
- Public ETL pipelines
- Data validation & freshness checks
- Vintage snapshotting system

## ✅ Phase 2 — Seasonal & Feature Engineering (Weeks 2–4)
- X-13 Docker service
- Holiday/strike/weather regressors
- Mixed-frequency (MIDAS) lags
- Withholdings alignment
- Feature store structure

## ✅ Phase 3 — Core Modeling (Weeks 4–8)
- Dynamic Factor Model (DFM)
- MIDAS regression
- Quantile XGBoost/LightGBM
- First-to-final revision model
- Calibration layer (isotonic + conformal)
- MLflow tracking

## ✅ Phase 4 — Backtesting Suite (Weeks 8–10)
- Real-time vintage backtests
- CRPS, sMAPE, RMSE, turning-point metrics
- Stability & noise diagnostics
- Report generator (HTML/PDF)

## ✅ Phase 5 — SN41 Integration (Weeks 10–12)
- Event catalog & bins
- Probability vector generator
- Signing & submission logic
- Miner service with retries/logging
- Dry-run → live activation

## ✅ Phase 6 — Institutional Hardening (Weeks 12–16)
- Dashboards (Streamlit/Metabase)
- API endpoints for forecasts
- Model versioning policies
- Data licensing abstraction
- Security hardening

## ✅ Phase 7 — Optimization & Monetization (Weeks 16+)
- Accuracy refinement
- New private data integrations
- Forecast products (API/feeds)
- Institutional packaging
- Optional commercialization

## ✅ Contribution Guidelines + Repo Structure Explanation
# Contributing Guidelines

## ✅ Branching Model
- `main` — stable, production-ready
- `dev` — active development
- Feature branches: `feature/<name>`

All PRs must include:
- Data validation tests
- Style compliance (Black, Ruff)
- Backtest report (if model changes)
- Zero-breaking-changes for API

## ✅ Code Style
- Python 3.11
- Use type hints everywhere
- Favor pure functions for modeling
- Keep ETL deterministic & reproducible
- No secrets committed — use `.env`

## ✅ Repo Structure Explanation
- **/etl/** — Public/private ingestion modules with data-quality checks.  
- **/seasonal/** — X-13 specs + regressors (holidays, strikes, weather).  
- **/features/** — Transformation from raw → model-ready features.  
- **/models_src/** — DFM, MIDAS, GBM quantile, revision & calibration code.  
- **/backtests/** — Vintage-honest evaluation suite (no future leakage).  
- **/recon/** — MinT/WLS reconciliation for state/national alignment.  
- **/sn41/** — Mapping logic to produce SN41-ready probability vectors.  
- **/agents_src/** — AI automation tools (optional).  
- **/dashboards_src/** — Monitoring dashboards (Streamlit/Metabase).  
- **/infra/** — Docker images, build scripts, CI/CD helpers.

## ✅ Pull Request Requirements
- Pass all CI checks  
- Zero nondeterministic code  
- No edits to vintage data  
- Full reproducibility from raw → forecast  
- Updated documentation for new components  

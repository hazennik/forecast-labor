Full-scope repo scaffolding you can paste straight into your README. It includes every directory + key subdirs with brief descriptions so an IDE agent (or a human) can implement it cleanly.

forecast-labor/
├─ README.md                      # Project overview, quick start, links to docs
├─ LICENSE                        # Proprietary license (All Rights Reserved)
├─ .gitignore                     # Ignore /data, secrets, artifacts, venv, etc.
├─ .env.example                   # Template env vars for local & server
├─ docker-compose.yml             # Multi-service local stack (minio, pg, mlflow, x13, api, dashboards, miner)
├─ Makefile                       # One-liners: up/seed/seasonal/features/train/backtest/submit/miner
│
├─ infra/                         # Infra build files (images, IaC, compose profiles)
│  ├─ x13/                        # Dockerfile + entrypoint for X-13 microservice
│  ├─ models/                     # Dockerfile for training/inference workers
│  ├─ miner/                      # Dockerfile for subnet submitter service (any subnet)
│  ├─ dashboards/                 # Dockerfile for Streamlit/Metabase
│  ├─ agents/                     # Dockerfile for agent runner (optional)
│  └─ compose/                    # Compose overrides (zone1/zone2, prod profiles)
│
├─ app/                           # Lightweight API (FastAPI) for health/forecast/export
│  ├─ main.py                     # Entrypoints (health, run forecast, serve artifacts)
│  ├─ routers/                    # Route modules (forecast, reports, status)
│  └─ schemas/                    # Pydantic models for inputs/outputs
│
├─ etl/                           # Deterministic data ingestion + validation
│  ├─ public/                     # Public data sources (reproducible, versioned)
│  │  ├─ bls_ces/                 # NFP & sector payrolls (with vintaging)
│  │  ├─ bls_laus/                # State employment series
│  │  ├─ claims/                  # UI initial & continuing claims (state + national)
│  │  ├─ treasury_withholdings/   # Daily tax withholdings (pay-period aligned)
│  │  ├─ strikes/                 # BLS/FMCS strike logs
│  │  ├─ weather/                 # NOAA storms/smoke indices
│  │  └─ cnbfs/                   # Census Business Formation Statistics
│  ├─ private_hooks/              # Adapters for Homebase/UKG/ADP/postings (disabled by default)
│  ├─ validators/                 # Great Expectations/dbt checks (freshness, schema, nulls)
│  ├─ dbt/                        # Optional: dbt models for staging/clean tables
│  └─ common/                     # Shared ETL utils (downloader, decompressor, snapshotter)
│
├─ seasonal/                      # X-13ARIMA-SEATS specs & runners
│  ├─ specs/                      # .spc templates per series (maintained by Stats Agent)
│  ├─ regressors/                 # Holiday timing, strikes, weather dummies
│  ├─ diagnostics/                # M-stats, stability reports (gate: fail if degrades)
│  └─ service_client/             # Python client to call x13 microservice
│
├─ features/                      # Mixed-frequency features (daily/weekly → monthly)
│  ├─ midas/                      # MIDAS lag constructors & weighting schemes
│  ├─ dfm_inputs/                 # Standardized inputs for factor extraction
│  ├─ transforms/                 # Scaling, calendar align, winsorization
│  ├─ aggregations/               # State→national, sector→total signals
│  └─ registry.py                 # Single registry of produced feature tables (Parquet)
│
├─ models_src/                    # Modeling stack (econometric + ML + calibration)
│  ├─ dfm/                        # Dynamic Factor Model (extraction, smoothing)
│  ├─ midas/                      # MIDAS regression for nowcasting
│  ├─ gbm_quantile/               # XGBoost/LightGBM quantile models
│  ├─ revision/                   # First→second & benchmark revision models
│  ├─ calibration/                # Isotonic + conformal prediction calibration
│  ├─ reconcile/                  # MinT/WLS reconciliation utilities
│  ├─ pipelines/                  # Orchestrated train/infer flows (Prefect)
│  └─ utils/                      # Metrics (RMSE/sMAPE/CRPS), IO, MLflow loggers
│
├─ backtests/                     # Vintage-honest evaluation suite
│  ├─ vintage_harness/            # Reconstruct “what was known then”
│  ├─ metrics/                    # Accuracy, coverage, turning points, stability
│  ├─ scenarios/                  # What-if shocks (storms/strikes) for audits
│  └─ reports/                    # HTML/PDF summary generation
│
├─ recon/                         # Hierarchical reconciliation (stability boost)
│  ├─ mint/                       # MinT reconciliation methods & shrinkage covariance
│  └─ tests/                      # Coherence tests (nation == Σstates within tolerance)
│
├─ subnets/                       # Subnet integration (adapter pattern for any Bittensor subnet)
│  ├─ base_adapter.py             # Abstract base class defining subnet interface
│  ├─ registry.py                 # Registry to discover & load subnet adapters
│  ├─ scheduler.py                # Handles multi-subnet scheduling & windows
│  ├─ scoring_shim.py             # Abstraction layer for subnet-specific scoring
│  ├─ sn41/                       # SN41-specific implementation (labor market forecasts)
│  │  ├─ adapter.py               # SN41 adapter implementing base interface
│  │  ├─ event_catalog.py         # SN41 event/bin definitions & versions
│  │  ├─ payload_builder.py       # SN41 probability vector builders + validators
│  │  ├─ config.yaml              # SN41-specific config (bins, targets, cadence)
│  │  └─ tests/                   # SN41-specific tests
│  └─ keys/                       # Hotkey/coldkey storage path (excluded from VCS)
│
├─ agents_src/                    # AI automation & maintenance agents
│  ├─ planner/                    # Global planner/orchestrator
│  ├─ data_eng/                   # ETL watchdog & schema drift fixer
│  ├─ seasonal/                   # X-13 spec maintenance & diagnostics
│  ├─ features/                   # Feature refresher & staleness checks
│  ├─ trainer/                    # Model training runner (gated)
│  ├─ nowcast/                    # In-month updates near release windows
│  ├─ mint/                       # Reconciliation agent
│  ├─ revision/                   # Revision forecasting agent
│  ├─ evaluator/                  # CI gates (sMAPE/CRPS/coverage/coherence)
│  ├─ explainer/                  # Human-readable diagnostics & change logs
│  └─ ops/                        # SRE: restarts, resource checks, alert hooks
│
├─ dashboards_src/                # Monitoring & analyst views
│  ├─ streamlit/                  # App: freshness, accuracy, probabilities, miner health
│  └─ metabase/                   # SQL questions & dashboards (if used)
│
├─ configs/                       # Configuration files
│  ├─ subnets/                    # Subnet-specific configurations
│  │  ├─ sn41.yaml                # SN41 config (bins, targets, cadence, weights)
│  │  └─ template.yaml            # Template for new subnet adapters
│  └─ zones/                      # Zone-specific settings (training vs inference)
│
├─ docs/                          # Project documentation (renders well on GitHub)
│  ├─ ACCURACY_MAP.md             # Accuracy targets & ranges
│  ├─ ACCURACY_DESCRIPTION.md     # Why the ceiling exists; how we hit the top end
│  ├─ FORECASTING_CAPABILITIES.md # Everything the system predicts
│  ├─ 5_PILLARS.md                # Architecture principles for elite accuracy
│  ├─ PROJECT_INSTRUCTIONS.md     # Build spec that agents follow
│  ├─ AGENTS_AND_OPS_RUNBOOK.md   # Agents roster, autonomy levels, ops gates
│  ├─ SUBNET_INTEGRATION.md       # How to add new subnet adapters
│  ├─ arch/                       # Diagrams (SVG/PNG) & two-zone notes
│  │  ├─ architecture.svg
│  │  └─ two_zone_architecture.md
│  ├─ ops/                        # Runbooks & CI/CD gates
│  │  ├─ DEPLOY_GATES.md          # sMAPE/coverage/coherence thresholds (hard blockers)
│  │  └─ RUNBOOK.md               # Incident, rollback, release calendar
│  └─ planning/                   # Timeline & costs (public vs private data)
│     └─ TIMELINE_AND_COSTS.md
│
├─ scripts/                       # CLI helpers for local dev/ops
│  ├─ seed_public_data.py         # Download first snapshots & write vintages
│  ├─ run_x13_bundle.py           # Batch seasonal adjustment job
│  ├─ build_features.py           # Produce feature tables
│  ├─ train_all.py                # Train DFM/MIDAS/GBM + revision + calibration
│  ├─ run_backtest.py             # Full vintage backtest + report
│  ├─ make_subnet_payload.py      # Build & validate subnet payloads (any subnet)
│  └─ submit_to_subnet.py         # Submit to active subnet (server-only)
│
├─ tests/                         # Unit/integration tests (PyTest)
│  ├─ etl/                        # Schema/freshness/rowcount tests
│  ├─ seasonal/                   # M-stat stability, regressor effects
│  ├─ features/                   # Determinism & shape checks
│  ├─ models/                     # Reproducibility & leakage guards
│  ├─ backtests/                  # Metric computation & report generation
│  └─ subnets/                    # Adapter pattern tests, payload validation
│
├─ zone1/                         # Private training zone (kept off public servers if needed)
│  ├─ configs/                    # Training profiles (public-only vs private-data)
│  └─ artifacts/                  # Versioned models & calibrators (signed packages)
│
├─ zone2/                         # Subnet-facing inference zone
│  ├─ runner/                     # Minimal inference app; loads signed artifacts only
│  ├─ logs/                       # Submission logs, latencies, rewards
│  └─ active_subnet.env           # Currently active subnet configuration
│
└─ data/                          # Local data lake (ignored in git)
   ├─ raw/                        # Raw downloads per source
   ├─ vintages/                   # Immutable monthly snapshots (DO NOT EDIT)
   ├─ features/                   # Parquet feature tables
   ├─ artifacts/                  # Current model bundles & scalers
   ├─ reports/                    # Backtest HTML/PDF & CSV metrics
   └─ secrets/                    # Keys/tokens (chmod 600; NEVER commit)


   Notes & conventions
	•	Immutability: Treat data/vintages/ as append-only; never rewrite history.
	•	Determinism: All pipelines must be reproducible given the same vintage + config.
	•	Calibration-first: SN41 rewards smooth, low-variance, well-calibrated probability vectors.
	•	Two-Zone flow: Only signed artifacts move from zone1 → zone2; no raw data or training code leaves Zone 1.
	•	Agents guardrails: Auto-merge only when CI + accuracy gates pass; human review for architecture changes.

Suggested .gitignore essentials
/data/
/zone1/artifacts/
/zone2/logs/
/zone2/active_subnet.env
/subnets/keys/
/**/*.env
/.venv
/__pycache__/
*.pyc
.prof

Makefile targets (example)
make up          # Start local stack
make seed        # Pull public data & snapshot vintages
make seasonal    # Run X-13 with regressors & diagnostics
make features    # Build mixed-frequency features
make train       # Train DFM/MIDAS/GBM + revision + calibration (logs to MLflow)
make backtest    # Vintage-honest eval & report
make submit      # Build subnet payloads for active subnet (dry run locally)
make miner       # Start subnet submitter (server-only; uses ACTIVE_SUBNET env var)
make down        # Stop stack


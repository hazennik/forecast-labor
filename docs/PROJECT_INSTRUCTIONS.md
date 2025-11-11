✅ PROJECT INSTRUCTIONS

Project Title:

Real-Time U.S. Labor-Market Forecasting Engine + SN41 Miner

⸻

Project Objective:

Build a fully operational forecasting system capable of producing extremely accurate, low-noise, institution-grade U.S. labor-market predictions, and generating calibrated probability distributions for SN41 that position this system as a top 1% miner and an institutional-quality forecasting asset.

⸻

System Requirements & Mandates

✅ 1. Architecture Requirements
	•	Use a modular, containerized architecture (Docker Compose).
	•	The system must run locally on macOS (Apple Silicon) and seamlessly on a hosted Linux server.
	•	All services should be separated cleanly:
	•	etl (data ingestion pipelines)
	•	seasonal (X-13 service + regressors)
	•	features (mixed-frequency engineering)
	•	models (DFM, MIDAS, GBM quantile, revision model, calibration)
	•	backtests (vintage-honest evaluation)
	•	miner (SN41 payload generator + submitter)
	•	dashboards (Streamlit or Metabase)
	•	agents (optional AI automation)

⸻

✅ 2. Data Requirements

The ETL pipeline must ingest, validate, and version the following:

Public Data (Mandatory)
	•	Weekly UI Claims (national + state)
	•	Daily Treasury Tax Withholdings
	•	CES payrolls (with vintages)
	•	LAUS state employment
	•	BLS strike data
	•	NOAA weather disruptions
	•	Census Business Formation Statistics
	•	Optional: Google Trends labor signals

Private Data (Optional hooks)
	•	Homebase / UKG / ADP microdata
	•	Job postings (Lightcast / Indeed / LinkedIn)
	•	Card spend data (Facteus / Affinity)

Data Rules
	•	ALL data must be stored in immutable vintage snapshots.
	•	Never overwrite historical vintages.
	•	Enforce schema validation + data freshness checks.

⸻

✅ 3. Seasonal Adjustment Requirements
	•	All monthly series must be seasonally adjusted using X-13ARIMA-SEATS.
	•	Include regressors:
	•	holiday timing
	•	weather anomalies
	•	strikes
	•	Build an X-13 microservice container.
	•	Reject seasonal specs if M-stats degrade (automated test).

⸻

✅ 4. Feature Engineering Requirements

Build mixed-frequency features including:
	•	MIDAS-style weekly/daily → monthly lags
	•	Pay-period aligned Treasury withholdings
	•	Momentum, deviation-from-trend, and volatility features
	•	State-to-national aggregation signals
	•	Weather/strike adjustment signals

Features should be exported to:
/data/features/ as Parquet files.

⸻

✅ 5. Modeling Requirements

The system must implement the full hybrid economic forecasting stack:

✅ 1. Dynamic Factor Model (DFM)
	•	Extract latent job-market state
	•	Fuse dozens of signals
	•	Smooth noise & detect turning points

✅ 2. MIDAS Regression
	•	Consume weekly claims & daily withholdings
	•	Generate real-time nowcasts

✅ 3. Quantile ML Model (XGBoost or LightGBM)
	•	Predict all forecast quantiles
	•	Support nonlinearities
	•	Output uncertainty ranges

✅ 4. Revision Model
	•	Predict first → second print adjustments
	•	Predict first → benchmark (QCEW) shifts
	•	Improve accuracy vs. “true” job creation

✅ 5. Calibration Layer
	•	Conformal prediction
	•	Isotonic regression
	•	Ensure SN41 probability distributions are stable & valid

All model artifacts must be versioned via MLflow.

⸻

✅ 6. Backtesting Requirements

Implement a vintage-honest backtesting system:
	•	Reconstruct what was known each month historically
	•	No forward-looking data ever allowed
	•	Evaluate:
	•	RMSE
	•	sMAPE
	•	CRPS
	•	Turning point accuracy
	•	Interval coverage
	•	Produce HTML/PDF reports per run
	•	Block deployments if accuracy degrades

Outputs stored in:
/data/reports/.

⸻

✅ 7. SN41 Miner Integration Requirements

Build a complete SN41 prediction miner:
	•	Map predictions into SN41 event bins
	•	Generate low-noise, calibrated probability vectors
	•	Sign payloads using provided hotkey
	•	Submit reliably inside SN41 windows
	•	Retry logic with jitter, full logs, and error handling
	•	Health endpoint + submission logs

Miner must be disabled locally and enabled only via .env.server.

⸻

✅ 8. Operational Requirements
	•	Must run end-to-end via a Makefile:
	•	make up
	•	make seed
	•	make seasonal
	•	make features
	•	make train
	•	make backtest
	•	make submit
	•	make miner
	•	Code must be:
	•	deterministic
	•	reproducible
	•	zero nondeterminism across runs
	•	Logs must be clean, timestamped, and stored per run.

⸻

✅ 9. Code Quality Requirements
	•	Full type hints (Python typing)
	•	Black + Ruff formatting
	•	Modular file structure
	•	No secrets in code
	•	No vendor data committed
	•	CI checks (optional for now)

⸻

✅ 10. Documentation Requirements

Generate:
	•	README.md (already done)
	•	Architecture diagram (SVG/PDF)
	•	Module docs under /docs/
	•	Developer setup instructions
	•	Data source notes & update schedule
	•	SN41 payload specification

⸻

✅ 11. Repo Directory Structure (Enforced)
/infra/
/app/
/etl/
/seasonal/
/features/
/models_src/
/backtests/
/recon/
/sn41/
/agents_src/
/dashboards_src/
/data/ (ignored)
/docs/
/scripts/
.env.example
docker-compose.yml
Makefile

✅ 12. What “Done” Looks Like

The system must:

✅ Run end-to-end locally
✅ Run identically on a server
✅ Produce accurate forecasts
✅ Pass vintage backtests
✅ Output calibrated SN41 probability vectors
✅ Submit successfully to SN41
✅ Maintain stability, reproducibility, and reliability

The final product must be:
	•	Top 1% SN41 miner-capable
	•	Institution-grade forecasting engine
	•	Production-ready economic research pipeline
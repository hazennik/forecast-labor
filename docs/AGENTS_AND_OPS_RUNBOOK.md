AGENTS & OPERATIONS RUNBOOK

Full Automation, Monitoring, and Maintenance Framework for the Labor-Market Forecasting System

This document defines the agent ecosystem, automated workflows, governance, deployment model, and CI accuracy gates required for a top-1% labor-market prediction engine and SN41 miner.

It complements:
	•	✅ 5 Pillars.md
	•	✅ Project Instructions.md
	•	✅ Accuracy Map.md

and finalizes the operational architecture of the system.

⸻

1. Multi-Agent System Overview

Your forecasting platform uses a self-monitoring, self-optimizing AI agent ecosystem designed to perform:
	•	Data ingestion & quality checks
	•	Seasonal adjustment maintenance
	•	Feature engineering checks
	•	Model training & validation
	•	Revision forecasting & coherence checks
	•	Probability calibration
	•	SN41 vector generation
	•	System monitoring, anomaly detection, and automatic repair

Below is the full roster.

⸻

2. Agent Roster & Responsibilities

2.1 Planner Agent
	•	Maintains global understanding of system state
	•	Designs experiments and training jobs
	•	Suggests improvements based on error patterns
	•	Coordinates other agents’ tasks

⸻

2.2 Data Engineering Agent
	•	Monitors APIs (claims, Treasury, CES, LAUS, weather, strikes)
	•	Validates new data snapshots
	•	Ensures vintage integrity
	•	Detects missing data, schema drift, or feed failures
	•	Repairs or patches data without breaking backtests

⸻

2.3 Seasonal/Stats Agent
	•	Maintains X-13 spec files
	•	Rebuilds ARIMA models when needed
	•	Handles regressors for:
	•	strikes
	•	weather events
	•	holiday shifts
	•	Checks seasonal stability

⸻

2.4 Feature Engineering Agent
	•	Updates MIDAS and high-frequency feature lags
	•	Maintains DFM inputs
	•	Detects stale features
	•	Automatically rebuilds feature sets when new data relationships emerge

⸻

2.5 Model Training Agent
	•	Runs training pipelines for:
	•	DFM
	•	MIDAS
	•	Gradient boosting
	•	Revision models
	•	Ensures reproducible training
	•	Enforces non-leakage
	•	Manages MLflow model versioning

⸻

2.6 Nowcasting Agent
	•	Updates daily/weekly forecasts
	•	Generates near-release NFP and private payroll predictions
	•	Produces SN41-ready probability vectors
	•	Detects last-minute anomalies (claims revisions, unexpected strikes, storms)

⸻

2.7 Hierarchy (MinT) Agent
	•	Ensures coherence between:
	•	states → nation
	•	sectors → nation
	•	private → total payrolls
	•	Reconciles forecasts using MinT and shrinkage covariance estimators

⸻

2.8 Revision Analyst Agent
	•	Predicts first→second NFP revisions
	•	Predicts benchmark revisions
	•	Tracks CES drift vs. QCEW
	•	Improves accuracy of “true employment” estimation

⸻

2.9 Evaluator Agent
	•	Runs validation on each model version
	•	Applies CI gates (see Section 5)
	•	Generates score reports:
	•	sMAPE
	•	CRPS
	•	80% PI coverage
	•	Coherence
	•	Revision error
	•	Flags anomalies and blocks unsafe deployments

⸻

2.10 Explainer Agent
	•	Generates human-readable summaries
	•	Creates system diagnostics
	•	Explains forecast changes
	•	Converts model signals into clear English
	•	Can generate SN41 “commentary metadata” (optional)

⸻

2.11 Ops/SRE Agent
	•	Monitors uptime
	•	Monitors RAM/CPU/GPU loads
	•	Restarts failed services
	•	Prevents silent failures
	•	Manages logs, alerts, and resource scaling

⸻

3. Agent Autonomy Levels

Agents operate under guardrails that prevent catastrophic actions.

Level 0 — Read-Only

Can observe, report, propose.

Level 1 — Safe Write

Can modify documentation, configs, or local staging files.

Level 2 — Auto-Merge With Tests

Allowed only when:
	•	CI passes
	•	Accuracy gates pass
	•	No architecture changes involved
	•	Changes are in ETL, seasonal files, or features
	•	Deployment is deterministic

Level 3 — Human Review Required

Required for:
	•	Model architecture changes
	•	Changes that alter output ranges
	•	Historical backtest rewrites
	•	Anything that impacts SN41 submission logic
	•	Any training pipeline modifications

⸻

4. Two-Zone Deployment Architecture

For safety, accuracy, and SN41 integrity, your system uses two zones.

⸻

Zone 1 — Private Training Environment

Contains:
	•	Training data (including optional private microdata)
	•	Model artifacts
	•	Seasonal models
	•	Treasury-derived features
	•	Backtests
	•	Calibration models

Not exposed to SN41 or public networks.

Output:
	•	Digitally signed “forecast packages” sent to Zone 2.

⸻

Zone 2 — Subnet-Facing Inference Node

Contains only:
	•	Clean inference code
	•	Latest signed model weights
	•	SN41 submission logic
	•	Probability vector generation

Cannot access:
	•	Raw data
	•	Training features
	•	Code that would reveal proprietary architecture

This separation prevents IP leakage and guarantees reproducibility.

⸻

5. CI/CD Accuracy Gates (Hard Blockers)

These gates protect accuracy, reproducibility, and model stability.

A new model cannot deploy unless:

✅ Gate 1 — NFP sMAPE
	•	0.15–0.25 (public-only)
	•	0.12–0.20 (public + private)

✅ Gate 2 — 80% Prediction Interval Coverage
	•	Must be between 78–85%

✅ Gate 3 — Probability Coherence
	•	Coherence error < 0.2%
	•	No negative probabilities
	•	No non-monotonic cumulative distributions

✅ Gate 4 — Revision Error Control
	•	First→second revision MAE < 70k

✅ Gate 5 — Calibration
	•	CRPS must not degrade from previous model

✅ Gate 6 — State/Sector Coherence
	•	MinT reconciliation must converge
	•	No sector/state mismatches

✅ Gate 7 — Reproducibility
	•	Training job recreates identical output within tolerance

⸻

6. Agent Tooling & Permissions Matrix

Agent
Tools
Auto-Merge?
Human Review Needed?
Planner
Read, propose
No
Yes
Data Eng
ETL pipelines
Yes (safe)
If schema changes
Seasonal/Stats
X-13
Yes
For regressor changes
Feature Agent
Feature store
Yes
For new features
Model Trainer
ML pipelines
No
Always
Nowcast
Inference only
Yes
No
MinT Agent
Reconciliation
Yes
If structure changes
Revision Agent
Revision models
No
Yes
Evaluator
CI gates
Yes
No
Explainer
Docs only
Yes
No
Ops/SRE
Infra
Yes
If infra changes


7. Core Four Signals Priority

Agents must prioritize these four foundational signals:
	1.	UI Claims (Initial & Continuing)
	2.	Daily Treasury Withholdings
	3.	CES/LAUS with proper X-13 seasonal adjustment
	4.	One payroll microdata source (optional but increases accuracy)

These are the strongest short-run predictors of NFP and revisions.

⸻

8. System Safety Features
	•	Strict one-way artifact flow (Zone 1 → Zone 2)
	•	Immutable historical data (vintages)
	•	Deterministic training runs
	•	Regressors updated only by Stats Agent
	•	SN41 submissions signed & logged
	•	Human review on all architecture changes

⸻

9. Phase Plan & Cost Bands

Phase 1 — Public Data Only
	•	Can run locally
	•	~$0/month baseline

Phase 2 — Add Private Payroll/Postings (optional)
	•	Requires credentialing
	•	+$30–$200/mo depending on provider

Phase 3 — Cloud Training
	•	Hourly GPU (optional, pay-per-use)
	•	No monthly commitment needed

Phase 4 — SN41 Deployment
	•	Lightweight
	•	<$10/mo server or even local inference

⸻

✅ Summary

This document defines:
	•	The full AI agent ecosystem
	•	Self-maintenance protocols
	•	Accuracy safety gates
	•	Two-zone architecture
	•	Autonomy levels
	•	Enforcement of elite model accuracy
	•	SN41 operational readiness

You now have the complete operational layer required to build, maintain, monitor, and continuously self-improve a top-1% labor forecasting system.

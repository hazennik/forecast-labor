# Forecast-Labor Documentation

Complete documentation for the Real-Time U.S. Labor-Market Forecasting Engine + SN41 Miner.

---

## 📚 Core Documentation

### Architecture & Principles
- **[5_PILLARS.md](./5_PILLARS.md)** - Five architectural principles for elite forecasting accuracy
- **[PROJECT_INSTRUCTIONS.md](./PROJECT_INSTRUCTIONS.md)** - Complete build specification and requirements
- **[FORECASTING_CAPABILITIES.md](./FORECASTING_CAPABILITIES.md)** - Everything the system predicts

### Accuracy & Performance
- **[ACCURACY_MAP.md](./ACCURACY_MAP.md)** - Target accuracy ranges by data type and horizon
- **[ACCURACY_DESCRIPTION.md](./ACCURACY_DESCRIPTION.md)** - Why accuracy ceilings exist and how to reach them

### Operations & Agents
- **[AGENTS_AND_OPS_RUNBOOK.md](./AGENTS_AND_OPS_RUNBOOK.md)** - AI agents roster, autonomy levels, and operational gates
- **[ops/RUNBOOK.md](./ops/RUNBOOK.md)** - Phase 6A API deployment, smoke checks, observability, and rollback
- **[ops/DEPLOY_GATES.md](./ops/DEPLOY_GATES.md)** - Phase 6A model, artifact, API, and rollback deployment gates

---

## 📋 Planning & Progress

Located in [`planning/`](./planning/)

### Project Management
- **[IMPLEMENTATION_STATUS.md](./planning/IMPLEMENTATION_STATUS.md)** - Current status across all phases
- **[REPO_SCAFFOLDING.md](./planning/REPO_SCAFFOLDING.md)** - Complete repository structure and organization
- **[QUICK_PLAN.md](./planning/QUICK_PLAN.md)** - High-level development roadmap

### Phase Completions
- **[PHASE_2_COMPLETE.md](./planning/PHASE_2_COMPLETE.md)** - Data pipelines complete (7/7 sources)
- **[PHASE_3_PROGRESS.md](./planning/PHASE_3_PROGRESS.md)** - Progress tracking for validation & seasonal adjustment
- **[PHASE_3_COMPLETE.md](./planning/PHASE_3_COMPLETE.md)** - Validation & seasonal adjustment complete

### Development Notes
- **[SESSION_SUMMARY.md](./planning/SESSION_SUMMARY.md)** - Detailed development session notes
- **[IDE_AGENT_OUTLINE.md](./planning/IDE_AGENT_OUTLINE.md)** - AI agent implementation details
- **[EXTRA_PROJECT_NOISE.md](./planning/EXTRA_PROJECT_NOISE.md)** - Working notes and scratch space

---

## 🏗️ Architecture

Located in [`arch/`](./arch/) _(to be created)_

Will contain:
- Architecture diagrams (SVG/PNG)
- Two-zone architecture documentation
- Data flow diagrams
- Component interactions

---

## 🚀 Operations

Located in [`ops/`](./ops/)

Will contain:
- **DEPLOY_GATES.md** - CI/CD gates (sMAPE, coverage, coherence, artifact, and API thresholds)
- **RUNBOOK.md** - Phase 6A API deployment, smoke checks, incident response, and rollback
- Production deployment guides
- Monitoring and alerting setup

---

## 📊 Current Project Status

**Current Phase:** Phase 7 in progress  
**Overall Progress:** See [`IMPLEMENTATION_STATUS.md`](./planning/IMPLEMENTATION_STATUS.md) for the current source of truth.

### ✅ Completed Phases
- **Phase 1:** Foundation (100%)
  - Docker infrastructure
  - Database schemas
  - Base ETL framework

- **Phase 2:** Data Pipelines (100%)
  - UI Claims (weekly unemployment)
  - Treasury Withholdings (daily payroll proxy)
  - BLS CES (monthly NFP - primary target)
  - BLS LAUS (state employment)
  - Work Stoppages (strikes)
  - NOAA Weather (disruptions)
  - Census Business Formation Statistics

- **Phase 3:** Validation & Seasonal Adjustment (100%)
  - Complete validation framework
  - X-13ARIMA-SEATS integration
  - Intelligent regressors (holidays, strikes, weather)
  - Diagnostics and quality gates

- **Phase 4:** Feature Engineering (100%)
  - MIDAS lag constructors and mixed-frequency transformations
  - Pay-period alignment
  - State/sector aggregations

- **Phase 5:** Core Models and Post-Phase-6 Documentation Refresh (100%)
  - MIDAS, XGBoost, and LightGBM production candidates
  - DFM retained as diagnostic/research until pre-release gates pass
  - Calibration, revision forecasting, and MinT reconciliation support

- **Phase 6:** Backtesting, Reporting, Quality Gates, and Infrastructure (100%)
  - Vintage-honest backtesting and report generation
  - Model selection and accuracy gates
  - Scenario testing and feature lineage
  - X-13 CI service integration

- **Phase 6A:** API & Two-Zone Architecture (100%)
  - FastAPI forecast/status/artifact surface
  - Signed-artifact inference boundary
  - Zone 2 isolation checks, rate limiting, metrics, and request IDs
  - API deployment profile, runbook, and deployment gates

### 🚧 In Progress
- **Phase 7:** Subnet Integration (Adapter Pattern)
  - Base adapter interface, registry, scheduler, and scoring shim
  - Subnet configuration template
  - SN41 adapter as the first concrete implementation

### 📋 Upcoming
- **Phase 8:** AI Agents & Automation

---

## 🎯 Quick Links

### Getting Started
- [README.md](../README.md) - Project overview
- [QUICKSTART.md](../QUICKSTART.md) - Setup and first run

### For Developers
- [IMPLEMENTATION_STATUS.md](./planning/IMPLEMENTATION_STATUS.md) - What's done, what's next
- [REPO_SCAFFOLDING.md](./planning/REPO_SCAFFOLDING.md) - Where everything goes
- [PROJECT_INSTRUCTIONS.md](./PROJECT_INSTRUCTIONS.md) - Build requirements

### For Data Scientists
- [FORECASTING_CAPABILITIES.md](./FORECASTING_CAPABILITIES.md) - What we predict
- [ACCURACY_MAP.md](./ACCURACY_MAP.md) - Target accuracies
- [5_PILLARS.md](./5_PILLARS.md) - Design principles

### For Operations
- [AGENTS_AND_OPS_RUNBOOK.md](./AGENTS_AND_OPS_RUNBOOK.md) - Agent operations
- [ops/RUNBOOK.md](./ops/RUNBOOK.md) - Phase 6A API operations
- [ops/DEPLOY_GATES.md](./ops/DEPLOY_GATES.md) - Deployment gates

---

## 📝 Documentation Standards

All documentation follows these standards:
- **Markdown format** for GitHub rendering
- **Clear headings** for easy navigation
- **Code examples** where applicable
- **Status indicators** (✅ Complete, 🚧 In Progress, 📋 Planned)
- **Last updated dates** on planning documents

---

## 🔄 Keeping Documentation Updated

Documentation is updated:
- After each phase completion
- When major features are added
- When architecture changes occur
- During code reviews

See [IMPLEMENTATION_STATUS.md](./planning/IMPLEMENTATION_STATUS.md) for real-time progress.

---

**Last Updated:** 2026-06-06  
**Project Version:** Phase 7 In Progress


# Forecasting Capabilities

This document summarizes what the forecasting system is designed to predict and what is currently validated after the Phase 6 backtesting, model-selection, scenario, lineage, performance, and quality-gate work.

The important current boundary is this: the production candidate set is **MIDAS + XGBoost + LightGBM**, with calibration, revision forecasting, feature lineage, scenario testing, and MinT reconciliation available around those models. `DynamicFactorModel` is stable on real CES vintages, but it remains research/diagnostic only until true pre-release public signals pass vintage-honest accuracy gates.

## Current Validation Snapshot

- Production candidate models: `MIDAS`, `XGBoostQuantile`, and `LightGBMQuantile`.
- Diagnostic/research model: `DynamicFactorModel`.
- Excluded for production now: DFM, because corrected pre-release CES-only validation missed the deployment accuracy gate.
- Runtime readiness: full deterministic production candidate pipeline baseline is `0.565893s` training and `0.029653s` prediction on the Phase 6 fixture.
- Accuracy readiness: model promotion remains gated by vintage-honest sMAPE/RMSE, interval coverage, ECE, probability coherence, revision quality, reconciliation coherence, and forecast stability.

---

## 1. Primary Production Forecasts

### 1.1 Nonfarm Payrolls (NFP) First Release

This remains the core target. The current production candidate workflow can support:

- Month-over-month NFP job growth forecasts.
- Prediction intervals from quantile and conformal calibration layers.
- Probability vectors for subnet payloads once a subnet adapter defines the required bins.
- Vintage-aware training and evaluation so forecasts use only data available at the forecast date.

Current status: implemented model infrastructure and gates are ready, but promotion still depends on passing vintage-honest accuracy gates for a candidate bundle.

### 1.2 Private Payrolls, Sector Payrolls, and Related CES Targets

The pipeline can represent private-payroll and sector-level targets through CES source features, sector aggregations, and hierarchical reconciliation. These targets are useful both as direct forecasts and as supporting signals for top-line NFP.

Current status: feature and model infrastructure exists; production use requires target-specific backtests and gate reports.

### 1.3 Unemployment, Participation, and Wage Indicators

The system is designed to ingest and model labor-market indicators such as unemployment direction, labor force participation, and wage growth. These are secondary targets and supporting features rather than the current production-selection focus.

Current status: supported by the broader architecture, but not the primary validated Phase 6 production path.

## 2. High-Frequency Nowcasts

The mixed-frequency stack can align daily, weekly, and monthly inputs into monthly forecast features through `MIDASBridge` and `MixedFrequencyPipeline`.

Supported signal types include:

- Initial and continuing unemployment claims.
- Treasury withholding momentum.
- Business formation signals.
- Strike and weather controls.
- Prior-release CES information.
- Other public or private signals that are registered with release timing and vintage metadata.

Current status: the bridge and pipeline infrastructure are implemented. Automated daily/weekly triggering remains future Nowcast Agent scope, and production promotion requires vintage-honest validation with true pre-release signal availability.

## 3. Probabilistic Forecasts and Calibration

The model stack supports probability-aware forecasting rather than point forecasts only.

Implemented capabilities:

- Quantile outputs from XGBoost and LightGBM models.
- Split conformal prediction intervals.
- Isotonic probability calibration.
- Coverage and ECE validation.
- Probability coherence checks for subnet payloads.

Promotion gates:

- 90% interval coverage should remain within the accepted 85%-95% range.
- ECE should remain at or below the calibration threshold when event outcomes are available.
- Probability vectors must sum to one within tolerance.
- Probability histories should avoid unstable month-to-month swings.

## 4. Revision Forecasts

The revision model supports first-to-later-print adjustment workflows after an initial BLS release is available.

Implemented capabilities:

- Revision magnitude forecasting.
- Revision direction support.
- Separate revision MAE and direction-accuracy gates.

Promotion gates:

- Revision MAE must remain within the configured threshold.
- Revision direction accuracy must pass the configured lower bound.
- Revision results should be evaluated separately from pre-release nowcast accuracy.

## 5. Hierarchical and Coherent Forecasts

The reconciliation layer can enforce coherence across related forecast levels, such as state-to-national or sector-to-total outputs.

Implemented capabilities:

- OLS reconciliation.
- WLS reconciliation.
- Sample MinT reconciliation.
- Shrinkage MinT reconciliation.
- Mathematical property tests for coherence and method differentiation.

Promotion gates:

- Reconciliation error must stay within the coherence threshold.
- Reconciliation must not materially degrade base forecast accuracy.
- Hierarchical outputs must preserve documented lineage from source features to model artifact.

## 6. Scenario and Shock Testing

The Phase 6 scenario framework supports deterministic stress tests for forecast behavior under special events.

Implemented scenario coverage:

- Storm or hurricane disruption.
- Large transport or labor strike.
- Policy uncertainty shock.
- Neutral scenarios that should not materially move the forecast.

The scenario system validates whether shocked features move forecasts in expected directions and whether magnitudes remain plausible.

## 7. Feature Registry and Lineage

The feature registry supports production metadata needed for reproducible forecasts and auditability.

Implemented capabilities:

- PostgreSQL-backed feature metadata.
- Feature versioning and rollback support.
- Feature lineage tracking.
- Model artifact to feature registry validation.
- Vintage-date checks between model artifacts and feature metadata.
- Rollback impact analysis.

These capabilities reduce the risk of training on stale, missing, unregistered, or incorrectly versioned features.

## 8. Dynamic Factor Model Boundary

`DynamicFactorModel` is implemented and numerically stable with the statsmodels-backed refactor. It remains valuable for diagnostics and research.

Current production decision:

- DFM is excluded from the production ensemble.
- Phase 6.3.1a corrected validation showed stable predictions but poor pre-release CES-only accuracy.
- DFM should not receive production ensemble weight until true pre-release public signals are integrated and vintage-honest gates pass.

What must change before DFM can be promoted:

- Add true pre-release public mixed-frequency inputs to the validation harness.
- Re-run vintage-honest point accuracy, interval coverage, calibration, and stability gates.
- Tune interval calibration only after point forecasts pass the deployment accuracy gate.

## 9. Subnet Readiness

The forecasting stack is designed to support subnet payloads through the adapter pattern rather than hardcoded subnet logic.

Current readiness:

- Forecast and calibration layers can produce probability-ready outputs.
- Selection gates include probability coherence and stability checks.
- SN41-specific payload construction remains future adapter-phase work.

The subnet adapter phase should use the validated production candidate bundle rather than reintroducing model-selection logic inside subnet code.

## Summary

Current production candidates:

- MIDAS for interpretable mixed-frequency nowcasting.
- XGBoost for nonlinear public-signal interactions and quantile outputs.
- LightGBM for nonlinear public-signal interactions and quantile outputs.

Validated support systems:

- Calibration.
- Revision forecasting.
- MinT reconciliation.
- Scenario testing.
- Feature registry lineage.
- Performance baselines.
- Accuracy and deployment gates.

Conditional or future capabilities:

- DFM production ensemble inclusion.
- Automated intramonth nowcast triggering.
- SN41 payload submission through the subnet adapter.
- Secondary target production promotion for unemployment, wages, state forecasts, and sector forecasts.

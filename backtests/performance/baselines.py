"""Real-model performance baseline measurement for Phase 6 backtesting.

The benchmark intentionally uses deterministic, backtest-sized synthetic data so
it can run in CI without live API calls or mutable vintage writes. It measures
the actual Phase 5 model classes rather than mock forecasters, giving the
performance regression fixture meaningful model-specific values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, Mapping, Optional, Tuple
import json
import os

import numpy as np
import pandas as pd
from loguru import logger

from models_src.dfm.dfm_model import DynamicFactorModel
from models_src.gbm_quantile.lgb_quantile import LightGBMQuantile
from models_src.gbm_quantile.xgb_quantile import XGBoostQuantile
from models_src.midas.midas_model import MIDASRegression
from models_src.revision.revision_model import RevisionForecaster


DEFAULT_BASELINE_PATH = Path("tests/fixtures/performance_baselines.json")
MODEL_NAMES = ("dfm", "midas", "xgboost", "lightgbm", "revision")


@dataclass(frozen=True)
class BenchmarkConfig:
    """Configuration for deterministic real-model performance measurements."""

    n_samples: int = 72
    n_features: int = 8
    test_size: int = 12
    random_state: int = 42
    vintage_date: str = "2025-11-29"
    xgb_estimators: int = 10
    lgb_estimators: int = 10
    dfm_max_iter: int = 10

    def __post_init__(self) -> None:
        """Validate benchmark dimensions."""
        if self.n_samples <= self.test_size:
            raise ValueError("n_samples must be larger than test_size")
        if self.n_features <= 0:
            raise ValueError("n_features must be positive")
        if self.test_size <= 0:
            raise ValueError("test_size must be positive")
        if self.xgb_estimators <= 0 or self.lgb_estimators <= 0:
            raise ValueError("GBM estimator counts must be positive")
        if self.dfm_max_iter <= 0:
            raise ValueError("dfm_max_iter must be positive")


@dataclass(frozen=True)
class ModelPerformanceResult:
    """Measured training, prediction, memory, and throughput baseline."""

    training_time_sec: float
    prediction_time_sec: float
    memory_mb: float
    throughput_pred_per_sec: float
    n_train_samples: int
    n_test_samples: int
    n_features: int


def generate_benchmark_dataset(config: BenchmarkConfig) -> Tuple[pd.DataFrame, pd.Series]:
    """Generate deterministic macro-shaped data for real model benchmarking.

    Args:
        config: Benchmark configuration controlling shape and seed.

    Returns:
        Feature matrix and target series with a monthly DatetimeIndex.
    """
    rng = np.random.default_rng(config.random_state)
    dates = pd.date_range("2018-01-01", periods=config.n_samples, freq="MS")

    common_factor = rng.normal(0.0, 1.0, size=config.n_samples).cumsum()
    cycle = np.sin(np.linspace(0.0, 6.0 * np.pi, config.n_samples))
    noise = rng.normal(0.0, 0.35, size=(config.n_samples, config.n_features))

    features = {}
    for feature_idx in range(config.n_features):
        loading = 0.25 + feature_idx / (config.n_features * 4.0)
        features[f"feature_{feature_idx}"] = (
            loading * common_factor + (1.0 - loading / 2.0) * cycle + noise[:, feature_idx]
        )

    X = pd.DataFrame(features, index=dates)
    coefficients = np.linspace(6.0, 1.5, config.n_features)
    y_values = 150.0 + X.to_numpy() @ coefficients + rng.normal(0.0, 5.0, config.n_samples)
    y = pd.Series(y_values, index=dates, name="nfp_change")
    return X, y


def measure_real_model_baselines(
    config: Optional[BenchmarkConfig] = None,
) -> Dict[str, Any]:
    """Measure performance baselines for implemented real model classes.

    Args:
        config: Optional benchmark configuration.

    Returns:
        JSON-serializable baseline payload for ``real_models``.
    """
    benchmark_config = config or BenchmarkConfig()
    X, y = generate_benchmark_dataset(benchmark_config)
    split_idx = benchmark_config.n_samples - benchmark_config.test_size
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]

    model_factories: Mapping[str, Callable[[], Any]] = {
        "dfm": lambda: DynamicFactorModel(
            n_factors=1,
            max_iter=benchmark_config.dfm_max_iter,
            tol=1e-3,
            random_state=benchmark_config.random_state,
        ),
        "midas": lambda: MIDASRegression(
            n_lags=benchmark_config.n_features,
            almon_degree=1,
            optimization_method="L-BFGS-B",
            random_state=benchmark_config.random_state,
        ),
        "xgboost": lambda: XGBoostQuantile(
            quantiles=[0.1, 0.5, 0.9],
            n_estimators=benchmark_config.xgb_estimators,
            max_depth=2,
            learning_rate=0.05,
            random_state=benchmark_config.random_state,
        ),
        "lightgbm": lambda: LightGBMQuantile(
            quantiles=[0.1, 0.5, 0.9],
            n_estimators=benchmark_config.lgb_estimators,
            max_depth=2,
            num_leaves=7,
            learning_rate=0.05,
            random_state=benchmark_config.random_state,
        ),
        "revision": lambda: RevisionForecaster(
            alpha=1.0, random_state=benchmark_config.random_state
        ),
    }

    measured: Dict[str, Any] = {}
    for model_name in MODEL_NAMES:
        logger.info("measuring_model_performance", model=model_name)
        result = _measure_single_model(
            model_factory=model_factories[model_name],
            X_train=X_train,
            y_train=y_train,
            X_test=X_test,
            vintage_date=benchmark_config.vintage_date,
        )
        measured[model_name] = asdict(result)

    measured["dfm"].update(
        {
            "production_inclusion": False,
            "validation_note": (
                "Stable on Phase 6.3.1a real CES vintages but excluded until true "
                "pre-release public signals pass accuracy gates"
            ),
            "phase_6_3_1a_stability_rate": 1.0,
            "phase_6_3_1a_smape": 103.61,
        }
    )
    measured["full_pipeline"] = _build_full_pipeline_baseline(measured)
    measured["_measurement"] = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_type": "deterministic_real_model_classes",
        "n_samples": benchmark_config.n_samples,
        "n_features": benchmark_config.n_features,
        "test_size": benchmark_config.test_size,
        "random_state": benchmark_config.random_state,
        "vintage_date": benchmark_config.vintage_date,
    }
    return measured


def update_performance_baseline_file(
    baseline_path: Path = DEFAULT_BASELINE_PATH,
    config: Optional[BenchmarkConfig] = None,
) -> Dict[str, Any]:
    """Measure real model baselines and persist them into the fixture file.

    Args:
        baseline_path: JSON fixture path to update.
        config: Optional benchmark configuration.

    Returns:
        Updated JSON payload.
    """
    baseline_path = Path(baseline_path)
    with baseline_path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    payload["real_models"] = measure_real_model_baselines(config)
    payload["_updated"] = datetime.now(timezone.utc).isoformat()
    payload["_phase"] = "6.3.1b"
    payload["_purpose"] = "Track real model performance over time to detect regressions"

    with baseline_path.open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, indent=2)
        file_obj.write("\n")

    logger.info("performance_baseline_file_updated", path=str(baseline_path))
    return payload


def _measure_single_model(
    model_factory: Callable[[], Any],
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    vintage_date: str,
) -> ModelPerformanceResult:
    """Measure a single model's training, prediction, and memory profile."""
    memory_before = _resident_memory_mb()
    model = model_factory()

    train_start = perf_counter()
    model.fit(X_train, y_train, vintage_date=vintage_date)
    training_time = perf_counter() - train_start

    predict_start = perf_counter()
    _ = model.predict(X_test)
    prediction_time = perf_counter() - predict_start

    memory_after = _resident_memory_mb()
    memory_used = max(0.001, memory_after - memory_before)
    throughput = len(X_test) / prediction_time if prediction_time > 0 else float("inf")

    return ModelPerformanceResult(
        training_time_sec=round(training_time, 6),
        prediction_time_sec=round(prediction_time, 6),
        memory_mb=round(memory_used, 3),
        throughput_pred_per_sec=round(float(throughput), 3),
        n_train_samples=len(X_train),
        n_test_samples=len(X_test),
        n_features=X_train.shape[1],
    )


def _resident_memory_mb() -> float:
    """Return current process resident memory in MB."""
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except ImportError:
        logger.warning("psutil_unavailable_for_memory_measurement")
        return 0.0


def _build_full_pipeline_baseline(real_models: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate candidate model measurements into a full-pipeline baseline."""
    candidate_names = ("midas", "xgboost", "lightgbm", "revision")
    training_time = sum(float(real_models[name]["training_time_sec"]) for name in candidate_names)
    prediction_time = sum(
        float(real_models[name]["prediction_time_sec"]) for name in candidate_names
    )
    memory_mb = sum(float(real_models[name]["memory_mb"]) for name in candidate_names)
    n_test_samples = int(real_models["midas"]["n_test_samples"])
    throughput = n_test_samples / prediction_time if prediction_time > 0 else float("inf")
    return {
        "training_time_sec": round(training_time, 6),
        "prediction_time_sec": round(prediction_time, 6),
        "memory_mb": round(memory_mb, 3),
        "throughput_pred_per_sec": round(float(throughput), 3),
        "included_models": list(candidate_names),
        "excluded_models": ["dfm"],
        "exclusion_reason": "DFM diagnostic-only until pre-release public-signal accuracy gate passes",
    }

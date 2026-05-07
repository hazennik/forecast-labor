"""Tests for Phase 6.3.1b real-model performance baseline measurement."""

from pathlib import Path
from typing import Any
import importlib
import json
import sys

import numpy as np
import pytest

def _performance_module() -> Any:
    """Import production backtest performance utilities after test collection."""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) in sys.path:
        sys.path.remove(str(project_root))
    sys.path.insert(0, str(project_root))
    sys.modules.pop("backtests", None)
    return importlib.import_module("backtests.performance")


class TestBenchmarkDataset:
    """Validate deterministic benchmark data construction."""

    def test_dataset_is_deterministic_for_same_seed(self):
        """Same config must produce identical benchmark data."""
        performance = _performance_module()
        config = performance.BenchmarkConfig(
            n_samples=36, n_features=4, test_size=6, random_state=123
        )
        X_first, y_first = performance.generate_benchmark_dataset(config)
        X_second, y_second = performance.generate_benchmark_dataset(config)

        assert X_first.equals(X_second)
        assert y_first.equals(y_second)

    def test_dataset_changes_with_seed(self):
        """Different seeds should produce distinct workloads."""
        performance = _performance_module()
        first_config = performance.BenchmarkConfig(
            n_samples=36, n_features=4, test_size=6, random_state=123
        )
        second_config = performance.BenchmarkConfig(
            n_samples=36, n_features=4, test_size=6, random_state=456
        )

        X_first, y_first = performance.generate_benchmark_dataset(first_config)
        X_second, y_second = performance.generate_benchmark_dataset(second_config)

        assert not np.allclose(X_first.to_numpy(), X_second.to_numpy())
        assert not np.allclose(y_first.to_numpy(), y_second.to_numpy())

    def test_config_validates_dimensions(self):
        """Invalid benchmark shapes should fail early."""
        performance = _performance_module()
        with pytest.raises(ValueError, match="n_samples must be larger"):
            performance.BenchmarkConfig(n_samples=12, test_size=12)

        with pytest.raises(ValueError, match="n_features must be positive"):
            performance.BenchmarkConfig(n_features=0)


class TestRealModelBaselines:
    """Validate real model baseline measurement structure."""

    @pytest.mark.performance
    def test_measure_real_model_baselines_has_required_models(self):
        """Baseline measurement should cover all Phase 5 real model classes."""
        performance = _performance_module()
        config = performance.BenchmarkConfig(
            n_samples=36,
            n_features=4,
            test_size=6,
            xgb_estimators=2,
            lgb_estimators=2,
            dfm_max_iter=2,
        )

        baselines = performance.measure_real_model_baselines(config)

        for model_name in ("dfm", "midas", "xgboost", "lightgbm", "revision"):
            assert model_name in baselines
            assert baselines[model_name]["training_time_sec"] > 0
            assert baselines[model_name]["prediction_time_sec"] >= 0
            assert baselines[model_name]["memory_mb"] > 0
            assert baselines[model_name]["throughput_pred_per_sec"] > 0
            assert baselines[model_name]["n_train_samples"] == 30
            assert baselines[model_name]["n_test_samples"] == 6
            assert baselines[model_name]["n_features"] == 4

        assert baselines["dfm"]["production_inclusion"] is False
        assert "full_pipeline" in baselines
        assert baselines["full_pipeline"]["excluded_models"] == ["dfm"]
        assert baselines["_measurement"]["benchmark_type"] == "deterministic_real_model_classes"

    @pytest.mark.performance
    def test_update_performance_baseline_file_preserves_top_level_structure(self, tmp_path):
        """Writing baselines should update real_models without dropping SLA metadata."""
        performance = _performance_module()
        baseline_file = tmp_path / "performance_baselines.json"
        baseline_file.write_text(
            json.dumps(
                {
                    "_comment": "Performance baselines for regression detection",
                    "_created": "2025-11-24",
                    "_tolerance_pct": 20,
                    "_purpose": "Track performance over time to detect regressions",
                    "mock_model": {
                        "training_time_sec": 1.0,
                        "prediction_time_sec": 0.1,
                        "memory_mb": 500,
                        "throughput_pred_per_sec": 10,
                    },
                    "real_models": {},
                    "slas": {
                        "full_pipeline_max_minutes": 30,
                        "prediction_latency_max_ms": 1000,
                        "memory_limit_mb": 4096,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        config = performance.BenchmarkConfig(
            n_samples=36,
            n_features=4,
            test_size=6,
            xgb_estimators=2,
            lgb_estimators=2,
            dfm_max_iter=2,
        )
        updated = performance.update_performance_baseline_file(Path(baseline_file), config)

        assert updated["_phase"] == "6.3.1b"
        assert updated["mock_model"]["training_time_sec"] == 1.0
        assert updated["slas"]["full_pipeline_max_minutes"] == 30
        assert updated["real_models"]["full_pipeline"]["training_time_sec"] > 0

        reloaded = json.loads(baseline_file.read_text(encoding="utf-8"))
        assert reloaded == updated

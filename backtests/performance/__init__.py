"""Performance utilities for Phase 6 backtesting.

The benchmark module imports model implementations and their heavier numerical
dependencies. Keep package exports lazy so validation-only tools can run without
loading the full model stack.
"""

from typing import Any

__all__ = [
    "BenchmarkConfig",
    "ComponentProfile",
    "ModelPerformanceResult",
    "PerformanceFinding",
    "PerformanceSeverity",
    "PerformanceSLA",
    "PerformanceValidationReport",
    "generate_benchmark_dataset",
    "load_performance_baseline",
    "measure_real_model_baselines",
    "update_performance_baseline_file",
    "validate_performance_baseline",
    "validate_performance_baseline_file",
]

_BASELINE_EXPORTS = {
    "BenchmarkConfig",
    "ModelPerformanceResult",
    "generate_benchmark_dataset",
    "measure_real_model_baselines",
    "update_performance_baseline_file",
}

_VALIDATION_EXPORTS = {
    "ComponentProfile",
    "PerformanceFinding",
    "PerformanceSeverity",
    "PerformanceSLA",
    "PerformanceValidationReport",
    "load_performance_baseline",
    "validate_performance_baseline",
    "validate_performance_baseline_file",
}


def __getattr__(name: str) -> Any:
    """Lazily load performance utilities."""
    if name in _BASELINE_EXPORTS:
        from backtests.performance import baselines

        return getattr(baselines, name)
    if name in _VALIDATION_EXPORTS:
        from backtests.performance import validation

        return getattr(validation, name)
    raise AttributeError(f"module 'backtests.performance' has no attribute {name!r}")

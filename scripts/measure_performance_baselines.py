#!/usr/bin/env python3
"""Measure Phase 6.3.1b real-model performance baselines."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json

from backtests.performance import BenchmarkConfig, measure_real_model_baselines
from backtests.performance.baselines import DEFAULT_BASELINE_PATH, update_performance_baseline_file


def parse_args() -> ArgumentParser:
    """Build the command-line parser."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--write", action="store_true", help="Persist measurements to the output file")
    parser.add_argument("--n-samples", type=int, default=72)
    parser.add_argument("--n-features", type=int, default=8)
    parser.add_argument("--test-size", type=int, default=12)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--vintage-date", type=str, default="2025-11-29")
    parser.add_argument("--xgb-estimators", type=int, default=10)
    parser.add_argument("--lgb-estimators", type=int, default=10)
    parser.add_argument("--dfm-max-iter", type=int, default=10)
    return parser


def main() -> None:
    """Measure and optionally write real model performance baselines."""
    args = parse_args().parse_args()
    config = BenchmarkConfig(
        n_samples=args.n_samples,
        n_features=args.n_features,
        test_size=args.test_size,
        random_state=args.random_state,
        vintage_date=args.vintage_date,
        xgb_estimators=args.xgb_estimators,
        lgb_estimators=args.lgb_estimators,
        dfm_max_iter=args.dfm_max_iter,
    )

    if args.write:
        payload = update_performance_baseline_file(args.output, config)
        print(json.dumps(payload["real_models"], indent=2))
        return

    measurements = measure_real_model_baselines(config)
    print(json.dumps(measurements, indent=2))


if __name__ == "__main__":
    main()

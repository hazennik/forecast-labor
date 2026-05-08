#!/usr/bin/env python3
"""Validate Phase 6 performance baselines against production SLA gates."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtests.performance.validation import (
    DEFAULT_BASELINE_PATH,
    validate_performance_baseline_file,
)


def parse_args() -> ArgumentParser:
    """Build CLI parser."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    """Run performance validation and exit non-zero on critical SLA failures."""
    args = parse_args().parse_args()
    report = validate_performance_baseline_file(args.baseline, report_path=args.report)
    print(json.dumps(report.to_dict(), indent=2))
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()

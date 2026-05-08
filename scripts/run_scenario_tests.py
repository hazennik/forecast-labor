#!/usr/bin/env python3
"""Run Phase 6.4.3 scenario tests from a JSON payload."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtests.scenarios import evaluate_scenario_file


def parse_args() -> ArgumentParser:
    """Build CLI parser."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON scenario payload")
    parser.add_argument("--report", type=Path, default=None, help="Optional JSON report path")
    return parser


def main() -> None:
    """Run scenario validation and exit non-zero on critical failures."""
    args = parse_args().parse_args()
    report = evaluate_scenario_file(args.input, report_path=args.report)
    print(json.dumps(report.to_dict(), indent=2))
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()

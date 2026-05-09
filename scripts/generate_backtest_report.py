#!/usr/bin/env python3
"""Generate Phase 6 backtest summary reports."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtests.performance.validation import validate_performance_baseline_file
from backtests.reports import BacktestReportGenerator


def parse_args() -> ArgumentParser:
    """Build CLI parser."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--performance-baseline",
        type=Path,
        default=Path("tests/fixtures/performance_baselines.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports"))
    parser.add_argument("--stem", type=str, default="phase_6_backtest_report")
    parser.add_argument("--title", type=str, default="Phase 6 Backtest Report")
    parser.add_argument(
        "--metadata", type=str, default="{}", help="JSON object with report metadata"
    )
    return parser


def main() -> None:
    """Generate and write the report."""
    args = parse_args().parse_args()
    metadata = json.loads(args.metadata)
    if not isinstance(metadata, dict):
        raise ValueError("--metadata must decode to a JSON object")

    performance_report = validate_performance_baseline_file(args.performance_baseline).to_dict()
    report = BacktestReportGenerator().generate(
        title=args.title,
        performance_report=performance_report,
        metadata=metadata,
    )
    paths = BacktestReportGenerator().write(report, args.output_dir, stem=args.stem)
    sys.stdout.write(json.dumps({key: str(path) for key, path in paths.items()}, indent=2) + "\n")


if __name__ == "__main__":
    main()

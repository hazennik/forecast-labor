#!/usr/bin/env python3
"""Validate Phase 6.4.4 feature registry lineage payloads."""

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtests.lineage import validate_feature_lineage_file


def parse_args() -> ArgumentParser:
    """Build CLI parser."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSON lineage payload")
    parser.add_argument("--report", type=Path, default=None, help="Optional JSON report path")
    return parser


def main() -> None:
    """Run lineage validation and exit non-zero on critical failures."""
    args = parse_args().parse_args()
    report = validate_feature_lineage_file(args.input, report_path=args.report)
    print(json.dumps(report.to_dict(), indent=2))
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()

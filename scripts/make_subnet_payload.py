#!/usr/bin/env python3
"""Build and validate subnet submission payloads for the active adapter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subnets import create_default_registry
from subnets.config import DEFAULT_CONFIG_DIR


def parse_args() -> argparse.Namespace:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="JSON file containing event probability predictions",
    )
    parser.add_argument(
        "--subnet",
        default=None,
        help="Subnet ID (defaults to ACTIVE_SUBNET environment variable)",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="Directory containing subnet YAML configs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path for the payload bytes",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Build the payload and validate it without writing output",
    )
    return parser.parse_args()


def load_predictions(path: Path) -> Mapping[str, Any]:
    """Load predictions JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """Build a subnet payload and optionally write it to disk."""
    args = parse_args()
    registry = create_default_registry(config_dir=args.config_dir)
    subnet_id = (args.subnet or "").strip()
    adapter = registry.get_adapter(subnet_id) if subnet_id else registry.get_active_adapter()

    predictions = load_predictions(args.predictions)
    payload = adapter.build_payload(predictions)
    if not adapter.validate_payload(payload):
        raise SystemExit("Payload validation failed")

    if args.validate_only:
        print(
            json.dumps(
                {
                    "subnet_id": adapter.subnet_id,
                    "payload_bytes": len(payload),
                    "valid": True,
                },
                indent=2,
            )
        )
        return

    if args.output is None:
        sys.stdout.buffer.write(payload)
        return

    args.output.write_bytes(payload)
    print(
        json.dumps(
            {
                "subnet_id": adapter.subnet_id,
                "output": str(args.output),
                "payload_bytes": len(payload),
                "valid": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

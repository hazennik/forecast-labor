#!/usr/bin/env python3
"""Submit a validated subnet payload through the active adapter."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from subnets import create_default_registry
from subnets.base_adapter import SubmissionKeyPaths
from subnets.config import DEFAULT_CONFIG_DIR
from subnets.scheduler import SubnetScheduler


def parse_args() -> argparse.Namespace:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="Optional JSON predictions file used to build a payload",
    )
    parser.add_argument(
        "--payload",
        type=Path,
        default=None,
        help="Optional prebuilt payload file",
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
        "--hotkey-path",
        type=Path,
        default=None,
        help="Hotkey path (defaults to HOTKEY_PATH environment variable)",
    )
    parser.add_argument(
        "--coldkey-path",
        type=Path,
        default=None,
        help="Optional coldkey path (defaults to COLDKEY_PATH environment variable)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip submission window checks",
    )
    return parser.parse_args()


def resolve_hotkey_path(explicit: Optional[Path]) -> Path:
    """Resolve hotkey path from CLI or environment."""
    if explicit is not None:
        return explicit
    env_path = os.environ.get("HOTKEY_PATH", "").strip()
    if env_path:
        return Path(env_path)
    raise SystemExit("HOTKEY_PATH is required (flag or environment variable)")


def resolve_coldkey_path(explicit: Optional[Path]) -> Optional[Path]:
    """Resolve optional coldkey path from CLI or environment."""
    if explicit is not None:
        return explicit
    env_path = os.environ.get("COLDKEY_PATH", "").strip()
    return Path(env_path) if env_path else None


def load_predictions(path: Path) -> Mapping[str, Any]:
    """Load predictions JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def submission_result_to_dict(result: Any) -> dict[str, Any]:
    """Convert a SubmissionResult dataclass to JSON-serializable output."""
    payload = asdict(result)
    payload["submitted_at"] = result.submitted_at.isoformat()
    return payload


def main() -> None:
    """Submit a subnet payload through the active adapter."""
    args = parse_args()
    if args.payload is None and args.predictions is None:
        raise SystemExit("Provide --payload or --predictions")

    registry = create_default_registry(config_dir=args.config_dir)
    subnet_id = (args.subnet or "").strip()
    adapter = registry.get_adapter(subnet_id) if subnet_id else registry.get_active_adapter()

    if not args.force:
        scheduler = SubnetScheduler([adapter])
        if not scheduler.should_submit(adapter.subnet_id):
            raise SystemExit("Submission window is closed; use --force to override")

    if args.payload is not None:
        payload = args.payload.read_bytes()
    else:
        predictions = load_predictions(args.predictions)  # type: ignore[arg-type]
        payload = adapter.build_payload(predictions)

    if not adapter.validate_payload(payload):
        raise SystemExit("Payload validation failed")

    keys = SubmissionKeyPaths(
        hotkey_path=resolve_hotkey_path(args.hotkey_path),
        coldkey_path=resolve_coldkey_path(args.coldkey_path),
    )
    result = adapter.submit(payload, keys)
    print(json.dumps(submission_result_to_dict(result), indent=2))
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()

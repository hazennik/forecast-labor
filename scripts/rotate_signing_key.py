#!/usr/bin/env python3
"""
Script to rotate model artifact signing keys.

This script helps with regular quarterly key rotation following the
procedures documented in docs/SECURITY_KEY_MANAGEMENT.md.

Usage:
    # Generate new key version
    python scripts/rotate_signing_key.py --action generate --version v3
    
    # Verify new key
    python scripts/rotate_signing_key.py --action verify --version v3
    
    # Activate new key (make it current)
    python scripts/rotate_signing_key.py --action activate --version v3
    
    # Archive old key
    python scripts/rotate_signing_key.py --action archive --version v2

Phase 5.9.2 Quality Gap Resolution
"""

import argparse
import secrets
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict

# Configuration
SECRETS_DIR = Path("data/secrets/signing_keys")
ARCHIVE_DIR = SECRETS_DIR / "archived"
REVOKED_LOG = SECRETS_DIR / "REVOKED_KEYS.txt"
ROTATION_LOG = SECRETS_DIR / "ROTATION_LOG.json"


def ensure_directories():
    """Create necessary directories if they don't exist"""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure .gitignore exists
    gitignore = SECRETS_DIR.parent / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# Signing keys must never be committed\n*.key\nREVOKED_*.txt\nROTATION_LOG.json\n"
        )
        print(f"✅ Created .gitignore: {gitignore}")


def generate_key(version: str, force: bool = False) -> Dict:
    """
    Generate a new signing key.

    Args:
        version: Key version (e.g., 'v3')
        force: Overwrite if key already exists

    Returns:
        Dictionary with key metadata
    """
    ensure_directories()

    key_file = SECRETS_DIR / f"signing_key_{version}.key"

    if key_file.exists() and not force:
        print(f"❌ Key already exists: {key_file}")
        print("   Use --force to overwrite")
        return {}

    # Generate random key material (512 bits)
    key_bytes = secrets.token_bytes(64)
    key_hex = key_bytes.hex()
    key_id = hashlib.sha256(key_bytes).hexdigest()[:16]

    # Write key to file
    key_file.write_text(key_hex)
    key_file.chmod(0o600)  # Owner read/write only

    # Log rotation event
    metadata = {
        "version": version,
        "key_id": key_id,
        "created_at": datetime.now().isoformat(),
        "file": str(key_file),
        "status": "generated",
    }

    log_rotation_event(metadata)

    print("✅ Key generated successfully")
    print(f"   Version: {version}")
    print(f"   Key ID: {key_id}")
    print(f"   File: {key_file}")
    print(f"   Permissions: {oct(key_file.stat().st_mode)[-3:]}")

    return metadata


def verify_key(version: str) -> bool:
    """
    Verify that a key exists and is valid.

    Args:
        version: Key version to verify

    Returns:
        True if key is valid
    """
    key_file = SECRETS_DIR / f"signing_key_{version}.key"

    if not key_file.exists():
        print(f"❌ Key file not found: {key_file}")
        return False

    # Check permissions
    mode = key_file.stat().st_mode
    perms = oct(mode)[-3:]

    if perms != "600":
        print(f"⚠️ Warning: Insecure permissions: {perms} (should be 600)")

    # Verify key format
    try:
        key_hex = key_file.read_text().strip()

        if len(key_hex) != 128:  # 64 bytes = 128 hex chars
            print(f"❌ Invalid key length: {len(key_hex)} (expected 128)")
            return False

        # Try to decode
        key_bytes = bytes.fromhex(key_hex)
        key_id = hashlib.sha256(key_bytes).hexdigest()[:16]

        print("✅ Key verified successfully")
        print(f"   Version: {version}")
        print(f"   Key ID: {key_id}")
        print(f"   File: {key_file}")
        print(f"   Size: {len(key_bytes)} bytes")
        print(f"   Permissions: {perms}")

        return True

    except Exception as e:
        print(f"❌ Key validation failed: {e}")
        return False


def activate_key(version: str) -> bool:
    """
    Activate a key version (make it the current signing key).

    This updates the .env file and rotation log.

    Args:
        version: Key version to activate

    Returns:
        True if activation successful
    """
    key_file = SECRETS_DIR / f"signing_key_{version}.key"

    if not key_file.exists():
        print(f"❌ Key not found: {key_file}")
        return False

    # Verify key first
    if not verify_key(version):
        print("❌ Key verification failed, cannot activate")
        return False

    # Update .env file
    env_file = Path(".env")
    env_lines = []

    if env_file.exists():
        env_lines = env_file.read_text().splitlines()

    # Update or add SIGNING_KEY_VERSION
    updated = False
    for i, line in enumerate(env_lines):
        if line.startswith("SIGNING_KEY_VERSION="):
            env_lines[i] = f"SIGNING_KEY_VERSION={version}"
            updated = True
            break

    if not updated:
        env_lines.append(f"SIGNING_KEY_VERSION={version}")

    # Write back to .env
    env_file.write_text("\n".join(env_lines) + "\n")

    # Log activation
    metadata = {"version": version, "activated_at": datetime.now().isoformat(), "status": "active"}

    log_rotation_event(metadata)

    print("✅ Key activated successfully")
    print(f"   Version: {version}")
    print(f"   Updated: {env_file}")
    print("")
    print("⚠️ Next steps:")
    print("   1. Test signing with new key")
    print("   2. Keep old key for verification during transition")
    print("   3. After all models re-signed, archive old key")

    return True


def archive_key(version: str, reason: str = "rotation") -> bool:
    """
    Archive an old key version (move to archived directory).

    Args:
        version: Key version to archive
        reason: Reason for archival (default: 'rotation')

    Returns:
        True if archival successful
    """
    key_file = SECRETS_DIR / f"signing_key_{version}.key"

    if not key_file.exists():
        print(f"❌ Key not found: {key_file}")
        return False

    # Create archive filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_file = ARCHIVE_DIR / f"signing_key_{version}_{timestamp}.key"

    # Move to archive
    key_file.rename(archive_file)

    # Log archival
    metadata = {
        "version": version,
        "archived_at": datetime.now().isoformat(),
        "reason": reason,
        "archive_file": str(archive_file),
        "status": "archived",
    }

    log_rotation_event(metadata)

    print("✅ Key archived successfully")
    print(f"   Version: {version}")
    print(f"   Archive: {archive_file}")
    print(f"   Reason: {reason}")

    return True


def log_rotation_event(metadata: Dict):
    """
    Log a key rotation event to the rotation log.

    Args:
        metadata: Event metadata to log
    """
    log = []

    if ROTATION_LOG.exists():
        log = json.loads(ROTATION_LOG.read_text())

    log.append(metadata)

    ROTATION_LOG.write_text(json.dumps(log, indent=2))


def show_status():
    """Display current key status"""
    print("=" * 70)
    print("SIGNING KEY STATUS")
    print("=" * 70)
    print()

    # Check for keys
    if not SECRETS_DIR.exists():
        print("❌ Secrets directory not found")
        return

    keys = sorted(SECRETS_DIR.glob("signing_key_*.key"))

    if not keys:
        print("⚠️ No signing keys found")
        print()
        print("Generate a new key:")
        print("  python scripts/rotate_signing_key.py --action generate --version v1")
        return

    print(f"Active Keys: ({len(keys)} found)")
    print()

    for key_file in keys:
        version = key_file.stem.replace("signing_key_", "")

        try:
            key_hex = key_file.read_text().strip()
            key_bytes = bytes.fromhex(key_hex)
            key_id = hashlib.sha256(key_bytes).hexdigest()[:16]
            perms = oct(key_file.stat().st_mode)[-3:]

            is_current = False
            env_file = Path(".env")
            if env_file.exists():
                env_content = env_file.read_text()
                if f"SIGNING_KEY_VERSION={version}" in env_content:
                    is_current = True

            status = "✅ CURRENT" if is_current else "  "

            print(f"{status} {version:8} | Key ID: {key_id} | Perms: {perms}")

        except Exception as e:
            print(f"❌ {version:8} | ERROR: {e}")

    print()

    # Show archived keys
    archived = sorted(ARCHIVE_DIR.glob("signing_key_*.key")) if ARCHIVE_DIR.exists() else []

    if archived:
        print(f"Archived Keys: ({len(archived)} found)")
        print()
        for key_file in archived:
            print(f"  📦 {key_file.name}")
        print()

    # Show rotation log
    if ROTATION_LOG.exists():
        log = json.loads(ROTATION_LOG.read_text())
        recent = log[-3:]  # Last 3 events

        print("Recent Rotation Events:")
        print()
        for event in recent:
            print(
                f"  {event.get('version', 'unknown'):8} | "
                f"{event.get('status', 'unknown'):10} | "
                f"{event.get('created_at') or event.get('activated_at') or event.get('archived_at', 'unknown')}"
            )
        print()

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Rotate model artifact signing keys",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check current status
    python scripts/rotate_signing_key.py --action status
    
    # Generate new key version
    python scripts/rotate_signing_key.py --action generate --version v3
    
    # Verify key
    python scripts/rotate_signing_key.py --action verify --version v3
    
    # Activate key (make it current)
    python scripts/rotate_signing_key.py --action activate --version v3
    
    # Archive old key
    python scripts/rotate_signing_key.py --action archive --version v2 --reason "quarterly rotation"

See docs/SECURITY_KEY_MANAGEMENT.md for full procedures.
        """,
    )

    parser.add_argument(
        "--action",
        choices=["generate", "verify", "activate", "archive", "status"],
        required=True,
        help="Action to perform",
    )

    parser.add_argument("--version", help="Key version (e.g., v3)")

    parser.add_argument(
        "--reason", default="rotation", help="Reason for archival (default: rotation)"
    )

    parser.add_argument("--force", action="store_true", help="Force overwrite if key exists")

    args = parser.parse_args()

    # Validate version provided for actions that need it
    if args.action != "status" and not args.version:
        parser.error(f"--version required for action: {args.action}")

    # Execute action
    if args.action == "status":
        show_status()

    elif args.action == "generate":
        generate_key(args.version, force=args.force)

    elif args.action == "verify":
        success = verify_key(args.version)
        exit(0 if success else 1)

    elif args.action == "activate":
        success = activate_key(args.version)
        exit(0 if success else 1)

    elif args.action == "archive":
        success = archive_key(args.version, reason=args.reason)
        exit(0 if success else 1)


if __name__ == "__main__":
    main()

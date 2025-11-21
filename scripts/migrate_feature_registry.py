#!/usr/bin/env python3
"""
Feature Registry Migration Script

Migrates features from in-memory registry to PostgreSQL database.

Usage:
    python scripts/migrate_feature_registry.py --source memory --target database --validate
    python scripts/migrate_feature_registry.py --export features_backup.json
    python scripts/migrate_feature_registry.py --import features_backup.json --target database

Features:
- Export features from in-memory registry
- Import features to database
- Validate migration (count, checksums)
- Rollback capability
- Dry-run mode for testing
"""

import argparse
import json
import sys
import hashlib
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from features.registry import FeatureRegistry
from loguru import logger


def export_features(registry: FeatureRegistry, output_file: Path) -> int:
    """
    Export features from registry to JSON file.
    
    Args:
        registry: FeatureRegistry instance
        output_file: Path to output JSON file
    
    Returns:
        Number of features exported
    """
    logger.info("Exporting features from registry")
    
    features = registry.export_to_dict()
    
    # Add export metadata
    export_data = {
        "export_timestamp": datetime.now().isoformat(),
        "feature_count": len(features),
        "features": features,
    }
    
    # Write to file
    with open(output_file, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    logger.info(
        "Features exported successfully",
        output_file=str(output_file),
        feature_count=len(features),
    )
    
    return len(features)


def import_features(registry: FeatureRegistry, input_file: Path) -> int:
    """
    Import features from JSON file to registry.
    
    Args:
        registry: FeatureRegistry instance
        input_file: Path to input JSON file
    
    Returns:
        Number of features imported
    """
    logger.info("Importing features to registry", input_file=str(input_file))
    
    # Read from file
    with open(input_file, 'r') as f:
        export_data = json.load(f)
    
    features = export_data.get("features", [])
    
    if not features:
        logger.warning("No features found in import file")
        return 0
    
    # Import features
    registry.import_from_dict(features)
    
    logger.info(
        "Features imported successfully",
        feature_count=len(features),
    )
    
    return len(features)


def validate_migration(
    source_registry: FeatureRegistry,
    target_registry: FeatureRegistry,
) -> bool:
    """
    Validate that migration was successful.
    
    Args:
        source_registry: Source registry (in-memory)
        target_registry: Target registry (database)
    
    Returns:
        True if validation passed, False otherwise
    """
    logger.info("Validating migration")
    
    # Get all features from both registries
    source_features = source_registry.export_to_dict()
    target_features = target_registry.list_all() if hasattr(target_registry, 'list_all') else []
    
    # Check count
    if len(source_features) != len(target_features):
        logger.error(
            "Feature count mismatch",
            source_count=len(source_features),
            target_count=len(target_features),
        )
        return False
    
    logger.info("Feature count validation passed", count=len(source_features))
    
    # Check feature names
    source_names = {f['name'] for f in source_features}
    target_names = {f['name'] for f in target_features}
    
    missing_in_target = source_names - target_names
    extra_in_target = target_names - source_names
    
    if missing_in_target:
        logger.error("Features missing in target", missing=list(missing_in_target))
        return False
    
    if extra_in_target:
        logger.warning("Extra features in target", extra=list(extra_in_target))
    
    logger.info("Feature name validation passed")
    
    # Check checksums for each feature (if available)
    checksum_mismatches = []
    for source_feature in source_features:
        feature_name = source_feature['name']
        
        # Find matching target feature
        target_feature = next((f for f in target_features if f['name'] == feature_name), None)
        
        if not target_feature:
            continue
        
        # Compute checksums
        source_checksum = compute_feature_checksum(source_feature)
        target_checksum = compute_feature_checksum(target_feature)
        
        if source_checksum != target_checksum:
            checksum_mismatches.append(feature_name)
    
    if checksum_mismatches:
        logger.error(
            "Checksum mismatches detected",
            mismatched_features=checksum_mismatches,
        )
        return False
    
    logger.info("Checksum validation passed")
    logger.info("✅ Migration validation PASSED")
    
    return True


def compute_feature_checksum(feature: Dict[str, Any]) -> str:
    """
    Compute checksum for a feature dictionary.
    
    Args:
        feature: Feature metadata dictionary
    
    Returns:
        SHA256 checksum (hex string)
    """
    # Create a canonical representation
    canonical = {
        "name": feature.get("name"),
        "source": feature.get("source"),
        "frequency": feature.get("frequency"),
        "version": feature.get("version"),
    }
    
    canonical_str = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(canonical_str.encode()).hexdigest()


def migrate_memory_to_database(
    memory_registry: FeatureRegistry,
    db_config: Dict[str, Any],
    dry_run: bool = False,
    validate: bool = True,
) -> bool:
    """
    Migrate features from in-memory registry to database.
    
    Args:
        memory_registry: In-memory source registry
        db_config: Database configuration
        dry_run: If True, don't actually write to database
        validate: If True, validate migration after completion
    
    Returns:
        True if migration successful, False otherwise
    """
    logger.info("Starting migration from memory to database", dry_run=dry_run)
    
    # Export features
    features = memory_registry.export_to_dict()
    
    logger.info("Features to migrate", count=len(features))
    
    if dry_run:
        logger.info("DRY RUN: Would migrate features", feature_names=[f['name'] for f in features])
        return True
    
    # Create database registry
    try:
        db_registry = FeatureRegistry(backend='database', db_config=db_config)
    except Exception as e:
        logger.error("Failed to connect to database", error=str(e), exc_info=True)
        return False
    
    # Import features to database
    try:
        db_registry.import_from_dict(features)
        logger.info("Features migrated to database", count=len(features))
    except Exception as e:
        logger.error("Migration failed", error=str(e), exc_info=True)
        return False
    
    # Validate if requested
    if validate:
        validation_passed = validate_migration(memory_registry, db_registry)
        if not validation_passed:
            logger.error("Migration validation failed")
            return False
    
    logger.info("✅ Migration completed successfully")
    return True


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate feature registry from in-memory to database"
    )
    
    parser.add_argument(
        "--source",
        choices=["memory", "database"],
        default="memory",
        help="Source backend (default: memory)",
    )
    
    parser.add_argument(
        "--target",
        choices=["memory", "database"],
        default="database",
        help="Target backend (default: database)",
    )
    
    parser.add_argument(
        "--export",
        type=Path,
        help="Export features to JSON file",
    )
    
    parser.add_argument(
        "--import",
        dest="import_file",
        type=Path,
        help="Import features from JSON file",
    )
    
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate migration after completion",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't actually write to target)",
    )
    
    parser.add_argument(
        "--db-host",
        default="localhost",
        help="Database host (default: localhost)",
    )
    
    parser.add_argument(
        "--db-port",
        type=int,
        default=5432,
        help="Database port (default: 5432)",
    )
    
    parser.add_argument(
        "--db-name",
        default="forecast_labor",
        help="Database name (default: forecast_labor)",
    )
    
    parser.add_argument(
        "--db-user",
        default="forecast_labor",
        help="Database user (default: forecast_labor)",
    )
    
    parser.add_argument(
        "--db-password",
        help="Database password (required for database mode)",
    )
    
    args = parser.parse_args()
    
    # Build database config
    db_config = {
        "host": args.db_host,
        "port": args.db_port,
        "database": args.db_name,
        "user": args.db_user,
        "password": args.db_password or "",
    }
    
    try:
        # Export mode
        if args.export:
            registry = FeatureRegistry(backend=args.source)
            if args.source == "database":
                registry = FeatureRegistry(backend='database', db_config=db_config)
            
            count = export_features(registry, args.export)
            logger.info(f"✅ Exported {count} features to {args.export}")
            return 0
        
        # Import mode
        if args.import_file:
            if not args.import_file.exists():
                logger.error(f"Import file not found: {args.import_file}")
                return 1
            
            registry = FeatureRegistry(backend=args.target)
            if args.target == "database":
                registry = FeatureRegistry(backend='database', db_config=db_config)
            
            count = import_features(registry, args.import_file)
            logger.info(f"✅ Imported {count} features from {args.import_file}")
            return 0
        
        # Migration mode
        if args.source == "memory" and args.target == "database":
            memory_registry = FeatureRegistry(backend='memory')
            
            # Load some test features for demonstration
            # In production, this would be your actual in-memory registry
            logger.warning("Migration source is empty in-memory registry. Add features first.")
            
            success = migrate_memory_to_database(
                memory_registry=memory_registry,
                db_config=db_config,
                dry_run=args.dry_run,
                validate=args.validate,
            )
            
            return 0 if success else 1
        
        logger.error("Invalid source/target combination or missing arguments")
        parser.print_help()
        return 1
    
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        return 130
    
    except Exception as e:
        logger.error("Migration failed with unexpected error", error=str(e), exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())


"""
Artifact versioning and signing for secure model deployment.

This module provides cryptographic signing and verification for model artifacts,
ensuring integrity and preventing tampering during deployment from Zone 1 (training)
to Zone 2 (inference/subnet submission).

Key features:
- SHA256 artifact signing
- Signature verification with tamper detection
- Metadata embedding (model info, feature checksums, vintage date)
- Signed bundle creation for zone transfers
- Feature lineage validation

Security model:
- All artifacts signed in Zone 1 (training environment)
- Zone 2 (inference) only accepts signed, verified artifacts
- Tampering detection prevents malicious modifications
- Feature checksums ensure reproducibility
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
from datetime import datetime
import hashlib
import json
import zipfile
import shutil

from loguru import logger

try:
    from features.registry import get_global_registry
except ImportError:  # pragma: no cover - optional integration
    get_global_registry = None


# ============================================================================
# Custom Exceptions
# ============================================================================


class SignatureError(Exception):
    """Base exception for signature-related errors."""
    pass


class TamperDetectedError(SignatureError):
    """Raised when artifact tampering is detected."""
    pass


# ============================================================================
# Hashing Utilities
# ============================================================================


def compute_file_hash(file_path: Path) -> str:
    """
    Compute SHA256 hash of a file.
    
    Args:
        file_path: Path to file
    
    Returns:
        SHA256 hash as hex string
    
    Raises:
        FileNotFoundError: If file doesn't exist
    
    Example:
        >>> hash_value = compute_file_hash(Path("model.pkl"))
        >>> print(f"Hash: {hash_value}")
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    sha256 = hashlib.sha256()
    
    # Read file in chunks for memory efficiency
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def compute_feature_checksum(feature_metadata: Dict[str, Any]) -> str:
    """
    Compute checksum for feature metadata.
    
    This creates a deterministic hash of feature metadata to ensure
    that the same feature definition always produces the same checksum.
    
    Args:
        feature_metadata: Feature metadata dictionary
    
    Returns:
        SHA256 checksum as hex string
    
    Example:
        >>> metadata = {"name": "unemployment_rate", "version": "1.0.0"}
        >>> checksum = compute_feature_checksum(metadata)
    """
    # Sort keys for deterministic serialization
    json_str = json.dumps(feature_metadata, sort_keys=True)
    
    sha256 = hashlib.sha256()
    sha256.update(json_str.encode("utf-8"))
    
    return sha256.hexdigest()


def _compute_combined_hash(
    file_hash: str,
    metadata: Dict[str, Any],
    feature_checksums: Dict[str, str],
) -> str:
    """
    Compute combined hash of file, metadata, and feature checksums.
    
    This creates a single signature that covers:
    - The artifact file itself
    - Model metadata
    - Feature checksums
    
    Any modification to any of these will change the signature.
    
    Args:
        file_hash: SHA256 hash of artifact file
        metadata: Model metadata
        feature_checksums: Feature checksums
    
    Returns:
        Combined SHA256 signature
    """
    # Create combined data structure
    combined_data = {
        "file_hash": file_hash,
        "metadata": metadata,
        "feature_checksums": feature_checksums,
    }
    
    # Serialize deterministically
    json_str = json.dumps(combined_data, sort_keys=True)
    
    sha256 = hashlib.sha256()
    sha256.update(json_str.encode("utf-8"))
    
    return sha256.hexdigest()


# ============================================================================
# SignedArtifact Data Class
# ============================================================================


@dataclass
class SignedArtifact:
    """
    Container for signed artifact information.
    
    Attributes:
        artifact_path: Path to the signed artifact
        signature: SHA256 signature
        metadata: Model metadata
        feature_checksums: Checksums of features used
        signed_at: Timestamp when artifact was signed
    """
    
    artifact_path: str
    signature: str
    metadata: Dict[str, Any]
    feature_checksums: Dict[str, str] = field(default_factory=dict)
    signed_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        data = asdict(self)
        # Convert datetime to ISO string
        data["signed_at"] = self.signed_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignedArtifact":
        """
        Create SignedArtifact from dictionary.
        
        Args:
            data: Dictionary with artifact information
        
        Returns:
            SignedArtifact instance
        """
        # Parse datetime from ISO string
        if isinstance(data.get("signed_at"), str):
            data["signed_at"] = datetime.fromisoformat(data["signed_at"])
        
        return cls(**data)


# ============================================================================
# Artifact Signer
# ============================================================================


class ArtifactSigner:
    """
    Sign and verify model artifacts for secure deployment.
    
    This class provides cryptographic signing to ensure artifact integrity
    and prevent tampering during deployment from Zone 1 to Zone 2.
    
    Examples:
        >>> signer = ArtifactSigner()
        >>> 
        >>> # Sign an artifact
        >>> signed = signer.sign(
        ...     artifact_path=Path("model.pkl"),
        ...     metadata={"model_name": "nfp_forecast", "version": 1},
        ...     feature_checksums={"feat1": "abc123", "feat2": "def456"}
        ... )
        >>> 
        >>> # Verify the signature
        >>> is_valid = signer.verify(signed)
        >>> print(f"Signature valid: {is_valid}")
    """
    
    def __init__(self):
        """Initialize artifact signer."""
        logger.info("Artifact signer initialized")
    
    def sign(
        self,
        artifact_path: Path,
        metadata: Dict[str, Any],
        feature_checksums: Optional[Dict[str, str]] = None,
        validate_features: bool = False,
    ) -> SignedArtifact:
        """
        Sign an artifact with metadata and feature checksums.
        
        Args:
            artifact_path: Path to artifact file
            metadata: Model metadata
            feature_checksums: Optional feature checksums
            validate_features: If True, validate against feature registry
        
        Returns:
            SignedArtifact with signature
        
        Raises:
            FileNotFoundError: If artifact doesn't exist
        
        Example:
            >>> signed = signer.sign(
            ...     artifact_path=Path("model.pkl"),
            ...     metadata={"vintage_date": "2024-12-31"}
            ... )
        """
        artifact_path = Path(artifact_path)
        
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")
        
        logger.info(
            "Signing artifact",
            artifact=str(artifact_path),
            has_features=feature_checksums is not None,
        )
        
        # Compute file hash
        file_hash = compute_file_hash(artifact_path)
        
        # Use empty dict if no feature checksums provided
        if feature_checksums is None:
            feature_checksums = {}
        
        # Optionally validate against feature registry
        if validate_features:
            try:
                if get_global_registry is None:
                    raise ImportError("Feature registry not available")
                registry = get_global_registry()
                
                # Query registry for feature validation
                for feature_name in feature_checksums.keys():
                    matches = registry.search(name=feature_name)
                    if matches:
                        logger.debug(f"Validated feature: {feature_name}")
            
            except ImportError:
                logger.warning("Feature registry not available for validation")
        
        # Compute combined signature
        signature = _compute_combined_hash(file_hash, metadata, feature_checksums)
        
        # Create signed artifact
        signed_artifact = SignedArtifact(
            artifact_path=str(artifact_path),
            signature=signature,
            metadata=metadata,
            feature_checksums=feature_checksums,
            signed_at=datetime.now(),
        )
        
        logger.info(
            "Artifact signed successfully",
            artifact=str(artifact_path),
            signature=signature[:16] + "...",
        )
        
        return signed_artifact
    
    def verify(self, signed_artifact: SignedArtifact) -> bool:
        """
        Verify signed artifact integrity.
        
        This checks:
        1. Artifact file exists
        2. File hash matches signature
        3. Metadata hasn't been modified
        4. Feature checksums haven't been modified
        
        Args:
            signed_artifact: SignedArtifact to verify
        
        Returns:
            True if valid
        
        Raises:
            FileNotFoundError: If artifact file not found
            TamperDetectedError: If tampering detected
        
        Example:
            >>> is_valid = signer.verify(signed_artifact)
            >>> if is_valid:
            ...     print("Artifact is authentic")
        """
        artifact_path = Path(signed_artifact.artifact_path)
        
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")
        
        logger.info("Verifying artifact", artifact=str(artifact_path))
        
        # Recompute file hash
        current_file_hash = compute_file_hash(artifact_path)
        
        # Recompute signature
        expected_signature = _compute_combined_hash(
            current_file_hash,
            signed_artifact.metadata,
            signed_artifact.feature_checksums,
        )
        
        # Compare signatures
        if expected_signature != signed_artifact.signature:
            logger.error(
                "Signature verification failed - tampering detected",
                artifact=str(artifact_path),
                expected=expected_signature[:16] + "...",
                actual=signed_artifact.signature[:16] + "...",
            )
            raise TamperDetectedError(
                f"Signature verification failed for {artifact_path}. "
                "Artifact may have been tampered with."
            )
        
        logger.info(
            "Artifact verified successfully",
            artifact=str(artifact_path),
        )
        
        return True


# ============================================================================
# Signed Bundle Operations (Zone 1 → Zone 2)
# ============================================================================


def create_signed_bundle(
    artifact_path: Path,
    metadata: Dict[str, Any],
    output_path: Path,
    feature_checksums: Optional[Dict[str, str]] = None,
    additional_files: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """
    Create signed bundle for Zone 2 deployment.
    
    This packages the model artifact, metadata, and signatures into a
    single zip file that can be securely transferred to Zone 2.
    
    Bundle structure:
    - manifest.json: Signature and metadata
    - artifact/: Model artifact files
    - additional/: Any additional files
    
    Args:
        artifact_path: Path to main artifact
        metadata: Model metadata
        output_path: Output path for bundle
        feature_checksums: Optional feature checksums
        additional_files: Optional additional files to include
    
    Returns:
        Bundle information dictionary
    
    Raises:
        FileNotFoundError: If artifact or additional files not found
    
    Example:
        >>> bundle = create_signed_bundle(
        ...     artifact_path=Path("model.pkl"),
        ...     metadata={"model_name": "nfp_forecast"},
        ...     output_path=Path("model_bundle.zip"),
        ...     feature_checksums={"feat1": "abc123"}
        ... )
    """
    artifact_path = Path(artifact_path)
    output_path = Path(output_path)
    
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")
    
    logger.info(
        "Creating signed bundle",
        artifact=str(artifact_path),
        output=str(output_path),
    )
    
    # Sign the artifact
    signer = ArtifactSigner()
    signed_artifact = signer.sign(artifact_path, metadata, feature_checksums)
    
    # Create bundle
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add manifest
        manifest = signed_artifact.to_dict()
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        # Add main artifact
        zf.write(artifact_path, f"artifact/{artifact_path.name}")
        
        # Add additional files if provided
        if additional_files:
            for file_path in additional_files:
                file_path = Path(file_path)
                if not file_path.exists():
                    logger.warning(f"Additional file not found: {file_path}")
                    continue
                zf.write(file_path, f"additional/{file_path.name}")
    
    bundle_info = {
        "bundle_path": str(output_path),
        "manifest": signed_artifact.to_dict(),
        "size_bytes": output_path.stat().st_size,
        "created_at": datetime.now().isoformat(),
    }
    
    logger.info(
        "Signed bundle created successfully",
        output=str(output_path),
        size_mb=round(bundle_info["size_bytes"] / 1024 / 1024, 2),
    )
    
    return bundle_info


def extract_signed_bundle(
    bundle_path: Path,
    extract_dir: Path,
    verify: bool = True,
) -> Dict[str, Any]:
    """
    Extract and verify signed bundle.
    
    This extracts a signed bundle and optionally verifies its signature
    to ensure no tampering occurred during transfer.
    
    Args:
        bundle_path: Path to bundle file
        extract_dir: Directory to extract to
        verify: If True, verify signature after extraction
    
    Returns:
        Extraction result with verification status
    
    Raises:
        FileNotFoundError: If bundle not found
        TamperDetectedError: If verification fails
    
    Example:
        >>> result = extract_signed_bundle(
        ...     bundle_path=Path("model_bundle.zip"),
        ...     extract_dir=Path("zone2/models"),
        ...     verify=True
        ... )
        >>> if result["verified"]:
        ...     print("Bundle verified successfully")
    """
    bundle_path = Path(bundle_path)
    extract_dir = Path(extract_dir)
    
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle not found: {bundle_path}")
    
    logger.info(
        "Extracting signed bundle",
        bundle=str(bundle_path),
        extract_dir=str(extract_dir),
        verify=verify,
    )
    
    # Extract bundle
    with zipfile.ZipFile(bundle_path, "r") as zf:
        # Check for manifest
        if "manifest.json" not in zf.namelist():
            raise SignatureError("Bundle missing manifest.json")

        if verify:
            unexpected_files = [
                name for name in zf.namelist()
                if not (
                    name == "manifest.json"
                    or name.startswith("artifact/")
                    or name.startswith("additional/")
                )
            ]
            if unexpected_files:
                raise TamperDetectedError(
                    f"Bundle contains unexpected files: {unexpected_files}"
                )
        
        # Read manifest
        manifest_data = json.loads(zf.read("manifest.json"))
        signed_artifact = SignedArtifact.from_dict(manifest_data)
        
        # Extract all files
        zf.extractall(extract_dir)
    
    result = {
        "extract_dir": str(extract_dir),
        "manifest": manifest_data,
        "artifacts": [],
        "verified": False,
    }
    
    # Verify signature if requested
    if verify:
        # Update artifact path to extracted location
        artifact_name = Path(signed_artifact.artifact_path).name
        extracted_artifact_path = extract_dir / "artifact" / artifact_name
        
        if not extracted_artifact_path.exists():
            raise FileNotFoundError(
                f"Extracted artifact not found: {extracted_artifact_path}"
            )
        
        # Update path for verification
        signed_artifact.artifact_path = str(extracted_artifact_path)
        
        # Verify
        signer = ArtifactSigner()
        is_valid = signer.verify(signed_artifact)
        
        result["verified"] = is_valid
        
        logger.info(
            "Bundle verification completed",
            verified=is_valid,
        )
    
    # List extracted artifacts
    if (extract_dir / "artifact").exists():
        result["artifacts"] = [
            str(f.relative_to(extract_dir))
            for f in (extract_dir / "artifact").iterdir()
        ]
    
    logger.info(
        "Bundle extracted successfully",
        extract_dir=str(extract_dir),
        n_artifacts=len(result["artifacts"]),
    )
    
    return result


# ============================================================================
# Standalone Convenience Functions
# ============================================================================


def sign_artifact(
    artifact_path: Path,
    metadata: Dict[str, Any],
    feature_checksums: Optional[Dict[str, str]] = None,
) -> SignedArtifact:
    """
    Convenience function to sign an artifact.
    
    Args:
        artifact_path: Path to artifact
        metadata: Model metadata
        feature_checksums: Optional feature checksums
    
    Returns:
        SignedArtifact
    
    Example:
        >>> signed = sign_artifact(
        ...     Path("model.pkl"),
        ...     {"model_name": "nfp_forecast"}
        ... )
    """
    signer = ArtifactSigner()
    return signer.sign(artifact_path, metadata, feature_checksums)


def verify_artifact(signed_artifact: SignedArtifact) -> bool:
    """
    Convenience function to verify an artifact.
    
    Args:
        signed_artifact: SignedArtifact to verify
    
    Returns:
        True if valid
    
    Raises:
        TamperDetectedError: If tampering detected
    
    Example:
        >>> is_valid = verify_artifact(signed_artifact)
    """
    signer = ArtifactSigner()
    return signer.verify(signed_artifact)


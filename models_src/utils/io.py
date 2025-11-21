"""
Model I/O and serialization utilities.

This module provides functionality for saving and loading forecasting models
with comprehensive metadata tracking, versioning, and integrity verification.

Key features:
- Multiple serialization formats (pickle, joblib)
- SHA256-based artifact versioning and verification
- Comprehensive metadata tracking (training date, features, hyperparameters, vintage)
- Integration with feature registry for reproducibility
- Signature verification to detect tampering
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import date, datetime
import pickle
import joblib
import hashlib
import json
import sys

from loguru import logger


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ModelMetadata:
    """
    Comprehensive metadata for a trained forecasting model.
    
    This metadata enables reproducibility, auditing, and version management
    of model artifacts. All timestamps should be timezone-aware.
    
    Attributes:
        model_id: Unique identifier for the model instance
        model_type: Type/class name of the model (e.g., "DFM", "MIDAS")
        training_date: Timestamp when the model was trained
        vintage_date: The vintage date of training data (critical for reproducibility)
        features: List of feature names used in training
        hyperparameters: Model hyperparameters used for training
        metrics: Performance metrics (e.g., {"rmse": 100, "smape": 15})
        python_version: Python version used for training
        dependencies: Key dependency versions (e.g., {"pandas": "2.0.0"})
        feature_versions: Optional mapping of feature names to versions
        notes: Optional free-text notes about the model
    """
    
    model_id: str
    model_type: str
    training_date: datetime
    vintage_date: date
    features: List[str]
    hyperparameters: Dict[str, Any]
    metrics: Dict[str, float]
    python_version: str
    dependencies: Dict[str, str]
    feature_versions: Optional[Dict[str, str]] = None
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert metadata to a JSON-serializable dictionary.
        
        Returns:
            Dictionary representation of metadata
        """
        data = asdict(self)
        
        # Convert datetime to ISO format string
        if isinstance(data["training_date"], datetime):
            data["training_date"] = data["training_date"].isoformat()
        
        # Convert date to ISO format string
        if isinstance(data["vintage_date"], date):
            data["vintage_date"] = data["vintage_date"].isoformat()
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelMetadata":
        """
        Create ModelMetadata from a dictionary.
        
        Args:
            data: Dictionary with metadata fields
        
        Returns:
            ModelMetadata instance
        """
        # Parse datetime string
        if isinstance(data["training_date"], str):
            data["training_date"] = datetime.fromisoformat(data["training_date"])
        
        # Parse date string
        if isinstance(data["vintage_date"], str):
            data["vintage_date"] = date.fromisoformat(data["vintage_date"])
        
        return cls(**data)


@dataclass
class ModelArtifact:
    """
    Container for a model artifact with all associated metadata.
    
    This class represents a complete, serialized model artifact including
    the model object, metadata, and verification information.
    
    Attributes:
        model: The model object (may be None if not loaded)
        metadata: Associated metadata
        model_path: Path to the serialized model file
        metadata_path: Path to the metadata JSON file
        hash_value: SHA256 hash of the model artifact
    """
    
    model: Optional[Any]
    metadata: ModelMetadata
    model_path: Path
    metadata_path: Path
    hash_value: str


# ============================================================================
# Basic Save/Load Functions
# ============================================================================


def save_model(
    model: Any,
    file_path: Union[str, Path],
    format: str = "joblib",
) -> None:
    """
    Save a model to disk using the specified serialization format.
    
    Args:
        model: The model object to save
        file_path: Path where the model should be saved
        format: Serialization format ("pickle" or "joblib")
    
    Raises:
        ValueError: If the format is unsupported
        IOError: If saving fails
    
    Examples:
        >>> save_model(my_model, "models/my_model.joblib", format="joblib")
        >>> save_model(my_model, "models/my_model.pkl", format="pickle")
    """
    file_path = Path(file_path)
    
    # Validate format
    if format not in ["pickle", "joblib"]:
        raise ValueError(f"Unsupported format: {format}. Use 'pickle' or 'joblib'.")
    
    # Create parent directory if it doesn't exist
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if format == "pickle":
            with open(file_path, "wb") as f:
                pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
        elif format == "joblib":
            joblib.dump(model, file_path, compress=3)
        
        logger.info(
            "Model saved successfully",
            file_path=str(file_path),
            format=format,
            size_bytes=file_path.stat().st_size,
        )
    
    except Exception as e:
        logger.error(
            "Failed to save model",
            file_path=str(file_path),
            format=format,
            error=str(e),
            exc_info=True,
        )
        raise IOError(f"Failed to save model to {file_path}: {e}") from e


def load_model(
    file_path: Union[str, Path],
    format: str = "joblib",
) -> Any:
    """
    Load a model from disk using the specified serialization format.
    
    Args:
        file_path: Path to the serialized model file
        format: Serialization format ("pickle" or "joblib")
    
    Returns:
        The loaded model object
    
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the format is unsupported
        IOError: If loading fails
    
    Examples:
        >>> model = load_model("models/my_model.joblib", format="joblib")
        >>> model = load_model("models/my_model.pkl", format="pickle")
    """
    file_path = Path(file_path)
    
    # Check if file exists
    if not file_path.exists():
        raise FileNotFoundError(f"Model file not found: {file_path}")
    
    # Validate format
    if format not in ["pickle", "joblib"]:
        raise ValueError(f"Unsupported format: {format}. Use 'pickle' or 'joblib'.")
    
    try:
        if format == "pickle":
            with open(file_path, "rb") as f:
                model = pickle.load(f)
        elif format == "joblib":
            model = joblib.load(file_path)
        
        logger.info(
            "Model loaded successfully",
            file_path=str(file_path),
            format=format,
            model_type=type(model).__name__,
        )
        
        return model
    
    except Exception as e:
        logger.error(
            "Failed to load model",
            file_path=str(file_path),
            format=format,
            error=str(e),
            exc_info=True,
        )
        raise IOError(f"Failed to load model from {file_path}: {e}") from e


# ============================================================================
# Artifact Hashing & Verification
# ============================================================================


def compute_artifact_hash(file_path: Union[str, Path]) -> str:
    """
    Compute SHA256 hash of a file for versioning and integrity verification.
    
    This function reads the file in chunks to handle large model files
    efficiently without loading the entire file into memory.
    
    Args:
        file_path: Path to the file to hash
    
    Returns:
        SHA256 hash as a hexadecimal string (64 characters)
    
    Raises:
        FileNotFoundError: If the file doesn't exist
        IOError: If reading the file fails
    
    Examples:
        >>> hash_value = compute_artifact_hash("models/my_model.joblib")
        >>> print(len(hash_value))  # Always 64
        64
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    sha256_hash = hashlib.sha256()
    
    try:
        with open(file_path, "rb") as f:
            # Read in 64kb chunks for memory efficiency
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)
        
        hash_value = sha256_hash.hexdigest()
        
        logger.debug(
            "Computed artifact hash",
            file_path=str(file_path),
            hash=hash_value,
        )
        
        return hash_value
    
    except Exception as e:
        logger.error(
            "Failed to compute artifact hash",
            file_path=str(file_path),
            error=str(e),
            exc_info=True,
        )
        raise IOError(f"Failed to compute hash for {file_path}: {e}") from e


def verify_artifact_signature(
    file_path: Union[str, Path],
    expected_hash: str,
) -> bool:
    """
    Verify that a file's hash matches the expected value.
    
    This function is used to detect tampering or corruption of model artifacts.
    
    Args:
        file_path: Path to the file to verify
        expected_hash: Expected SHA256 hash (64-character hex string)
    
    Returns:
        True if the hash matches, False otherwise
    
    Raises:
        FileNotFoundError: If the file doesn't exist
    
    Examples:
        >>> expected = compute_artifact_hash("models/my_model.joblib")
        >>> is_valid = verify_artifact_signature("models/my_model.joblib", expected)
        >>> assert is_valid is True
    """
    actual_hash = compute_artifact_hash(file_path)
    is_valid = actual_hash == expected_hash
    
    if is_valid:
        logger.debug(
            "Artifact signature verified",
            file_path=str(file_path),
            hash=actual_hash,
        )
    else:
        logger.warning(
            "Artifact signature verification FAILED",
            file_path=str(file_path),
            expected_hash=expected_hash,
            actual_hash=actual_hash,
        )
    
    return is_valid


# ============================================================================
# Model + Metadata Save/Load
# ============================================================================


def save_model_with_metadata(
    model: Any,
    metadata: ModelMetadata,
    output_dir: Union[str, Path],
    model_name: str,
    format: str = "joblib",
    include_feature_info: bool = False,
) -> ModelArtifact:
    """
    Save a model with comprehensive metadata and compute artifact hash.
    
    This function saves:
    1. The model artifact (using pickle or joblib)
    2. A metadata JSON file with training information
    3. Computes and stores the artifact hash in metadata
    
    Args:
        model: The model object to save
        metadata: ModelMetadata instance with training information
        output_dir: Directory where artifacts should be saved
        model_name: Base name for the model files (without extension)
        format: Serialization format ("pickle" or "joblib")
        include_feature_info: If True, query feature registry for feature info
    
    Returns:
        ModelArtifact instance with paths and hash
    
    Examples:
        >>> metadata = ModelMetadata(...)
        >>> artifact = save_model_with_metadata(
        ...     model=my_model,
        ...     metadata=metadata,
        ...     output_dir="models/production",
        ...     model_name="nfp_forecast_v1",
        ... )
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine file extension
    extension = "pkl" if format == "pickle" else "joblib"
    
    # Define file paths
    model_path = output_dir / f"{model_name}.{extension}"
    metadata_path = output_dir / f"{model_name}_metadata.json"
    
    # Save the model
    save_model(model, model_path, format=format)
    
    # Compute artifact hash
    hash_value = compute_artifact_hash(model_path)
    
    # Prepare metadata dictionary
    metadata_dict = metadata.to_dict()
    metadata_dict["artifact_hash"] = hash_value
    metadata_dict["serialization_format"] = format
    
    # Optionally include feature registry information
    if include_feature_info:
        try:
            # Import here to avoid circular dependency
            from features.registry import get_global_registry
            
            registry = get_global_registry()
            
            # Get feature metadata for features used in model training
            feature_info = []
            if metadata.feature_names:
                for feature_name in metadata.feature_names:
                    try:
                        # Search for feature by name
                        matches = registry.search(name=feature_name)
                        if matches:
                            # Use the most recent version
                            feature_metadata = matches[0]
                            feature_info.append({
                                'name': feature_metadata.get('name'),
                                'source': feature_metadata.get('source'),
                                'frequency': feature_metadata.get('frequency'),
                                'vintage_date': feature_metadata.get('vintage_date'),
                                'version': feature_metadata.get('version', 1),
                            })
                    except Exception as e:
                        logger.warning(
                            "Could not retrieve feature metadata",
                            feature_name=feature_name,
                            error=str(e)
                        )
            
            metadata_dict["feature_registry_info"] = {
                'features': feature_info,
                'feature_count': len(feature_info),
                'registry_backend': registry.backend,
            }
            
            logger.info(
                "Feature registry info included",
                feature_count=len(feature_info),
                registry_backend=registry.backend
            )
            
        except ImportError:
            logger.warning("Feature registry not available, skipping feature info")
        except Exception as e:
            logger.warning(
                "Failed to query feature registry",
                error=str(e),
                exc_info=True
            )
    
    # Save metadata
    try:
        with open(metadata_path, "w") as f:
            json.dump(metadata_dict, f, indent=2)
        
        logger.info(
            "Model and metadata saved successfully",
            model_path=str(model_path),
            metadata_path=str(metadata_path),
            hash=hash_value,
            model_type=metadata.model_type,
        )
    
    except Exception as e:
        logger.error(
            "Failed to save metadata",
            metadata_path=str(metadata_path),
            error=str(e),
            exc_info=True,
        )
        raise IOError(f"Failed to save metadata to {metadata_path}: {e}") from e
    
    return ModelArtifact(
        model=model,
        metadata=metadata,
        model_path=model_path,
        metadata_path=metadata_path,
        hash_value=hash_value,
    )


def load_model_with_metadata(
    model_path: Union[str, Path],
    verify_signature: bool = True,
) -> ModelArtifact:
    """
    Load a model with its associated metadata and verify integrity.
    
    This function:
    1. Loads the metadata JSON file
    2. Optionally verifies the artifact hash
    3. Loads the model object
    4. Returns a ModelArtifact instance
    
    Args:
        model_path: Path to the serialized model file
        verify_signature: If True, verify artifact hash matches metadata
    
    Returns:
        ModelArtifact instance with loaded model and metadata
    
    Raises:
        FileNotFoundError: If model or metadata file doesn't exist
        ValueError: If signature verification fails (when enabled)
    
    Examples:
        >>> artifact = load_model_with_metadata("models/nfp_forecast_v1.joblib")
        >>> model = artifact.model
        >>> metadata = artifact.metadata
    """
    model_path = Path(model_path)
    
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    
    # Construct metadata path
    metadata_path = model_path.parent / f"{model_path.stem}_metadata.json"
    
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")
    
    # Load metadata
    try:
        with open(metadata_path, "r") as f:
            metadata_dict = json.load(f)
        
        # Extract artifact hash and format
        artifact_hash = metadata_dict.pop("artifact_hash", None)
        serialization_format = metadata_dict.pop("serialization_format", "joblib")
        
        # Create ModelMetadata instance
        metadata = ModelMetadata.from_dict(metadata_dict)
        
        logger.debug(
            "Metadata loaded successfully",
            metadata_path=str(metadata_path),
            model_type=metadata.model_type,
        )
    
    except Exception as e:
        logger.error(
            "Failed to load metadata",
            metadata_path=str(metadata_path),
            error=str(e),
            exc_info=True,
        )
        raise IOError(f"Failed to load metadata from {metadata_path}: {e}") from e
    
    # Verify signature if requested
    if verify_signature and artifact_hash:
        is_valid = verify_artifact_signature(model_path, artifact_hash)
        
        if not is_valid:
            raise ValueError(
                f"Artifact signature verification failed for {model_path}. "
                f"The file may have been tampered with or corrupted."
            )
    
    # Load the model
    model = load_model(model_path, format=serialization_format)
    
    return ModelArtifact(
        model=model,
        metadata=metadata,
        model_path=model_path,
        metadata_path=metadata_path,
        hash_value=artifact_hash or "",
    )


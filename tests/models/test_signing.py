"""
Tests for artifact versioning and signing.

This module tests model artifact signing for secure deployment:
- SHA256 artifact signing
- Signature verification
- Tamper detection
- Metadata embedding (including feature checksums)
- Zone 1 → Zone 2 artifact preparation
"""

import pytest
import tempfile
import shutil
import json
import hashlib
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import pickle

from models_src.utils.signing import (
    ArtifactSigner,
    SignedArtifact,
    SignatureError,
    TamperDetectedError,
    sign_artifact,
    verify_artifact,
    create_signed_bundle,
    extract_signed_bundle,
    compute_file_hash,
    compute_feature_checksum,
)
from models_src.utils.base_model import BaseForecaster


# ============================================================================
# Test Helpers
# ============================================================================


class MockForecaster(BaseForecaster):
    """Mock forecaster for testing signing operations."""
    
    def __init__(self, random_state=42):
        super().__init__(random_state=random_state)
        self._is_fitted = False
    
    def fit(self, X, y, vintage_date):
        """Fit mock model."""
        self._is_fitted = True
        self.vintage_date = vintage_date
        self.feature_names = X.columns.tolist()
        return self
    
    def predict(self, X):
        """Generate mock predictions."""
        if not self._is_fitted:
            raise ValueError("Model must be fitted before prediction")
        return X.iloc[:, 0].values
    
    def get_params(self):
        """Return mock parameters."""
        return {
            "random_state": self.random_state,
            "is_fitted": self._is_fitted,
        }


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create temporary directory for test artifacts."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir)


@pytest.fixture
def sample_model_file(temp_dir):
    """Create sample model file."""
    model = MockForecaster(random_state=42)
    model_path = temp_dir / "model.pkl"
    
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    
    return model_path


@pytest.fixture
def sample_metadata():
    """Sample metadata for artifact signing."""
    return {
        "model_name": "test_model",
        "model_version": 1,
        "vintage_date": "2024-12-31",
        "training_date": "2025-01-15T10:30:00",
        "features": ["feature_1", "feature_2", "feature_3"],
        "metrics": {"rmse": 100.0, "mae": 80.0},
    }


@pytest.fixture
def sample_feature_checksums():
    """Sample feature checksums."""
    return {
        "feature_1": "abc123def456",
        "feature_2": "789ghi012jkl",
        "feature_3": "345mno678pqr",
    }


# ============================================================================
# Test File Hashing
# ============================================================================


class TestFileHashing:
    """Test SHA256 file hashing utilities."""
    
    def test_compute_file_hash(self, sample_model_file):
        """Test computing SHA256 hash of a file."""
        hash_value = compute_file_hash(sample_model_file)
        
        assert hash_value is not None
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 is 64 hex characters
    
    def test_compute_file_hash_deterministic(self, sample_model_file):
        """Test that file hash is deterministic."""
        hash1 = compute_file_hash(sample_model_file)
        hash2 = compute_file_hash(sample_model_file)
        
        assert hash1 == hash2
    
    def test_compute_file_hash_different_files(self, temp_dir):
        """Test that different files have different hashes."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        
        file1.write_text("content 1")
        file2.write_text("content 2")
        
        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)
        
        assert hash1 != hash2
    
    def test_compute_file_hash_missing_file(self, temp_dir):
        """Test that missing file raises error."""
        missing_file = temp_dir / "nonexistent.pkl"
        
        with pytest.raises(FileNotFoundError):
            compute_file_hash(missing_file)
    
    def test_compute_file_hash_modified_file(self, temp_dir):
        """Test that hash changes when file is modified."""
        test_file = temp_dir / "test.txt"
        
        test_file.write_text("original content")
        hash1 = compute_file_hash(test_file)
        
        test_file.write_text("modified content")
        hash2 = compute_file_hash(test_file)
        
        assert hash1 != hash2


# ============================================================================
# Test Feature Checksums
# ============================================================================


class TestFeatureChecksums:
    """Test feature checksum computation."""
    
    def test_compute_feature_checksum(self):
        """Test computing checksum for a feature."""
        feature_metadata = {
            "name": "feature_1",
            "version": "1.0.0",
            "source": "ces",
            "transform": "log",
        }
        
        checksum = compute_feature_checksum(feature_metadata)
        
        assert checksum is not None
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA256
    
    def test_feature_checksum_deterministic(self):
        """Test that feature checksum is deterministic."""
        feature_metadata = {
            "name": "feature_1",
            "version": "1.0.0",
        }
        
        checksum1 = compute_feature_checksum(feature_metadata)
        checksum2 = compute_feature_checksum(feature_metadata)
        
        assert checksum1 == checksum2
    
    def test_feature_checksum_changes_with_metadata(self):
        """Test that checksum changes when metadata changes."""
        metadata1 = {"name": "feature_1", "version": "1.0.0"}
        metadata2 = {"name": "feature_1", "version": "1.0.1"}
        
        checksum1 = compute_feature_checksum(metadata1)
        checksum2 = compute_feature_checksum(metadata2)
        
        assert checksum1 != checksum2


# ============================================================================
# Test SignedArtifact Dataclass
# ============================================================================


class TestSignedArtifact:
    """Test SignedArtifact dataclass."""
    
    def test_signed_artifact_creation(self, sample_metadata):
        """Test creating SignedArtifact."""
        artifact = SignedArtifact(
            artifact_path="model.pkl",
            signature="abc123",
            metadata=sample_metadata,
            feature_checksums={},
            signed_at=datetime.now(),
        )
        
        assert artifact.artifact_path == "model.pkl"
        assert artifact.signature == "abc123"
        assert artifact.metadata == sample_metadata
    
    def test_signed_artifact_to_dict(self, sample_metadata):
        """Test converting SignedArtifact to dictionary."""
        signed_at = datetime.now()
        artifact = SignedArtifact(
            artifact_path="model.pkl",
            signature="abc123",
            metadata=sample_metadata,
            feature_checksums={"feat1": "xyz"},
            signed_at=signed_at,
        )
        
        artifact_dict = artifact.to_dict()
        
        assert artifact_dict["artifact_path"] == "model.pkl"
        assert artifact_dict["signature"] == "abc123"
        assert "signed_at" in artifact_dict
    
    def test_signed_artifact_from_dict(self, sample_metadata):
        """Test creating SignedArtifact from dictionary."""
        artifact_dict = {
            "artifact_path": "model.pkl",
            "signature": "abc123",
            "metadata": sample_metadata,
            "feature_checksums": {},
            "signed_at": "2025-01-15T10:30:00",
        }
        
        artifact = SignedArtifact.from_dict(artifact_dict)
        
        assert artifact.artifact_path == "model.pkl"
        assert artifact.signature == "abc123"


# ============================================================================
# Test ArtifactSigner
# ============================================================================


class TestArtifactSigner:
    """Test ArtifactSigner class."""
    
    def test_signer_initialization(self):
        """Test that signer initializes correctly."""
        signer = ArtifactSigner()
        
        assert signer is not None
    
    def test_sign_artifact(self, sample_model_file, sample_metadata):
        """Test signing an artifact."""
        signer = ArtifactSigner()
        
        signed_artifact = signer.sign(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
        )
        
        assert signed_artifact is not None
        assert signed_artifact.signature is not None
        assert len(signed_artifact.signature) == 64  # SHA256
        assert signed_artifact.metadata == sample_metadata
    
    def test_sign_artifact_with_features(
        self,
        sample_model_file,
        sample_metadata,
        sample_feature_checksums,
    ):
        """Test signing artifact with feature checksums."""
        signer = ArtifactSigner()
        
        signed_artifact = signer.sign(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            feature_checksums=sample_feature_checksums,
        )
        
        assert signed_artifact.feature_checksums == sample_feature_checksums
    
    def test_sign_missing_file(self, temp_dir, sample_metadata):
        """Test that signing missing file raises error."""
        signer = ArtifactSigner()
        missing_file = temp_dir / "nonexistent.pkl"
        
        with pytest.raises(FileNotFoundError):
            signer.sign(missing_file, sample_metadata)
    
    def test_sign_deterministic(self, sample_model_file, sample_metadata):
        """Test that signing produces deterministic signatures."""
        signer = ArtifactSigner()
        
        signed1 = signer.sign(sample_model_file, sample_metadata)
        signed2 = signer.sign(sample_model_file, sample_metadata)
        
        # Same file should produce same signature
        assert signed1.signature == signed2.signature


# ============================================================================
# Test Signature Verification
# ============================================================================


class TestSignatureVerification:
    """Test signature verification."""
    
    def test_verify_valid_signature(self, sample_model_file, sample_metadata):
        """Test verifying a valid signature."""
        signer = ArtifactSigner()
        
        # Sign the artifact
        signed_artifact = signer.sign(sample_model_file, sample_metadata)
        
        # Verify it
        is_valid = signer.verify(signed_artifact)
        
        assert is_valid is True
    
    def test_verify_modified_file_fails(self, sample_model_file, sample_metadata):
        """Test that verification fails if file is modified."""
        signer = ArtifactSigner()
        
        # Sign the artifact
        signed_artifact = signer.sign(sample_model_file, sample_metadata)
        
        # Modify the file
        with open(sample_model_file, "ab") as f:
            f.write(b"tampered")
        
        # Verification should fail
        with pytest.raises(TamperDetectedError):
            signer.verify(signed_artifact)
    
    def test_verify_modified_signature_fails(self, sample_model_file, sample_metadata):
        """Test that verification fails if signature is modified."""
        signer = ArtifactSigner()
        
        # Sign the artifact
        signed_artifact = signer.sign(sample_model_file, sample_metadata)
        
        # Modify the signature
        signed_artifact.signature = "invalid_signature_hash"
        
        # Verification should fail
        with pytest.raises(TamperDetectedError):
            signer.verify(signed_artifact)
    
    def test_verify_modified_metadata_fails(self, sample_model_file, sample_metadata):
        """Test that verification fails if metadata is modified."""
        signer = ArtifactSigner()
        
        # Sign the artifact
        signed_artifact = signer.sign(sample_model_file, sample_metadata)
        
        # Modify metadata
        signed_artifact.metadata["model_version"] = 999
        
        # Verification should fail (metadata is part of signature)
        with pytest.raises(TamperDetectedError):
            signer.verify(signed_artifact)
    
    def test_verify_missing_file_fails(self, sample_model_file, sample_metadata):
        """Test that verification fails if artifact file is missing."""
        signer = ArtifactSigner()
        
        # Sign the artifact
        signed_artifact = signer.sign(sample_model_file, sample_metadata)
        
        # Delete the file
        sample_model_file.unlink()
        
        # Verification should fail
        with pytest.raises(FileNotFoundError):
            signer.verify(signed_artifact)


# ============================================================================
# Test Round-Trip Signing/Verification
# ============================================================================


class TestRoundTripSignVerify:
    """Test sign/verify round-trip operations."""
    
    def test_sign_verify_roundtrip(self, sample_model_file, sample_metadata):
        """Test that sign → verify roundtrip works."""
        signer = ArtifactSigner()
        
        # Sign
        signed = signer.sign(sample_model_file, sample_metadata)
        
        # Verify
        is_valid = signer.verify(signed)
        
        assert is_valid is True
    
    def test_multiple_roundtrips(self, sample_model_file, sample_metadata):
        """Test multiple sign/verify cycles."""
        signer = ArtifactSigner()
        
        for i in range(5):
            signed = signer.sign(sample_model_file, sample_metadata)
            is_valid = signer.verify(signed)
            assert is_valid is True
    
    def test_roundtrip_with_features(
        self,
        sample_model_file,
        sample_metadata,
        sample_feature_checksums,
    ):
        """Test roundtrip with feature checksums."""
        signer = ArtifactSigner()
        
        signed = signer.sign(
            sample_model_file,
            sample_metadata,
            feature_checksums=sample_feature_checksums,
        )
        
        is_valid = signer.verify(signed)
        
        assert is_valid is True
        assert signed.feature_checksums == sample_feature_checksums


# ============================================================================
# Test Tamper Detection
# ============================================================================


class TestTamperDetection:
    """Test tamper detection capabilities."""
    
    def test_detect_file_modification(self, sample_model_file, sample_metadata):
        """Test detecting file modification."""
        signer = ArtifactSigner()
        signed = signer.sign(sample_model_file, sample_metadata)
        
        # Modify file
        with open(sample_model_file, "ab") as f:
            f.write(b"extra data")
        
        with pytest.raises(TamperDetectedError, match="Signature verification failed"):
            signer.verify(signed)
    
    def test_detect_signature_modification(self, sample_model_file, sample_metadata):
        """Test detecting signature modification."""
        signer = ArtifactSigner()
        signed = signer.sign(sample_model_file, sample_metadata)
        
        # Change signature
        signed.signature = "0" * 64
        
        with pytest.raises(TamperDetectedError):
            signer.verify(signed)
    
    def test_detect_metadata_modification(self, sample_model_file, sample_metadata):
        """Test detecting metadata modification."""
        signer = ArtifactSigner()
        signed = signer.sign(sample_model_file, sample_metadata)
        
        # Change metadata
        signed.metadata["vintage_date"] = "2099-12-31"
        
        with pytest.raises(TamperDetectedError):
            signer.verify(signed)
    
    def test_detect_feature_checksum_modification(
        self,
        sample_model_file,
        sample_metadata,
        sample_feature_checksums,
    ):
        """Test detecting feature checksum modification."""
        signer = ArtifactSigner()
        signed = signer.sign(
            sample_model_file,
            sample_metadata,
            feature_checksums=sample_feature_checksums,
        )
        
        # Modify feature checksum
        signed.feature_checksums["feature_1"] = "tampered_checksum"
        
        with pytest.raises(TamperDetectedError):
            signer.verify(signed)


# ============================================================================
# Test Signed Bundle Creation (Zone 1 → Zone 2)
# ============================================================================


class TestSignedBundleCreation:
    """Test creating signed bundles for Zone 2 deployment."""
    
    def test_create_signed_bundle(
        self,
        sample_model_file,
        sample_metadata,
        temp_dir,
    ):
        """Test creating a signed bundle."""
        output_path = temp_dir / "bundle.zip"
        
        bundle = create_signed_bundle(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            output_path=output_path,
        )
        
        assert bundle is not None
        assert output_path.exists()
        assert output_path.stat().st_size > 0
    
    def test_bundle_contains_manifest(
        self,
        sample_model_file,
        sample_metadata,
        temp_dir,
    ):
        """Test that bundle contains a manifest file."""
        output_path = temp_dir / "bundle.zip"
        
        bundle = create_signed_bundle(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            output_path=output_path,
        )
        
        # Bundle should have manifest
        assert "manifest" in bundle
        assert "signature" in bundle["manifest"]
        assert "metadata" in bundle["manifest"]
    
    def test_bundle_with_multiple_artifacts(self, temp_dir, sample_metadata):
        """Test creating bundle with multiple artifacts."""
        # Create multiple files
        model_file = temp_dir / "model.pkl"
        scaler_file = temp_dir / "scaler.pkl"
        
        model_file.write_bytes(b"model data")
        scaler_file.write_bytes(b"scaler data")
        
        output_path = temp_dir / "bundle.zip"
        
        bundle = create_signed_bundle(
            artifact_path=model_file,
            metadata=sample_metadata,
            output_path=output_path,
            additional_files=[scaler_file],
        )
        
        assert bundle is not None
        assert output_path.exists()


# ============================================================================
# Test Signed Bundle Extraction
# ============================================================================


class TestSignedBundleExtraction:
    """Test extracting and verifying signed bundles."""
    
    def test_extract_signed_bundle(
        self,
        sample_model_file,
        sample_metadata,
        temp_dir,
    ):
        """Test extracting a signed bundle."""
        # Create bundle
        bundle_path = temp_dir / "bundle.zip"
        create_signed_bundle(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            output_path=bundle_path,
        )
        
        # Extract bundle
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        result = extract_signed_bundle(bundle_path, extract_dir)
        
        assert result is not None
        assert "artifacts" in result
        assert "manifest" in result
    
    def test_extract_verifies_signature(
        self,
        sample_model_file,
        sample_metadata,
        temp_dir,
    ):
        """Test that extraction verifies signatures."""
        # Create bundle
        bundle_path = temp_dir / "bundle.zip"
        create_signed_bundle(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            output_path=bundle_path,
        )
        
        # Extract (should verify signature automatically)
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        result = extract_signed_bundle(bundle_path, extract_dir, verify=True)
        
        assert result is not None
        assert result["verified"] is True
    
    def test_extract_tampered_bundle_fails(
        self,
        sample_model_file,
        sample_metadata,
        temp_dir,
    ):
        """Test that extracting tampered bundle fails verification."""
        import zipfile
        
        # Create bundle
        bundle_path = temp_dir / "bundle.zip"
        create_signed_bundle(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            output_path=bundle_path,
        )
        
        # Tamper with bundle (modify a file inside)
        with zipfile.ZipFile(bundle_path, "a") as zf:
            zf.writestr("tamper.txt", "malicious content")
        
        # Extract with verification should fail
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()
        
        with pytest.raises(TamperDetectedError):
            extract_signed_bundle(bundle_path, extract_dir, verify=True)


# ============================================================================
# Test Feature Checksum Validation
# ============================================================================


class TestFeatureChecksumValidation:
    """Test feature checksum validation during verification."""
    
    def test_validate_feature_checksums(
        self,
        sample_model_file,
        sample_metadata,
        sample_feature_checksums,
    ):
        """Test that feature checksums are validated."""
        signer = ArtifactSigner()
        
        signed = signer.sign(
            sample_model_file,
            sample_metadata,
            feature_checksums=sample_feature_checksums,
        )
        
        # Should verify successfully
        is_valid = signer.verify(signed)
        assert is_valid is True
    
    def test_validate_feature_checksum_mismatch(
        self,
        sample_model_file,
        sample_metadata,
        sample_feature_checksums,
    ):
        """Test that mismatched feature checksums fail validation."""
        signer = ArtifactSigner()
        
        signed = signer.sign(
            sample_model_file,
            sample_metadata,
            feature_checksums=sample_feature_checksums,
        )
        
        # Modify a feature checksum
        signed.feature_checksums["feature_1"] = "wrong_checksum"
        
        with pytest.raises(TamperDetectedError):
            signer.verify(signed)
    
    @patch("models_src.utils.signing.get_global_registry")
    def test_validate_against_feature_registry(
        self,
        mock_get_registry,
        sample_model_file,
        sample_metadata,
    ):
        """Test validating feature checksums against feature registry."""
        # Mock feature registry
        mock_registry = Mock()
        mock_registry.search.return_value = [
            {"feature_id": "feat-1", "checksum": "abc123"},
        ]
        mock_get_registry.return_value = mock_registry
        
        signer = ArtifactSigner()
        
        # Sign with feature validation
        signed = signer.sign(
            sample_model_file,
            sample_metadata,
            validate_features=True,
        )
        
        # Should have queried feature registry
        assert signed is not None


# ============================================================================
# Test Standalone Convenience Functions
# ============================================================================


class TestStandaloneFunctions:
    """Test standalone convenience functions."""
    
    def test_sign_artifact_function(self, sample_model_file, sample_metadata):
        """Test standalone sign_artifact function."""
        signed = sign_artifact(sample_model_file, sample_metadata)
        
        assert signed is not None
        assert signed.signature is not None
    
    def test_verify_artifact_function(self, sample_model_file, sample_metadata):
        """Test standalone verify_artifact function."""
        signed = sign_artifact(sample_model_file, sample_metadata)
        is_valid = verify_artifact(signed)
        
        assert is_valid is True
    
    def test_verify_tampered_artifact_function(
        self,
        sample_model_file,
        sample_metadata,
    ):
        """Test that standalone verify detects tampering."""
        signed = sign_artifact(sample_model_file, sample_metadata)
        
        # Tamper with file
        with open(sample_model_file, "ab") as f:
            f.write(b"tampered")
        
        with pytest.raises(TamperDetectedError):
            verify_artifact(signed)


# ============================================================================
# Test Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling in signing operations."""
    
    def test_sign_invalid_path(self, sample_metadata):
        """Test signing with invalid path raises error."""
        signer = ArtifactSigner()
        
        with pytest.raises(FileNotFoundError):
            signer.sign(Path("/nonexistent/path.pkl"), sample_metadata)
    
    def test_verify_invalid_artifact(self):
        """Test verifying invalid artifact raises error."""
        signer = ArtifactSigner()
        
        invalid_artifact = SignedArtifact(
            artifact_path="nonexistent.pkl",
            signature="abc123",
            metadata={},
            feature_checksums={},
            signed_at=datetime.now(),
        )
        
        with pytest.raises(FileNotFoundError):
            signer.verify(invalid_artifact)
    
    def test_create_bundle_missing_artifact(self, temp_dir, sample_metadata):
        """Test creating bundle with missing artifact fails."""
        missing_file = temp_dir / "nonexistent.pkl"
        output_path = temp_dir / "bundle.zip"
        
        with pytest.raises(FileNotFoundError):
            create_signed_bundle(missing_file, sample_metadata, output_path)


# ============================================================================
# Test Zone Transfer Workflow
# ============================================================================


class TestZoneTransferWorkflow:
    """Test complete Zone 1 → Zone 2 transfer workflow."""
    
    def test_complete_zone_transfer(
        self,
        sample_model_file,
        sample_metadata,
        sample_feature_checksums,
        temp_dir,
    ):
        """Test complete workflow: sign → bundle → extract → verify."""
        # Zone 1: Sign the artifact
        signed = sign_artifact(
            sample_model_file,
            sample_metadata,
            feature_checksums=sample_feature_checksums,
        )
        
        # Zone 1: Create signed bundle
        bundle_path = temp_dir / "zone_transfer.zip"
        create_signed_bundle(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            output_path=bundle_path,
            feature_checksums=sample_feature_checksums,
        )
        
        # Zone 2: Extract bundle
        zone2_dir = temp_dir / "zone2"
        zone2_dir.mkdir()
        result = extract_signed_bundle(bundle_path, zone2_dir, verify=True)
        
        # Verify all steps succeeded
        assert result is not None
        assert result["verified"] is True
        assert "artifacts" in result
    
    def test_zone_transfer_prevents_tampering(
        self,
        sample_model_file,
        sample_metadata,
        temp_dir,
    ):
        """Test that zone transfer detects tampering."""
        import zipfile
        
        # Zone 1: Create bundle
        bundle_path = temp_dir / "zone_transfer.zip"
        create_signed_bundle(
            artifact_path=sample_model_file,
            metadata=sample_metadata,
            output_path=bundle_path,
        )
        
        # Attacker: Tamper with bundle
        with zipfile.ZipFile(bundle_path, "a") as zf:
            zf.writestr("malicious.py", "import os; os.system('rm -rf /')")
        
        # Zone 2: Extract should fail verification
        zone2_dir = temp_dir / "zone2"
        zone2_dir.mkdir()
        
        with pytest.raises(TamperDetectedError):
            extract_signed_bundle(bundle_path, zone2_dir, verify=True)


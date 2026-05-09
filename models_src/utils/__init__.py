"""Model utilities package."""

from models_src.utils.registry import (
    ModelRegistryClient,
    RegisteredModel,
    register_model,
    get_model_by_name,
    get_model_by_stage,
    promote_model,
    get_model_features,
    get_models_using_feature,
)

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

__all__ = [
    # Registry
    "ModelRegistryClient",
    "RegisteredModel",
    "register_model",
    "get_model_by_name",
    "get_model_by_stage",
    "promote_model",
    "get_model_features",
    "get_models_using_feature",
    # Signing
    "ArtifactSigner",
    "SignedArtifact",
    "SignatureError",
    "TamperDetectedError",
    "sign_artifact",
    "verify_artifact",
    "create_signed_bundle",
    "extract_signed_bundle",
    "compute_file_hash",
    "compute_feature_checksum",
]

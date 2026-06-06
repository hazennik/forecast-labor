"""Signed artifact loading and inference for Zone 2."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from app.schemas.forecast import ForecastInterval, ForecastRequest, ForecastResponse
from app.services.artifacts import ArtifactRepository
from app.services.deployment import summarize_zone2_isolation
from models_src.utils.io import load_model


class InferenceUnavailableError(RuntimeError):
    """Raised when no verified model artifact can serve inference."""


@dataclass
class LoadedModel:
    """Loaded model and signed artifact metadata."""

    model: Any
    metadata: Dict[str, Any]
    artifact_path: Path
    artifact_hash: str


class InferenceService:
    """Load verified signed artifacts and serve forecasts from them."""

    def __init__(self, repository: ArtifactRepository) -> None:
        """Initialize inference service with an artifact repository."""
        self.repository = repository
        self._cached_model: Optional[LoadedModel] = None
        self._cached_bundle_path: Optional[Path] = None

    def load_active_model(self) -> LoadedModel:
        """Load the active verified model artifact from Zone 2 storage."""
        isolation_status = summarize_zone2_isolation(self.repository.settings)
        if not isolation_status.isolated:
            raise InferenceUnavailableError("; ".join(isolation_status.blockers))

        bundle_path = self.repository.get_active_bundle_path()
        if bundle_path is None:
            raise InferenceUnavailableError("No active signed model bundle configured or found")

        if self._cached_model is not None and self._cached_bundle_path == bundle_path:
            return self._cached_model

        status = self.repository.summarize_active_bundle()
        if not status["active"] or not status["artifact"]:
            blockers = status.get("blockers", ["Active artifact is not verified"])
            raise InferenceUnavailableError("; ".join(blockers))

        artifact_info = status["artifact"]
        artifacts = artifact_info.get("artifacts", [])
        if not artifacts:
            raise InferenceUnavailableError("Verified bundle does not contain model artifacts")

        extract_dir = Path(artifact_info["extract_dir"])
        artifact_path = extract_dir / artifacts[0]
        model = load_model(artifact_path, format=self._serialization_format(artifact_path))
        manifest = artifact_info["metadata"]

        loaded = LoadedModel(
            model=model,
            metadata=dict(manifest.get("metadata", {})),
            artifact_path=artifact_path,
            artifact_hash=str(manifest.get("signature", "")),
        )
        self._cached_model = loaded
        self._cached_bundle_path = bundle_path
        return loaded

    def predict(self, request: ForecastRequest) -> ForecastResponse:
        """Run model inference for a forecast request."""
        loaded = self.load_active_model()
        raw_prediction = self._call_predict(loaded.model, request.features)
        prediction_payload = self._normalize_prediction(raw_prediction)
        metadata = dict(loaded.metadata)
        model_id = str(
            metadata.get("model_id")
            or metadata.get("model_name")
            or metadata.get("name")
            or type(loaded.model).__name__
        )

        return ForecastResponse(
            target=request.target,
            vintage_date=request.vintage_date,
            prediction=float(prediction_payload["prediction"]),
            intervals=prediction_payload["intervals"],
            probabilities=prediction_payload["probabilities"],
            model_id=model_id,
            artifact_hash=loaded.artifact_hash,
            metadata=metadata,
        )

    @staticmethod
    def _serialization_format(path: Path) -> str:
        """Infer model serialization format from artifact suffix."""
        return "pickle" if path.suffix in {".pkl", ".pickle"} else "joblib"

    @staticmethod
    def _call_predict(model: Any, features: Dict[str, float]) -> Any:
        """Call a model predict method with a single-row feature frame."""
        if not hasattr(model, "predict"):
            raise InferenceUnavailableError("Loaded artifact does not expose predict()")

        frame = pd.DataFrame([features])
        try:
            return model.predict(frame)
        except Exception as exc:
            logger.error("model_predict_failed", error=str(exc), exc_info=True)
            raise InferenceUnavailableError(f"Model prediction failed: {exc}") from exc

    @staticmethod
    def _normalize_prediction(raw_prediction: Any) -> Dict[str, Any]:
        """Normalize common model prediction shapes into API response parts."""
        if isinstance(raw_prediction, dict):
            prediction = raw_prediction.get("prediction", raw_prediction.get("point_forecast"))
            if prediction is None:
                raise InferenceUnavailableError("Prediction dictionary missing prediction value")
            return {
                "prediction": InferenceService._first_value(prediction),
                "intervals": InferenceService._parse_intervals(raw_prediction.get("intervals", [])),
                "probabilities": dict(raw_prediction.get("probabilities", {})),
            }

        return {
            "prediction": InferenceService._first_value(raw_prediction),
            "intervals": [],
            "probabilities": {},
        }

    @staticmethod
    def _first_value(value: Any) -> float:
        """Extract the first scalar value from common prediction containers."""
        if hasattr(value, "iloc"):
            return float(value.iloc[0])
        if isinstance(value, (list, tuple)):
            return float(value[0])
        if hasattr(value, "__array__"):
            array = value.__array__()
            return float(array.reshape(-1)[0])
        return float(value)

    @staticmethod
    def _parse_intervals(intervals: Any) -> List[ForecastInterval]:
        """Parse interval dictionaries into response schema objects."""
        parsed: List[ForecastInterval] = []
        for interval in intervals or []:
            parsed.append(
                ForecastInterval(
                    level=float(interval["level"]),
                    lower=float(interval["lower"]),
                    upper=float(interval["upper"]),
                )
            )
        return parsed

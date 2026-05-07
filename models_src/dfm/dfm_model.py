"""Statsmodels-backed Dynamic Factor Model for monthly nowcasting.

The MIDAS bridge aligns daily and weekly inputs to monthly frequency before
this model sees them. This class therefore uses statsmodels' single-frequency
``DynamicFactor`` implementation and preserves the existing project interface:
``fit(X, y, vintage_date)``, ``predict(X)``, ``save(path)``, and ``load(path)``.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Sequence
import re

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
import statsmodels

from models_src.utils.base_model import BaseForecaster


class DynamicFactorModel(BaseForecaster):
    """Dynamic Factor Model with statsmodels estimation and stable projection.

    Args:
        n_factors: Number of latent factors exposed by the public model.
        max_iter: Maximum optimizer iterations for statsmodels.
        tol: Optimizer tolerance.
        random_state: Random seed for deterministic preprocessing/fallbacks.
        ridge_alphas: Candidate ridge penalties for the supervised nowcast head.
        include_direct_features: Whether the supervised head can use standardized
            bridge features in addition to extracted DFM factors.

    Attributes:
        factors_: Extracted factor time series, shaped ``(n_samples, n_factors)``.
        loadings_: Factor loadings, shaped ``(n_features, n_factors)``.
        transition_: Factor transition matrix, shaped ``(n_factors, n_factors)``.
        is_fitted: Whether the model has been fitted.
    """

    IMPLEMENTATION = "statsmodels_dynamic_factor"

    def __init__(
        self,
        n_factors: int,
        max_iter: int = 100,
        tol: float = 1e-4,
        random_state: int = 42,
        ridge_alphas: Optional[Sequence[float]] = None,
        include_direct_features: bool = True,
    ):
        """Initialize the Dynamic Factor Model."""
        super().__init__(random_state=random_state)

        if n_factors <= 0:
            raise ValueError(f"n_factors must be positive, got {n_factors}")

        self.n_factors = n_factors
        self.max_iter = max_iter
        self.tol = tol
        self.ridge_alphas = tuple(ridge_alphas or (0.1, 1.0, 10.0, 100.0))
        if any(alpha < 0.0 for alpha in self.ridge_alphas):
            raise ValueError("ridge_alphas must be non-negative")
        self.include_direct_features = include_direct_features
        self.is_fitted = False

        logger.info(
            "dfm_initialized",
            n_factors=n_factors,
            max_iter=max_iter,
            tol=tol,
            random_state=random_state,
            ridge_alphas=self.ridge_alphas,
            include_direct_features=include_direct_features,
            implementation=self.IMPLEMENTATION,
        )

    def fit(
        self, X: pd.DataFrame, y: pd.Series, vintage_date: str
    ) -> "DynamicFactorModel":
        """Fit the statsmodels DynamicFactor model and target regression."""
        self._validate_fit_inputs(X, y, vintage_date)

        self.vintage_date = vintage_date
        self.n_features = X.shape[1]
        self.feature_names_ = list(X.columns)
        self.feature_metadata_ = {
            "feature_names": self.feature_names_,
            "vintage_date": vintage_date,
            "n_features": self.n_features,
        }

        logger.info(
            "dfm_training_started",
            n_samples=len(X),
            n_features=self.n_features,
            n_factors=self.n_factors,
            vintage_date=vintage_date,
        )

        np.random.seed(self.random_state)
        X_scaled = self._preprocess_features(X, fit=True)
        X_head = self._preprocess_supervised_features(X)
        y_scaled = self._preprocess_target(y, fit=True)

        self._fit_dynamic_factor(X_scaled)
        self._train_prediction_model(y_scaled, X_head)
        self.is_fitted = True

        logger.info(
            "dfm_training_completed",
            n_iter=self.n_iter_,
            converged=self.converged_,
            log_likelihood=float(self.log_likelihood_[-1]),
            explained_variance=float(self.explained_variance_),
        )
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Generate predictions for a feature matrix with training-time columns."""
        if not self.is_fitted:
            raise ValueError(
                "Model must be fitted before prediction. Call fit() first."
            )

        if list(X.columns) != self.feature_names_:
            raise ValueError(
                "Feature names do not match training. "
                f"Expected {self.feature_names_}, got {list(X.columns)}"
            )

        X_scaled = self._preprocess_features(X, fit=False)
        X_head = self._preprocess_supervised_features(X)
        factors = self._extract_factors(X_scaled)
        design = self._build_supervised_design(factors, X_head)
        predictions_scaled = design @ self.prediction_coef_ + self.prediction_intercept_
        predictions = predictions_scaled * self.y_std_ + self.y_mean_

        logger.debug(
            "dfm_predictions_generated",
            n_samples=len(X),
            mean_prediction=float(np.mean(predictions)),
            std_prediction=float(np.std(predictions)),
        )
        return np.asarray(predictions, dtype=float)

    def get_params(self) -> Dict[str, Any]:
        """Return model hyperparameters, metadata, and fitted-state details."""
        params: Dict[str, Any] = {
            "n_factors": self.n_factors,
            "max_iter": self.max_iter,
            "tol": self.tol,
            "random_state": self.random_state,
            "ridge_alphas": self.ridge_alphas,
            "include_direct_features": self.include_direct_features,
            "implementation": self.IMPLEMENTATION,
            "statsmodels_version": statsmodels.__version__,
            "is_fitted": self.is_fitted,
            "vintage_date": getattr(self, "vintage_date", None),
            "n_features": getattr(self, "n_features", None),
        }

        if self.is_fitted:
            params.update(
                {
                    "n_iter_": self.n_iter_,
                    "converged_": self.converged_,
                    "internal_n_factors_": self.internal_n_factors_,
                    "selected_ridge_alpha_": self.selected_ridge_alpha_,
                    "explained_variance_": self.explained_variance_,
                    "feature_metadata": self.feature_metadata_,
                }
            )

        return params

    def save(self, path: Path) -> None:
        """Save serializable model artifacts to disk."""
        if not self.is_fitted:
            raise ValueError("Model must be fitted before saving. Call fit() first.")

        model_data = {
            "implementation": self.IMPLEMENTATION,
            "statsmodels_version": statsmodels.__version__,
            "n_factors": self.n_factors,
            "internal_n_factors_": self.internal_n_factors_,
            "max_iter": self.max_iter,
            "tol": self.tol,
            "random_state": self.random_state,
            "ridge_alphas": self.ridge_alphas,
            "include_direct_features": self.include_direct_features,
            "vintage_date": self.vintage_date,
            "n_features": self.n_features,
            "feature_names_": self.feature_names_,
            "feature_metadata_": self.feature_metadata_,
            "loadings_": self.loadings_,
            "transition_": self.transition_,
            "factors_": self.factors_,
            "prediction_coef_": self.prediction_coef_,
            "prediction_intercept_": self.prediction_intercept_,
            "selected_ridge_alpha_": self.selected_ridge_alpha_,
            "explained_variance_": self.explained_variance_,
            "X_mean_": self.X_mean_,
            "X_std_": self.X_std_,
            "X_lower_": self.X_lower_,
            "X_upper_": self.X_upper_,
            "y_mean_": self.y_mean_,
            "y_std_": self.y_std_,
            "n_iter_": self.n_iter_,
            "converged_": self.converged_,
            "log_likelihood_": self.log_likelihood_,
            "model_id": self.model_id,
            "created_at": self.created_at,
        }

        joblib.dump(model_data, path)
        logger.info("dfm_model_saved", path=str(path), model_id=self.model_id)

    @classmethod
    def load(cls, path: Path) -> "DynamicFactorModel":
        """Load a saved DynamicFactorModel artifact."""
        model_data = joblib.load(path)
        model = cls(
            n_factors=model_data["n_factors"],
            max_iter=model_data["max_iter"],
            tol=model_data["tol"],
            random_state=model_data["random_state"],
            ridge_alphas=model_data.get("ridge_alphas"),
            include_direct_features=model_data.get("include_direct_features", True),
        )

        for key, value in model_data.items():
            if key in {"implementation", "statsmodels_version"}:
                continue
            setattr(model, key, value)

        model.is_fitted = True
        logger.info("dfm_model_loaded", path=str(path), model_id=model.model_id)
        return model

    def _validate_fit_inputs(
        self, X: pd.DataFrame, y: pd.Series, vintage_date: str
    ) -> None:
        """Validate fit inputs before estimation."""
        if len(X) != len(y):
            raise ValueError(
                f"X and y must have same length. Got X: {len(X)}, y: {len(y)}"
            )
        if len(X) < 5:
            raise ValueError("DynamicFactorModel requires at least 5 observations")
        if X.empty or X.shape[1] == 0:
            raise ValueError("X must contain at least one feature column")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", vintage_date):
            raise ValueError(
                f"vintage_date must be in YYYY-MM-DD format, got '{vintage_date}'"
            )

    def _preprocess_features(self, X: pd.DataFrame, fit: bool) -> np.ndarray:
        """Clean, standardize, and winsorize feature data."""
        numeric = self._clean_numeric_features(X)

        if fit:
            self.X_mean_ = numeric.mean(axis=0).to_numpy(dtype=float)
            std = numeric.std(axis=0, ddof=0).replace(0.0, 1.0)
            self.X_std_ = std.to_numpy(dtype=float)

        scaled = (numeric.to_numpy(dtype=float) - self.X_mean_) / self.X_std_

        if fit:
            self.X_lower_ = np.nanquantile(scaled, 0.01, axis=0)
            self.X_upper_ = np.nanquantile(scaled, 0.99, axis=0)
            same_bounds = np.isclose(self.X_lower_, self.X_upper_)
            self.X_lower_[same_bounds] = -np.inf
            self.X_upper_[same_bounds] = np.inf

        clipped = np.clip(scaled, self.X_lower_, self.X_upper_)
        return np.nan_to_num(clipped, nan=0.0, posinf=0.0, neginf=0.0)

    def _preprocess_supervised_features(self, X: pd.DataFrame) -> np.ndarray:
        """Standardize bridge features for the supervised head."""
        numeric = self._clean_numeric_features(X)
        scaled = (numeric.to_numpy(dtype=float) - self.X_mean_) / self.X_std_
        return np.nan_to_num(scaled, nan=0.0, posinf=0.0, neginf=0.0)

    def _clean_numeric_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """Convert feature data to finite numeric values."""
        numeric = X.apply(pd.to_numeric, errors="coerce")
        numeric = numeric.replace([np.inf, -np.inf], np.nan)
        return numeric.ffill().bfill().fillna(0.0)

    def _preprocess_target(self, y: pd.Series, fit: bool) -> np.ndarray:
        """Clean and standardize target data."""
        target = pd.to_numeric(y, errors="coerce").replace([np.inf, -np.inf], np.nan)
        target = (
            target.ffill()
            .bfill()
            .fillna(float(target.mean()) if not target.dropna().empty else 0.0)
        )

        if fit:
            self.y_mean_ = float(target.mean())
            self.y_std_ = float(target.std(ddof=0))
            if self.y_std_ == 0.0 or not np.isfinite(self.y_std_):
                self.y_std_ = 1.0

        return ((target.to_numpy(dtype=float) - self.y_mean_) / self.y_std_).astype(
            float
        )

    def _fit_dynamic_factor(self, X_scaled: np.ndarray) -> None:
        """Fit statsmodels DynamicFactor and extract serializable artifacts."""
        n_samples, n_features = X_scaled.shape
        self.internal_n_factors_ = self._choose_internal_factor_count(n_features)

        if n_features < 2:
            logger.warning(
                "dfm_using_pca_fallback",
                reason="statsmodels_requires_multiple_features",
            )
            self._fit_pca_fallback(X_scaled)
            return

        model = DynamicFactor(
            endog=X_scaled,
            k_factors=self.internal_n_factors_,
            factor_order=1,
            error_cov_type="diagonal",
            enforce_stationarity=True,
        )
        results = model.fit(disp=False, maxiter=self.max_iter, pgtol=self.tol)

        raw_factors = np.asarray(results.factors.filtered, dtype=float).T
        raw_loadings = self._extract_loadings(
            results, n_features, self.internal_n_factors_
        )
        raw_transition = self._extract_transition(results, self.internal_n_factors_)

        self.factors_ = self._pad_columns(raw_factors, n_samples)
        self.loadings_ = self._pad_loadings(raw_loadings, n_features)
        self.transition_ = self._pad_transition(raw_transition)
        self.log_likelihood_ = [float(results.llf)]
        self.n_iter_ = int(results.mle_retvals.get("iterations", self.max_iter))
        self.converged_ = bool(results.mle_retvals.get("converged", False))
        self.explained_variance_ = self._compute_explained_variance(X_scaled)

    def _fit_pca_fallback(self, X_scaled: np.ndarray) -> None:
        """Use deterministic SVD when statsmodels is not identifiable."""
        n_samples, n_features = X_scaled.shape
        _, singular_values, vt = np.linalg.svd(X_scaled, full_matrices=False)
        usable = min(self.n_factors, vt.shape[0])

        raw_factors = X_scaled @ vt[:usable].T
        raw_loadings = vt[:usable].T
        raw_transition = np.eye(usable) * 0.9

        self.factors_ = self._pad_columns(raw_factors, n_samples)
        self.loadings_ = self._pad_loadings(raw_loadings, n_features)
        self.transition_ = self._pad_transition(raw_transition)
        self.log_likelihood_ = [
            -0.5 * float(np.sum((X_scaled - self.factors_ @ self.loadings_.T) ** 2))
        ]
        self.n_iter_ = 1
        self.converged_ = True
        total_variance = float(np.sum(singular_values**2))
        self.explained_variance_ = (
            float(np.sum(singular_values[:usable] ** 2) / total_variance)
            if total_variance > 0
            else 0.0
        )

    def _choose_internal_factor_count(self, n_features: int) -> int:
        """Choose an identifiable statsmodels factor count."""
        if n_features < 2:
            return 1
        return max(1, min(self.n_factors, n_features - 1))

    def _extract_loadings(
        self, results: Any, n_features: int, n_factors: int
    ) -> np.ndarray:
        """Extract the observation/loading matrix from statsmodels results."""
        try:
            design = np.asarray(results.model.ssm["design"], dtype=float)
            if design.ndim == 3:
                design = design[:, :, 0]
            loadings = design[:, :n_factors]
            if loadings.shape == (n_features, n_factors) and np.any(
                np.abs(loadings) > 0
            ):
                return loadings
        except Exception as exc:
            logger.debug("dfm_design_extraction_failed", error=str(exc))

        loadings = np.zeros((n_features, n_factors), dtype=float)
        loading_params = [
            (name, value)
            for name, value in zip(results.param_names, results.params)
            if name.startswith("loading.f")
        ]
        for loading_idx, (param_name, param_value) in enumerate(loading_params):
            if not param_name.startswith("loading.f"):
                continue
            factor_part = param_name.split(".", 2)[1]
            factor_idx = int(factor_part.replace("f", "")) - 1
            series_idx = loading_idx // n_factors
            if factor_idx < n_factors and series_idx < n_features:
                loadings[series_idx, factor_idx] = float(param_value)

        if not np.any(np.abs(loadings) > 0):
            _, _, vt = np.linalg.svd(
                np.asarray(results.model.endog, dtype=float), full_matrices=False
            )
            loadings[:, :n_factors] = vt[:n_factors].T
        return loadings

    def _extract_transition(self, results: Any, n_factors: int) -> np.ndarray:
        """Extract a stable factor transition matrix from statsmodels results."""
        try:
            transition = np.asarray(results.model.ssm["transition"], dtype=float)
            if transition.ndim == 3:
                transition = transition[:, :, 0]
            transition = transition[:n_factors, :n_factors]
            if transition.shape == (n_factors, n_factors):
                return np.nan_to_num(transition, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception as exc:
            logger.debug("dfm_transition_extraction_failed", error=str(exc))
        return np.eye(n_factors) * 0.9

    def _pad_columns(self, factors: np.ndarray, n_samples: int) -> np.ndarray:
        """Pad or trim factor columns to the public ``n_factors`` count."""
        output = np.zeros((n_samples, self.n_factors), dtype=float)
        usable = min(self.n_factors, factors.shape[1])
        output[:, :usable] = factors[:, :usable]
        return output

    def _pad_loadings(self, loadings: np.ndarray, n_features: int) -> np.ndarray:
        """Pad or trim loading columns to the public ``n_factors`` count."""
        output = np.zeros((n_features, self.n_factors), dtype=float)
        usable = min(self.n_factors, loadings.shape[1])
        output[:, :usable] = loadings[:, :usable]
        return output

    def _pad_transition(self, transition: np.ndarray) -> np.ndarray:
        """Pad or trim transition matrix to the public ``n_factors`` count."""
        output = np.eye(self.n_factors, dtype=float) * 0.9
        usable = min(self.n_factors, transition.shape[0], transition.shape[1])
        output[:usable, :usable] = transition[:usable, :usable]
        return output

    def _compute_explained_variance(self, X_scaled: np.ndarray) -> float:
        """Estimate variance share represented by the retained factor dimension."""
        singular_values = np.linalg.svd(X_scaled, compute_uv=False)
        total = float(np.sum(singular_values**2))
        if total <= 0.0:
            return 0.0
        retained = min(self.n_factors, len(singular_values))
        explained = float(np.sum(singular_values[:retained] ** 2) / total)
        return max(0.0, min(1.0, explained))

    def _train_prediction_model(
        self, y_scaled: np.ndarray, X_scaled: np.ndarray
    ) -> None:
        """Train a regularized supervised nowcast head on DFM factors."""
        design = self._build_supervised_design(self.factors_, X_scaled)
        alpha = self._select_ridge_alpha(design, y_scaled)
        coef, intercept = self._fit_ridge_head(design, y_scaled, alpha)

        self.prediction_coef_ = coef
        self.prediction_intercept_ = intercept
        self.selected_ridge_alpha_ = alpha

    def _build_supervised_design(
        self, factors: np.ndarray, X_scaled: np.ndarray
    ) -> np.ndarray:
        """Combine DFM factors with standardized bridge features for nowcasting."""
        if not self.include_direct_features:
            return np.asarray(factors, dtype=float)
        return np.column_stack(
            [np.asarray(factors, dtype=float), np.asarray(X_scaled, dtype=float)]
        )

    def _select_ridge_alpha(self, design: np.ndarray, y_scaled: np.ndarray) -> float:
        """Choose ridge strength with a deterministic time-ordered validation split."""
        if len(self.ridge_alphas) == 1 or len(design) < 24:
            return float(self.ridge_alphas[0])

        split_idx = max(5, int(len(design) * 0.8))
        if len(design) - split_idx < 3:
            return float(self.ridge_alphas[0])

        X_train, X_val = design[:split_idx], design[split_idx:]
        y_train, y_val = y_scaled[:split_idx], y_scaled[split_idx:]
        best_alpha = float(self.ridge_alphas[0])
        best_mse = float("inf")

        for alpha in self.ridge_alphas:
            coef, intercept = self._fit_ridge_head(X_train, y_train, float(alpha))
            predictions = X_val @ coef + intercept
            mse = float(np.mean((predictions - y_val) ** 2))
            if mse < best_mse:
                best_mse = mse
                best_alpha = float(alpha)

        logger.info(
            "dfm_ridge_alpha_selected", alpha=best_alpha, validation_mse=best_mse
        )
        return best_alpha

    def _fit_ridge_head(
        self,
        design: np.ndarray,
        y_scaled: np.ndarray,
        alpha: float,
    ) -> tuple[np.ndarray, float]:
        """Fit a ridge regression head without penalizing the intercept."""
        X = np.asarray(design, dtype=float)
        y = np.asarray(y_scaled, dtype=float)
        X_mean = X.mean(axis=0)
        y_mean = float(y.mean())
        X_centered = X - X_mean
        y_centered = y - y_mean

        penalty = np.eye(X_centered.shape[1], dtype=float) * alpha
        lhs = X_centered.T @ X_centered + penalty
        rhs = X_centered.T @ y_centered
        coef = np.linalg.pinv(lhs) @ rhs
        intercept = y_mean - float(X_mean @ coef)
        return np.asarray(coef, dtype=float), float(intercept)

    def _extract_factors(self, X_scaled: np.ndarray) -> np.ndarray:
        """Project new standardized observations onto learned loadings."""
        if X_scaled.shape[1] != self.loadings_.shape[0]:
            raise ValueError(
                f"Expected {self.loadings_.shape[0]} features, got {X_scaled.shape[1]}"
            )
        loadings_pinv = np.linalg.pinv(self.loadings_)
        factors = X_scaled @ loadings_pinv.T
        return np.nan_to_num(factors, nan=0.0, posinf=0.0, neginf=0.0)

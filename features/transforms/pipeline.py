"""
Transformation pipeline for chaining multiple transforms.

Allows composing multiple transformations in sequence, similar to
sklearn.pipeline.Pipeline but for pandas Series.
"""

from typing import List, Tuple, Any
import pandas as pd
from loguru import logger


class TransformPipeline:
    """
    Chain multiple transformations in sequence.

    Each transform must implement fit(), transform(), and fit_transform() methods.

    Args:
        steps: List of (name, transformer) tuples

    Example:
        >>> from features.transforms.scaling import StandardScaler, Winsorizer
        >>> pipeline = TransformPipeline([
        ...     ('winsorize', Winsorizer(lower=0.05, upper=0.95)),
        ...     ('standardize', StandardScaler())
        ... ])
        >>> result = pipeline.fit_transform(series)
    """

    def __init__(self, steps: List[Tuple[str, Any]]):
        """Initialize transformation pipeline."""
        if len(steps) == 0:
            raise ValueError("Pipeline must have at least one step")

        self.steps = steps
        self._validate_steps()

        logger.info("transform_pipeline_initialized", step_count=len(steps))

    def _validate_steps(self) -> None:
        """Validate that all steps have required methods."""
        for name, transformer in self.steps:
            if not hasattr(transformer, "fit"):
                raise ValueError(f"Transformer '{name}' must have fit() method")
            if not hasattr(transformer, "transform"):
                raise ValueError(f"Transformer '{name}' must have transform() method")
            if not hasattr(transformer, "fit_transform"):
                raise ValueError(f"Transformer '{name}' must have fit_transform() method")

    def fit(self, series: pd.Series) -> "TransformPipeline":
        """
        Fit all transformers in sequence.

        Each transformer is fitted on the output of the previous transformer.

        Args:
            series: Training data

        Returns:
            self
        """
        current_data = series.copy()

        for name, transformer in self.steps:
            logger.info("fitting_pipeline_step", step_name=name)
            transformer.fit(current_data)
            current_data = transformer.transform(current_data)

        logger.info("transform_pipeline_fitted", step_count=len(self.steps))

        return self

    def transform(self, series: pd.Series) -> pd.Series:
        """
        Apply all transformers in sequence.

        Args:
            series: Data to transform

        Returns:
            Transformed series
        """
        current_data = series.copy()

        for name, transformer in self.steps:
            logger.debug("applying_pipeline_step", step_name=name)
            current_data = transformer.transform(current_data)

        return current_data

    def fit_transform(self, series: pd.Series) -> pd.Series:
        """
        Fit and transform in one step.

        Args:
            series: Training data

        Returns:
            Transformed series
        """
        return self.fit(series).transform(series)

    def get_step(self, name: str) -> Any:
        """
        Get a specific transformer by name.

        Args:
            name: Step name

        Returns:
            Transformer object

        Raises:
            KeyError: If step name not found
        """
        for step_name, transformer in self.steps:
            if step_name == name:
                return transformer

        raise KeyError(f"Step '{name}' not found in pipeline")

    def __repr__(self) -> str:
        """String representation of pipeline."""
        step_names = [name for name, _ in self.steps]
        return f"TransformPipeline(steps={step_names})"

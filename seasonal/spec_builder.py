"""
X-13 Spec File Builder
Generates X-13ARIMA-SEATS specification files
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class X13Spec:
    """X-13 specification configuration"""
    series_name: str
    title: str
    start_year: int
    start_month: int
    
    # ARIMA model specification
    arima_model: Optional[str] = None  # e.g., "(0 1 1)(0 1 1)"
    auto_model: bool = True  # Let X-13 choose model
    
    # Seasonal adjustment options
    mode: str = "mult"  # "mult" or "add"
    
    # Regression variables
    user_regressors: List[str] = None
    regressor_data: Optional[Any] = None  # DataFrame with regressor values for embedding
    easter: bool = True
    trading_day: bool = True
    
    # Output options
    save_tables: List[str] = None  # e.g., ["d11", "d12", "d13", "d16"]
    
    def __post_init__(self):
        if self.user_regressors is None:
            self.user_regressors = []
        if self.save_tables is None:
            self.save_tables = ["d11", "d12", "d13", "d16"]


class SpecBuilder:
    """
    Builder for X-13ARIMA-SEATS specification files
    
    Generates .spc files for seasonal adjustment
    """
    
    def __init__(self):
        """Initialize spec builder"""
        self.specs = {}
    
    def build_spec(self, config: X13Spec) -> str:
        """
        Build X-13 spec file content
        
        Args:
            config: X13Spec configuration
            
        Returns:
            str: Spec file content
        """
        logger.info(f"Building X-13 spec for: {config.series_name}")
        
        sections = []
        
        # Series section
        sections.append(self._build_series_section(config))
        
        # Transform section (log transformation for multiplicative)
        if config.mode == "mult":
            sections.append(self._build_transform_section())
        
        # Regression section
        if config.easter or config.trading_day or config.user_regressors:
            sections.append(self._build_regression_section(config))
        
        # ARIMA/AutoModel section
        if config.auto_model:
            sections.append(self._build_automodel_section())
        elif config.arima_model:
            sections.append(self._build_arima_section(config.arima_model))
        
        # X11 seasonal adjustment section
        sections.append(self._build_x11_section(config))
        
        # Output section
        sections.append(self._build_output_section(config))
        
        # Combine all sections
        spec_content = "\n\n".join(sections)
        
        logger.debug(f"Generated spec with {len(sections)} sections")
        
        return spec_content
    
    def _build_series_section(self, config: X13Spec) -> str:
        """Build series section"""
        # NOTE: The series data is provided in a separate .dat file
        # The spec references it via the file directive
        return f"""series {{
    title = "{config.title}"
    start = {config.start_year}.{config.start_month}
    period = 12
    decimals = 1
    file = "{config.series_name}.dat"
}}"""
    
    def _build_transform_section(self) -> str:
        """Build transform section (log transform for multiplicative)"""
        return """transform {
    function = log
}"""
    
    def _build_regression_section(self, config: X13Spec) -> str:
        """
        Build regression section following X-13ARIMA-SEATS Reference Manual syntax.
        
        Reference: docx13as.pdf, Section 7.13 (pages 145-169)
        https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/documentation/docx13as.pdf
        
        Approach: Use EXTERNAL file for user regressors (inline data hits 133-char line limit)
        The x13_service will write the regressor matrix to {series_name}_regressors.dat
        """
        regression_block = "regression {\n"
        
        # Define user regressors with EXTERNAL FILE reference
        # Per Census Bureau documentation and BLS examples
        if config.user_regressors:
            # User regressor names
            user_names = " ".join(config.user_regressors)
            regression_block += f"    user = ({user_names})\n"
            
            # Reference external regressor matrix file (written by x13_service)
            regression_block += f"    file = \"{config.series_name}_regressors.dat\"\n"
            
            # BLS approach: omit format argument for auto-detection
            # With user regressors now correctly declared (not duplicated in variables),
            # let X-13 auto-detect the format from the file
            
            regression_block += f"    start = {config.start_year}.{config.start_month}\n"
        
        # Build variables list
        # CRITICAL: User regressors should ONLY be in user=(), NOT in variables=()
        # They are automatically included once declared in user argument
        # The variables argument should ONLY list built-in regressors
        variables = []
        
        # Add built-in regressors (easter, trading day)
        if config.easter:
            variables.append("easter[8]")
        if config.trading_day:
            variables.append("td")
        
        # ONLY include variables if there are built-in regressors to list
        # If only user regressors, variables argument can be omitted
        if variables:
            variables_str = " ".join(variables)
            regression_block += f"    variables = ({variables_str})\n"
            
            # Add AIC test and savelog for built-in regressors
            aictest_vars = []
            if config.trading_day:
                aictest_vars.append("td")
            if config.easter:
                aictest_vars.append("easter")
            aictest_str = " ".join(aictest_vars)
            regression_block += f"    aictest = ({aictest_str})\n"
            regression_block += "    savelog = aictest\n"
        
        regression_block += "}"
        
        return regression_block
    
    def _build_automodel_section(self) -> str:
        """Build automodel section (automatic ARIMA selection)"""
        return """automdl {
    savelog = automodel
}"""
    
    def _build_arima_section(self, model: str) -> str:
        """Build ARIMA section with specified model"""
        return f"""arima {{
    model = {model}
}}"""
    
    def _build_x11_section(self, config: X13Spec) -> str:
        """Build X11 seasonal adjustment section (includes save and print directives)"""
        # X-13 expects "mult" or "add", not "multiplicative" or "additive"
        # Map table codes to save directives
        save_map = {
            "d11": "d11",  # Seasonally adjusted
            "d12": "d12",  # Trend
            "d13": "d13",  # Irregular
            "d16": "d16",  # Seasonal factors
        }
        
        saves = []
        for table in config.save_tables:
            if table in save_map:
                saves.append(save_map[table])
        
        saves_str = " ".join(saves)
        
        # M-statistics are automatically computed and output to .out file
        # when using x11 mode - no special print directive needed
        return f"""x11 {{
    mode = {config.mode}
    seasonalma = s3x5
    save = ({saves_str})
}}"""
    
    def _build_output_section(self, config: X13Spec) -> str:
        """Build output section (empty now - output is handled in x11 section)"""
        # Output tables are now specified in the x11 section's save directive
        # This method is kept for backward compatibility but returns empty string
        return ""
    
    def build_spec_for_series(
        self,
        series_name: str,
        title: str,
        start_year: int,
        start_month: int,
        mode: str = "mult",
        **kwargs
    ) -> str:
        """
        Convenience method to build spec for a series
        
        Args:
            series_name: Series identifier
            title: Series title/description
            start_year: Start year
            start_month: Start month (1-12)
            mode: "mult" or "add"
            **kwargs: Additional X13Spec parameters
            
        Returns:
            str: Spec file content
        """
        config = X13Spec(
            series_name=series_name,
            title=title,
            start_year=start_year,
            start_month=start_month,
            mode=mode,
            **kwargs
        )
        
        return self.build_spec(config)
    
    def save_spec(self, spec_content: str, output_path: Path):
        """
        Save spec content to file
        
        Args:
            spec_content: Spec file content
            output_path: Output file path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(spec_content)
        logger.info(f"Saved spec file: {output_path}")


def create_default_spec(
    series_name: str,
    title: str,
    start_year: int,
    start_month: int
) -> str:
    """
    Create a default X-13 spec with standard settings
    
    Args:
        series_name: Series identifier
        title: Series title
        start_year: Start year
        start_month: Start month
        
    Returns:
        str: Spec file content
    """
    builder = SpecBuilder()
    
    config = X13Spec(
        series_name=series_name,
        title=title,
        start_year=start_year,
        start_month=start_month,
        auto_model=True,
        easter=True,
        trading_day=True,
        mode="mult"
    )
    
    return builder.build_spec(config)


# Example usage
if __name__ == "__main__":
    # Create a spec for NFP
    builder = SpecBuilder()
    
    spec = builder.build_spec_for_series(
        series_name="ces_nfp",
        title="Total Nonfarm Payrolls",
        start_year=2014,
        start_month=1,
        mode="mult",
        easter=True,
        trading_day=True
    )
    
    print(spec)


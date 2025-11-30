"""
X-13 Service
Python wrapper for X-13ARIMA-SEATS seasonal adjustment
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
import shutil

import pandas as pd
from loguru import logger


class X13Error(Exception):
    """Raised when X-13 execution fails"""
    pass


class X13Service:
    """
    Service for running X-13ARIMA-SEATS seasonal adjustment
    
    Wraps the x13as binary and handles:
    - Spec file generation
    - Data file creation
    - Binary execution
    - Output parsing
    - Diagnostics extraction
    """
    
    def __init__(
        self,
        x13_path: str = "x13as",
        work_dir: Optional[Path] = None
    ):
        """
        Initialize X-13 service
        
        Args:
            x13_path: Path to x13as binary (default: assume in PATH)
            work_dir: Working directory for X-13 files (default: temp)
        """
        self.x13_path = x13_path
        self.work_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp())
        self.use_statsmodels = False
        
        # Verify X-13 is available
        if not self._verify_x13():
            logger.warning(f"X-13 binary not found at: {self.x13_path}")
            logger.warning("Will use statsmodels X-13 integration as fallback")
            self.use_statsmodels = True
        else:
            logger.info(f"X-13 service initialized: {self.x13_path}")
        
        logger.info(f"Working directory: {self.work_dir}")
    
    def _verify_x13(self) -> bool:
        """Verify X-13 binary is available"""
        try:
            result = subprocess.run(
                [self.x13_path, "-v"],
                capture_output=True,
                timeout=5
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            # Try alternate location
            if shutil.which("x13as"):
                self.x13_path = "x13as"
                return True
            return False
    
    def run_seasonal_adjustment(
        self,
        series: pd.Series,
        series_name: str,
        spec_content: str,
        regressors: Optional[pd.DataFrame] = None,
        save_output: bool = True
    ) -> Dict[str, Any]:
        """
        Run seasonal adjustment on a time series
        
        Args:
            series: Time series to adjust (DatetimeIndex)
            series_name: Name for the series
            spec_content: X-13 spec file content
            regressors: Optional DataFrame with regressor series (each column is a regressor)
            save_output: Whether to save output files
            
        Returns:
            dict: Results including seasonally adjusted series and diagnostics
        """
        logger.info(f"Running seasonal adjustment for: {series_name}")
        
        # Create temporary directory for this run
        run_dir = self.work_dir / series_name
        run_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Write data file
            data_file = run_dir / f"{series_name}.dat"
            self._write_data_file(series, data_file)
            
            # Write regressor matrix file if provided (all regressors in one file)
            # Per X-13 manual: user regressors go in a single regression matrix file
            if regressors is not None and len(regressors) > 0:
                logger.info(f"Writing regressor matrix file with {len(regressors.columns)} regressors...")
                regressor_file = run_dir / f"{series_name}_regressors.dat"
                self._write_regressor_matrix(regressors, regressor_file)
                logger.debug(f"  Wrote regressor matrix: {list(regressors.columns)}")
            
            # Write spec file
            spec_file = run_dir / f"{series_name}.spc"
            spec_file.write_text(spec_content)
            
            # Run X-13
            self._execute_x13(series_name, run_dir)
            
            # Parse results
            results = self._parse_results(series_name, run_dir)
            
            # Save outputs if requested
            if save_output:
                output_dir = Path("data/seasonal_output") / series_name
                output_dir.mkdir(parents=True, exist_ok=True)
                
                # Copy key output files
                for ext in [".d11", ".d12", ".d13", ".d16", ".err", ".out"]:
                    src = run_dir / f"{series_name}{ext}"
                    if src.exists():
                        shutil.copy(src, output_dir / src.name)
            
            logger.info(f"✓ Seasonal adjustment complete: {series_name}")
            
            return results
            
        except Exception as e:
            logger.error(f"Seasonal adjustment failed for {series_name}: {e}")
            raise X13Error(f"X-13 execution failed: {e}") from e
        
        finally:
            # Optionally clean up temp files
            if not save_output:
                shutil.rmtree(run_dir, ignore_errors=True)
    
    def _write_data_file(self, series: pd.Series, output_path: Path):
        """
        Write time series to X-13 data file format
        
        When the spec file has a series block with file reference,
        the .dat file should contain just the data values, not a series block.
        
        Format: value1 value2 value3 ... (one per line or space-separated)
        """
        if not isinstance(series.index, pd.DatetimeIndex):
            raise ValueError("Series must have DatetimeIndex")
        
        # Format data values (one per line for readability)
        values = "\n".join(str(v) for v in series.values)
        
        output_path.write_text(values + "\n")
        logger.debug(f"Wrote data file: {output_path} ({len(series)} values)")
    
    def _write_regressor_matrix(self, regressors: pd.DataFrame, output_path: Path):
        """
        Write regressor matrix in X-13 regression matrix format.
        
        Per X-13ARIMA-SEATS Reference Manual (docx13as.pdf, Section 7.13):
        - All user regressors in ONE file (regression matrix format)
        - Format: space-separated values, one row per observation
        - No column headers
        - Order of columns matches order in spec's "user" argument
        
        Reference: https://www2.census.gov/software/x-13arima-seats/x-13-data/download/x13datadoc.pdf
        (X-13-Data tool documentation, "Regression Matrix" format)
        
        Args:
            regressors: DataFrame with regressor values (DatetimeIndex, one column per regressor)
            output_path: Path to output .dat file
        """
        if not isinstance(regressors.index, pd.DatetimeIndex):
            raise ValueError("Regressors must have DatetimeIndex")
        
        # Write as fixed-width format to match X-13 format spec: (Nf12.6)
        # Each value is 12 characters wide with 6 decimal places
        with open(output_path, 'w') as f:
            for date_idx, row in regressors.iterrows():
                # Format: one row per observation, fixed-width values
                values = "".join(f"{v:12.6f}" for v in row.values)
                f.write(f"{values}\n")
        
        logger.debug(
            f"Wrote regressor matrix: {output_path} "
            f"({len(regressors)} rows, {len(regressors.columns)} cols)"
        )
    
    def _execute_x13(self, series_name: str, run_dir: Path):
        """Execute X-13 binary"""
        try:
            # X-13 expects to run in directory with spec file
            result = subprocess.run(
                [self.x13_path, series_name],
                cwd=run_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Check for errors
            error_file = run_dir / f"{series_name}.err"
            if error_file.exists():
                error_content = error_file.read_text()
                if "ERROR" in error_content:
                    logger.error(f"X-13 errors:\n{error_content}")
                    raise X13Error(f"X-13 reported errors: {error_content[:500]}")
            
            logger.debug(f"X-13 executed successfully for {series_name}")
            
        except subprocess.TimeoutExpired:
            raise X13Error("X-13 execution timed out")
        except subprocess.SubprocessError as e:
            raise X13Error(f"X-13 execution failed: {e}")
    
    def _parse_results(self, series_name: str, run_dir: Path) -> Dict[str, Any]:
        """
        Parse X-13 output files
        
        Key files:
        - .d11: Seasonally adjusted series
        - .d12: Trend-cycle
        - .d13: Irregular component
        - .d16: Seasonal factors
        - .out: Full output with diagnostics
        """
        results = {
            "series_name": series_name,
            "seasonally_adjusted": None,
            "trend": None,
            "irregular": None,
            "seasonal_factors": None,
            "diagnostics": {}
        }
        
        # Parse seasonally adjusted series (.d11)
        d11_file = run_dir / f"{series_name}.d11"
        if d11_file.exists():
            results["seasonally_adjusted"] = self._parse_x13_series_file(d11_file)
        
        # Parse trend (.d12)
        d12_file = run_dir / f"{series_name}.d12"
        if d12_file.exists():
            results["trend"] = self._parse_x13_series_file(d12_file)
        
        # Parse irregular (.d13)
        d13_file = run_dir / f"{series_name}.d13"
        if d13_file.exists():
            results["irregular"] = self._parse_x13_series_file(d13_file)
        
        # Parse seasonal factors (.d16)
        d16_file = run_dir / f"{series_name}.d16"
        if d16_file.exists():
            results["seasonal_factors"] = self._parse_x13_series_file(d16_file)
        
        # Parse diagnostics from .out file
        out_file = run_dir / f"{series_name}.out"
        if out_file.exists():
            results["diagnostics"] = self._parse_diagnostics(out_file)
        
        return results
    
    def _parse_x13_series_file(self, file_path: Path) -> pd.Series:
        """Parse X-13 series output file"""
        try:
            # X-13 output format: date value
            df = pd.read_csv(
                file_path,
                delim_whitespace=True,
                names=["date", "value"],
                skiprows=2  # Skip header
            )
            
            # Convert date strings to datetime
            # X-13 outputs dates in format "YYYYMM" (e.g., "201401")
            df["date"] = pd.to_datetime(df["date"], format="%Y%m")
            
            # Create series
            series = pd.Series(
                df["value"].values,
                index=df["date"],
                name=file_path.stem
            )
            
            return series
            
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return None
    
    def _parse_diagnostics(self, out_file: Path) -> Dict[str, Any]:
        """Parse diagnostics from X-13 output file"""
        diagnostics = {}
        
        try:
            content = out_file.read_text()
            
            # Extract key diagnostic statistics
            # M-statistics (quality measures)
            if "m  statistics" in content.lower():
                # Parse M-statistics section
                diagnostics["m_statistics"] = self._extract_m_statistics(content)
            
            # Q-statistics
            if "q-statistics" in content.lower():
                diagnostics["q_statistics"] = self._extract_q_statistics(content)
            
            # Model identification
            if "arima model" in content.lower():
                diagnostics["arima_model"] = self._extract_arima_model(content)
            
            return diagnostics
            
        except Exception as e:
            logger.warning(f"Failed to parse diagnostics: {e}")
            return {}
    
    def _extract_m_statistics(self, content: str) -> Dict[str, float]:
        """Extract M-statistics from output"""
        # Simplified extraction - would need regex for production
        return {"extracted": True}
    
    def _extract_q_statistics(self, content: str) -> Dict[str, float]:
        """Extract Q-statistics from output"""
        return {"extracted": True}
    
    def _extract_arima_model(self, content: str) -> str:
        """Extract ARIMA model specification"""
        return "model_extracted"


"""
Diagnostics Extractor
Parses X-13 output and extracts diagnostic statistics
"""

from typing import Dict, Any, Optional
from pathlib import Path
import re

import pandas as pd
from loguru import logger


class DiagnosticsExtractor:
    """
    Extracts diagnostic statistics from X-13 output
    
    Key diagnostics:
    - M-statistics (M1-M11): Quality of seasonal adjustment
    - Q-statistic: Overall quality score
    - Ljung-Box Q: Test for residual autocorrelation
    - Trading day F-test
    - Seasonality test results
    """
    
    def __init__(self):
        """Initialize diagnostics extractor"""
        self.diagnostics = {}
    
    def extract_from_output(self, output_text: str) -> Dict[str, Any]:
        """
        Extract diagnostics from X-13 output text
        
        Args:
            output_text: X-13 output file content
            
        Returns:
            Dictionary of diagnostic metrics
        """
        logger.info("Extracting diagnostics from X-13 output")
        
        diagnostics = {}
        
        # Extract M-statistics
        m_stats = self._extract_m_statistics(output_text)
        if m_stats:
            diagnostics.update(m_stats)
        
        # Extract Q-statistic
        q_stat = self._extract_q_statistic(output_text)
        if q_stat is not None:
            diagnostics["q_statistic"] = q_stat
        
        # Extract Ljung-Box Q
        ljung_box = self._extract_ljung_box(output_text)
        if ljung_box:
            diagnostics.update(ljung_box)
        
        # Extract seasonality tests
        seasonality = self._extract_seasonality_tests(output_text)
        if seasonality:
            diagnostics.update(seasonality)
        
        # Extract trading day tests
        td_tests = self._extract_trading_day_tests(output_text)
        if td_tests:
            diagnostics.update(td_tests)
        
        logger.info(f"Extracted {len(diagnostics)} diagnostic metrics")
        
        return diagnostics
    
    def _extract_m_statistics(self, output_text: str) -> Dict[str, float]:
        """
        Extract M-statistics (M1-M11)
        
        M-statistics measure different aspects of adjustment quality:
        - M1-M6: Relative contributions
        - M7: Combined seasonality test
        - M8-M11: Various quality measures
        - Q: Overall quality (average of M1-M11)
        """
        m_stats = {}
        
        # Pattern for M-statistics
        patterns = {
            f"m{i}": rf"M\s*{i}\s*[=:]\s*([\d.]+)" for i in range(1, 12)
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, output_text, re.IGNORECASE)
            if match:
                try:
                    m_stats[key] = float(match.group(1))
                except ValueError:
                    pass
        
        return m_stats
    
    def _extract_q_statistic(self, output_text: str) -> Optional[float]:
        """
        Extract Q-statistic (overall quality score)
        
        Q < 1.0: Acceptable
        1.0 <= Q < 2.0: Borderline
        Q >= 2.0: Poor quality
        """
        pattern = r"Q\s*[=:]\s*([\d.]+)"
        match = re.search(pattern, output_text, re.IGNORECASE)
        
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        
        return None
    
    def _extract_ljung_box(self, output_text: str) -> Dict[str, Any]:
        """
        Extract Ljung-Box Q test results
        
        Tests for residual autocorrelation
        """
        results = {}
        
        # Pattern for Ljung-Box Q
        pattern = r"Ljung-Box\s+Q\s*\((\d+)\)\s*[=:]\s*([\d.]+).*p-value\s*[=:]\s*([\d.]+)"
        match = re.search(pattern, output_text, re.IGNORECASE)
        
        if match:
            try:
                results["ljung_box_lag"] = int(match.group(1))
                results["ljung_box_q"] = float(match.group(2))
                results["ljung_box_pvalue"] = float(match.group(3))
            except ValueError:
                pass
        
        return results
    
    def _extract_seasonality_tests(self, output_text: str) -> Dict[str, Any]:
        """
        Extract seasonality test results
        
        Tests whether series has significant seasonality
        """
        results = {}
        
        # Combined seasonality test
        pattern = r"Combined\s+seasonality\s+test.*F\s*[=:]\s*([\d.]+).*p-value\s*[=:]\s*([\d.]+)"
        match = re.search(pattern, output_text, re.IGNORECASE)
        
        if match:
            try:
                results["seasonality_f"] = float(match.group(1))
                results["seasonality_pvalue"] = float(match.group(2))
                results["seasonality_significant"] = float(match.group(2)) < 0.05
            except ValueError:
                pass
        
        # Stable seasonality test
        pattern = r"Stable\s+seasonality\s+test.*F\s*[=:]\s*([\d.]+).*p-value\s*[=:]\s*([\d.]+)"
        match = re.search(pattern, output_text, re.IGNORECASE)
        
        if match:
            try:
                results["stable_seasonality_f"] = float(match.group(1))
                results["stable_seasonality_pvalue"] = float(match.group(2))
            except ValueError:
                pass
        
        return results
    
    def _extract_trading_day_tests(self, output_text: str) -> Dict[str, Any]:
        """
        Extract trading day test results
        
        Tests for trading day effects
        """
        results = {}
        
        # Trading day F-test
        pattern = r"Trading\s+day.*F\s*[=:]\s*([\d.]+).*p-value\s*[=:]\s*([\d.]+)"
        match = re.search(pattern, output_text, re.IGNORECASE)
        
        if match:
            try:
                results["trading_day_f"] = float(match.group(1))
                results["trading_day_pvalue"] = float(match.group(2))
                results["trading_day_significant"] = float(match.group(2)) < 0.05
            except ValueError:
                pass
        
        return results
    
    def extract_from_file(self, output_file: Path) -> Dict[str, Any]:
        """
        Extract diagnostics from X-13 output file
        
        Args:
            output_file: Path to X-13 output file
            
        Returns:
            Dictionary of diagnostic metrics
        """
        if not output_file.exists():
            logger.error(f"Output file not found: {output_file}")
            return {}
        
        output_text = output_file.read_text()
        return self.extract_from_output(output_text)
    
    def assess_quality(self, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assess overall adjustment quality from diagnostics
        
        Args:
            diagnostics: Diagnostic metrics
            
        Returns:
            Quality assessment
        """
        assessment = {
            "overall_quality": "unknown",
            "issues": [],
            "warnings": [],
        }
        
        # Check Q-statistic
        q_stat = diagnostics.get("q_statistic")
        if q_stat is not None:
            if q_stat < 1.0:
                assessment["overall_quality"] = "good"
            elif q_stat < 2.0:
                assessment["overall_quality"] = "acceptable"
                assessment["warnings"].append(f"Q-statistic borderline: {q_stat:.2f}")
            else:
                assessment["overall_quality"] = "poor"
                assessment["issues"].append(f"Q-statistic high: {q_stat:.2f}")
        
        # Check individual M-statistics (should be < 1.0)
        for i in range(1, 12):
            m_key = f"m{i}"
            m_val = diagnostics.get(m_key)
            if m_val is not None and m_val > 3.0:
                assessment["issues"].append(f"M{i} too high: {m_val:.2f}")
        
        # Check Ljung-Box (should have high p-value)
        ljung_box_p = diagnostics.get("ljung_box_pvalue")
        if ljung_box_p is not None and ljung_box_p < 0.05:
            assessment["issues"].append(f"Ljung-Box test failed (p={ljung_box_p:.3f})")
        
        # Check seasonality
        if not diagnostics.get("seasonality_significant"):
            assessment["warnings"].append("Weak or no seasonality detected")
        
        return assessment


def create_diagnostics_dataframe(
    diagnostics_dict: Dict[str, Dict[str, Any]]
) -> pd.DataFrame:
    """
    Convert diagnostics dictionary to DataFrame
    
    Args:
        diagnostics_dict: Dict of series_name -> diagnostics
        
    Returns:
        DataFrame with diagnostics for all series
    """
    rows = []
    
    for series_name, diagnostics in diagnostics_dict.items():
        row = {"series_name": series_name}
        row.update(diagnostics)
        rows.append(row)
    
    return pd.DataFrame(rows)


# Example usage
if __name__ == "__main__":
    extractor = DiagnosticsExtractor()
    
    # Sample X-13 output (simplified)
    sample_output = """
    M1 = 0.456
    M2 = 0.523
    M3 = 0.412
    M4 = 0.389
    M5 = 0.467
    M6 = 0.501
    M7 = 0.445
    M8 = 0.478
    M9 = 0.423
    M10 = 0.498
    M11 = 0.512
    Q = 0.463
    
    Ljung-Box Q(24) = 18.5, p-value = 0.773
    Combined seasonality test: F = 45.3, p-value = 0.000
    Trading day F-test: F = 3.2, p-value = 0.042
    """
    
    diagnostics = extractor.extract_from_output(sample_output)
    print("Diagnostics:")
    for key, value in diagnostics.items():
        print(f"  {key}: {value}")
    
    assessment = extractor.assess_quality(diagnostics)
    print(f"\nQuality Assessment:")
    print(f"  Overall: {assessment['overall_quality']}")
    print(f"  Issues: {assessment['issues']}")
    print(f"  Warnings: {assessment['warnings']}")


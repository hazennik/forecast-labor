"""
Validation Report Generator
Creates HTML and PDF reports from validation results
"""

from typing import List, Optional
from pathlib import Path
from datetime import datetime

import pandas as pd
from loguru import logger

from etl.validators.base_validator import ValidationResult, ValidationSeverity


class ValidationReportGenerator:
    """
    Generates validation reports in multiple formats

    Formats:
    - HTML: Interactive report with styling
    - PDF: Printable report (requires weasyprint)
    - CSV: Machine-readable summary
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize report generator

        Args:
            output_dir: Output directory for reports
        """
        self.output_dir = Path(output_dir) if output_dir else Path("data/reports/validation")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_html_report(
        self,
        results: List[ValidationResult],
        title: str = "Data Validation Report",
        output_file: Optional[Path] = None,
    ) -> Path:
        """
        Generate HTML validation report

        Args:
            results: List of validation results
            title: Report title
            output_file: Output file path

        Returns:
            Path to generated report
        """
        logger.info(f"Generating HTML validation report: {title}")

        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.output_dir / f"validation_report_{timestamp}.html"

        # Build HTML content
        html_content = self._build_html_report(results, title)

        # Write to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html_content)

        logger.info(f"HTML report saved: {output_file}")

        return output_file

    def generate_pdf_report(
        self,
        results: List[ValidationResult],
        title: str = "Data Validation Report",
        output_file: Optional[Path] = None,
    ) -> Path:
        """
        Generate PDF validation report

        Args:
            results: List of validation results
            title: Report title
            output_file: Output file path

        Returns:
            Path to generated report
        """
        logger.info(f"Generating PDF validation report: {title}")

        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.output_dir / f"validation_report_{timestamp}.pdf"

        # Generate HTML first
        html_content = self._build_html_report(results, title)

        # Convert to PDF
        try:
            from weasyprint import HTML

            HTML(string=html_content).write_pdf(str(output_file))
            logger.info(f"PDF report saved: {output_file}")
        except ImportError:
            logger.warning("weasyprint not installed - falling back to HTML only")
            # Save as HTML instead
            output_file = output_file.with_suffix(".html")
            output_file.write_text(html_content)
            logger.info(f"HTML report saved (PDF unavailable): {output_file}")

        return output_file

    def generate_csv_summary(
        self, results: List[ValidationResult], output_file: Optional[Path] = None
    ) -> Path:
        """
        Generate CSV summary of validation results

        Args:
            results: List of validation results
            output_file: Output file path

        Returns:
            Path to generated report
        """
        logger.info("Generating CSV validation summary")

        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.output_dir / f"validation_summary_{timestamp}.csv"

        # Convert to DataFrame
        df = self._results_to_dataframe(results)

        # Write to CSV
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_file, index=False)

        logger.info(f"CSV summary saved: {output_file}")

        return output_file

    def _build_html_report(self, results: List[ValidationResult], title: str) -> str:
        """Build HTML report content"""

        # Calculate summary statistics
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed

        # Group by severity
        by_severity = {}
        for severity in ValidationSeverity:
            count = sum(1 for r in results if r.severity == severity)
            by_severity[severity.value] = count

        # Group by validator
        by_validator = {}
        for result in results:
            validator = result.validator_name
            if validator not in by_validator:
                by_validator[validator] = {"passed": 0, "failed": 0}
            if result.passed:
                by_validator[validator]["passed"] += 1
            else:
                by_validator[validator]["failed"] += 1

        # Build HTML
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .summary-card {{
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .summary-card.passed {{
            background: #e8f5e9;
            border: 2px solid #4CAF50;
        }}
        .summary-card.failed {{
            background: #ffebee;
            border: 2px solid #f44336;
        }}
        .summary-card.info {{
            background: #e3f2fd;
            border: 2px solid #2196F3;
        }}
        .summary-card h3 {{
            margin: 0;
            font-size: 36px;
            font-weight: bold;
        }}
        .summary-card p {{
            margin: 5px 0 0 0;
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f5f5f5;
            font-weight: 600;
            color: #333;
        }}
        tr:hover {{
            background: #f9f9f9;
        }}
        .severity-CRITICAL {{
            color: #d32f2f;
            font-weight: bold;
        }}
        .severity-ERROR {{
            color: #f44336;
        }}
        .severity-WARNING {{
            color: #ff9800;
        }}
        .severity-INFO {{
            color: #2196F3;
        }}
        .passed {{
            color: #4CAF50;
            font-weight: bold;
        }}
        .failed {{
            color: #f44336;
            font-weight: bold;
        }}
        .timestamp {{
            color: #999;
            font-size: 0.9em;
        }}
        .validator-summary {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 4px;
            margin: 10px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <h2>Summary</h2>
        <div class="summary">
            <div class="summary-card passed">
                <h3>{passed}</h3>
                <p>Passed</p>
            </div>
            <div class="summary-card failed">
                <h3>{failed}</h3>
                <p>Failed</p>
            </div>
            <div class="summary-card info">
                <h3>{total}</h3>
                <p>Total Checks</p>
            </div>
        </div>
        
        <h2>By Severity</h2>
        <div class="validator-summary">
            <table>
                <tr>
                    <th>Severity</th>
                    <th>Count</th>
                </tr>
                {"".join(f'<tr><td class="severity-{sev}">{sev}</td><td>{count}</td></tr>' 
                         for sev, count in by_severity.items() if count > 0)}
            </table>
        </div>
        
        <h2>By Validator</h2>
        <div class="validator-summary">
            <table>
                <tr>
                    <th>Validator</th>
                    <th>Passed</th>
                    <th>Failed</th>
                    <th>Total</th>
                </tr>
                {"".join(f'''<tr>
                    <td>{validator}</td>
                    <td class="passed">{stats["passed"]}</td>
                    <td class="failed">{stats["failed"]}</td>
                    <td>{stats["passed"] + stats["failed"]}</td>
                </tr>''' for validator, stats in by_validator.items())}
            </table>
        </div>
        
        <h2>Detailed Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Validator</th>
                    <th>Check</th>
                    <th>Status</th>
                    <th>Severity</th>
                    <th>Message</th>
                    <th>Timestamp</th>
                </tr>
            </thead>
            <tbody>
                {"".join(self._result_to_html_row(r) for r in results)}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

        return html

    def _result_to_html_row(self, result: ValidationResult) -> str:
        """Convert validation result to HTML table row"""
        status_class = "passed" if result.passed else "failed"
        status_text = "✓ PASS" if result.passed else "✗ FAIL"

        return f"""
                <tr>
                    <td>{result.validator_name}</td>
                    <td>{result.rule_name}</td>
                    <td class="{status_class}">{status_text}</td>
                    <td class="severity-{result.severity.value}">{result.severity.value}</td>
                    <td>{result.message}</td>
                    <td class="timestamp">{result.timestamp.strftime("%Y-%m-%d %H:%M:%S")}</td>
                </tr>
"""

    def _results_to_dataframe(self, results: List[ValidationResult]) -> pd.DataFrame:
        """Convert validation results to DataFrame"""
        data = []

        for result in results:
            data.append(
                {
                    "validator": result.validator_name,
                    "check": result.rule_name,
                    "passed": result.passed,
                    "severity": result.severity.value,
                    "message": result.message,
                    "timestamp": result.timestamp.isoformat(),
                    "details": str(result.details) if result.details else "",
                }
            )

        return pd.DataFrame(data)


# Example usage
if __name__ == "__main__":
    from etl.validators.base_validator import ValidationStatus

    # Create sample validation results
    sample_results = [
        ValidationResult(
            validator_name="SchemaValidator",
            rule_name="required_columns",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.ERROR,
            message="All required columns present",
        ),
        ValidationResult(
            validator_name="FreshnessValidator",
            rule_name="data_age",
            status=ValidationStatus.FAILED,
            severity=ValidationSeverity.WARNING,
            message="Data is 3 days old (threshold: 2 days)",
        ),
        ValidationResult(
            validator_name="QualityValidator",
            rule_name="missing_values",
            status=ValidationStatus.PASSED,
            severity=ValidationSeverity.ERROR,
            message="Missing values within acceptable range (2.3%)",
        ),
    ]

    # Generate reports
    generator = ValidationReportGenerator()

    html_path = generator.generate_html_report(sample_results)
    print(f"HTML report: {html_path}")

    csv_path = generator.generate_csv_summary(sample_results)
    print(f"CSV summary: {csv_path}")

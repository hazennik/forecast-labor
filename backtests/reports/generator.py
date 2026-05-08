"""HTML and Markdown report generation for Phase 6 backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
import json

from loguru import logger


@dataclass(frozen=True)
class ReportSection:
    """A section in a generated backtest report."""

    title: str
    summary: str
    items: List[str] = field(default_factory=list)
    table: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate section content."""
        if not self.title.strip():
            raise ValueError("ReportSection title cannot be empty")
        if not self.summary.strip():
            raise ValueError("ReportSection summary cannot be empty")


@dataclass(frozen=True)
class BacktestReport:
    """Generated report content and serializable metadata."""

    title: str
    generated_at: str
    sections: List[ReportSection]
    metadata: Dict[str, Any]
    html: str
    markdown: str
    pdf: bytes

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable report payload."""
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "metadata": self.metadata,
            "sections": [
                {
                    "title": section.title,
                    "summary": section.summary,
                    "items": section.items,
                    "table": section.table,
                }
                for section in self.sections
            ],
        }


class BacktestReportGenerator:
    """Generate Phase 6 backtest reports from validation payloads."""

    def generate(
        self,
        *,
        title: str = "Phase 6 Backtest Report",
        performance_report: Optional[Mapping[str, Any]] = None,
        health_reports: Optional[Iterable[Mapping[str, Any]]] = None,
        accuracy_gates: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> BacktestReport:
        """Generate a report from available Phase 6 validation payloads.

        Args:
            title: Report title.
            performance_report: Performance validation report payload.
            health_reports: Optional model health report payloads.
            accuracy_gates: Optional accuracy gate payload.
            metadata: Optional report metadata.

        Returns:
            BacktestReport with HTML and Markdown content.
        """
        if not title.strip():
            raise ValueError("Report title cannot be empty")

        generated_at = datetime.now(timezone.utc).isoformat()
        health_payloads = list(health_reports or [])
        sections = [
            self._executive_summary_section(performance_report, health_payloads, accuracy_gates),
            self._performance_section(performance_report),
            self._health_section(health_payloads),
            self._accuracy_section(accuracy_gates),
        ]
        clean_metadata = dict(metadata or {})
        clean_metadata.setdefault("phase", "6.4.1")
        clean_metadata.setdefault("report_type", "backtest_summary")

        markdown = self._render_markdown(title, generated_at, sections, clean_metadata)
        html = self._render_html(title, generated_at, sections, clean_metadata)
        pdf = self._render_pdf(title, generated_at, sections, clean_metadata)

        logger.info(
            "backtest_report_generated",
            title=title,
            n_sections=len(sections),
            metadata=clean_metadata,
        )
        return BacktestReport(
            title=title,
            generated_at=generated_at,
            sections=sections,
            metadata=clean_metadata,
            html=html,
            markdown=markdown,
            pdf=pdf,
        )

    def write(
        self,
        report: BacktestReport,
        output_dir: Path,
        *,
        stem: str = "phase_6_backtest_report",
    ) -> Dict[str, Path]:
        """Write report HTML, Markdown, and JSON files.

        Args:
            report: Generated report.
            output_dir: Directory to write into.
            stem: File stem for all outputs.

        Returns:
            Mapping of output type to file path.
        """
        if not stem.strip():
            raise ValueError("stem cannot be empty")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = {
            "html": output_dir / f"{stem}.html",
            "markdown": output_dir / f"{stem}.md",
            "pdf": output_dir / f"{stem}.pdf",
            "json": output_dir / f"{stem}.json",
        }
        paths["html"].write_text(report.html, encoding="utf-8")
        paths["markdown"].write_text(report.markdown, encoding="utf-8")
        paths["pdf"].write_bytes(report.pdf)
        paths["json"].write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")

        logger.info("backtest_report_written", paths={key: str(path) for key, path in paths.items()})
        return paths

    def _executive_summary_section(
        self,
        performance_report: Optional[Mapping[str, Any]],
        health_reports: Optional[Iterable[Mapping[str, Any]]],
        accuracy_gates: Optional[Mapping[str, Any]],
    ) -> ReportSection:
        """Build executive summary section."""
        performance_passed = _passed(performance_report)
        health_payloads = list(health_reports or [])
        health_failures = sum(1 for report in health_payloads if not bool(report.get("passed", True)))
        accuracy_passed = _passed(accuracy_gates)

        items = [
            f"Performance validation: {'PASS' if performance_passed else 'FAIL'}",
            f"Model health reports: {len(health_payloads)} checked, {health_failures} critical failure(s)",
            f"Accuracy gates: {'PASS' if accuracy_passed else 'PENDING/FAIL'}",
        ]
        return ReportSection(
            title="Executive Summary",
            summary="High-level status of Phase 6 backtest validation artifacts.",
            items=items,
        )

    def _performance_section(
        self,
        performance_report: Optional[Mapping[str, Any]],
    ) -> ReportSection:
        """Build performance summary section."""
        if not performance_report:
            return ReportSection(
                title="Performance Validation",
                summary="No performance validation payload was provided.",
                items=["Status: pending"],
            )

        pipeline = performance_report.get("pipeline_summary", {})
        findings = performance_report.get("findings", [])
        table = [
            {
                "Metric": "Training time",
                "Value": f"{float(pipeline.get('training_time_sec', 0.0)):.6f}s",
            },
            {
                "Metric": "Prediction latency",
                "Value": f"{float(pipeline.get('prediction_latency_ms', 0.0)):.3f}ms",
            },
            {
                "Metric": "Memory",
                "Value": f"{float(pipeline.get('memory_mb', 0.0)):.3f}MB",
            },
            {
                "Metric": "Included models",
                "Value": ", ".join(pipeline.get("included_models", [])),
            },
            {
                "Metric": "Excluded models",
                "Value": ", ".join(pipeline.get("excluded_models", [])),
            },
        ]
        warning_items = [
            f"{finding.get('check_name')}: {finding.get('message')}"
            for finding in findings
            if finding.get("severity") in {"warning", "critical"}
        ]
        return ReportSection(
            title="Performance Validation",
            summary="SLA status and bottlenecks for the current production-candidate pipeline.",
            items=warning_items or ["No performance warnings or critical findings."],
            table=table,
        )

    def _health_section(
        self,
        health_reports: Optional[Iterable[Mapping[str, Any]]],
    ) -> ReportSection:
        """Build model health section."""
        reports = list(health_reports or [])
        if not reports:
            return ReportSection(
                title="Model Health",
                summary="No model health reports were provided.",
                items=["Status: pending"],
            )

        table = []
        items = []
        for report in reports:
            issues = report.get("issues", [])
            critical_count = sum(1 for issue in issues if issue.get("severity") == "critical")
            warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
            table.append(
                {
                    "Model": report.get("model_name", "unknown"),
                    "Status": "PASS" if report.get("passed", False) else "FAIL",
                    "Warnings": warning_count,
                    "Critical": critical_count,
                }
            )
            items.extend(
                f"{report.get('model_name', 'unknown')}: {issue.get('check_name')} - {issue.get('message')}"
                for issue in issues
                if issue.get("severity") in {"warning", "critical"}
            )
        return ReportSection(
            title="Model Health",
            summary="Health checks for model runs and known Phase 6 monitoring risks.",
            items=items or ["No health warnings or critical findings."],
            table=table,
        )

    def _accuracy_section(self, accuracy_gates: Optional[Mapping[str, Any]]) -> ReportSection:
        """Build accuracy gate section."""
        if not accuracy_gates:
            return ReportSection(
                title="Accuracy Gates",
                summary="Accuracy gate validation is scheduled for Phase 6.4.2.",
                items=["Status: pending Phase 6.4.2 model selection and gate validation."],
            )

        gates = accuracy_gates.get("gates", [])
        table = [
            {
                "Gate": gate.get("name", "unknown"),
                "Observed": gate.get("observed", "n/a"),
                "Threshold": gate.get("threshold", "n/a"),
                "Status": "PASS" if gate.get("passed", False) else "FAIL",
            }
            for gate in gates
        ]
        failed = [gate for gate in gates if not gate.get("passed", False)]
        return ReportSection(
            title="Accuracy Gates",
            summary="Deployment gate validation against configured accuracy targets.",
            items=[f"{len(failed)} failing gate(s)."] if failed else ["All provided gates passed."],
            table=table,
        )

    def _render_markdown(
        self,
        title: str,
        generated_at: str,
        sections: Iterable[ReportSection],
        metadata: Mapping[str, Any],
    ) -> str:
        """Render report as Markdown."""
        lines = [f"# {title}", "", f"Generated: `{generated_at}`", ""]
        if metadata:
            lines.extend(["## Metadata", ""])
            for key, value in metadata.items():
                lines.append(f"- `{key}`: `{value}`")
            lines.append("")

        for section in sections:
            lines.extend([f"## {section.title}", "", section.summary, ""])
            for item in section.items:
                lines.append(f"- {item}")
            if section.items:
                lines.append("")
            if section.table:
                headers = list(section.table[0].keys())
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("| " + " | ".join("---" for _ in headers) + " |")
                for row in section.table:
                    lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _render_html(
        self,
        title: str,
        generated_at: str,
        sections: Iterable[ReportSection],
        metadata: Mapping[str, Any],
    ) -> str:
        """Render report as standalone HTML."""
        body = [
            "<!doctype html>",
            "<html>",
            "<head>",
            "  <meta charset=\"utf-8\">",
            f"  <title>{escape(title)}</title>",
            "  <style>body{font-family:Arial,sans-serif;margin:2rem;line-height:1.45}"
            "table{border-collapse:collapse;margin:1rem 0;width:100%}"
            "th,td{border:1px solid #ddd;padding:.45rem;text-align:left}"
            "th{background:#f5f5f5}.meta{color:#555}</style>",
            "</head>",
            "<body>",
            f"<h1>{escape(title)}</h1>",
            f"<p class=\"meta\">Generated: <code>{escape(generated_at)}</code></p>",
        ]
        if metadata:
            body.append("<h2>Metadata</h2><ul>")
            for key, value in metadata.items():
                body.append(f"<li><code>{escape(str(key))}</code>: <code>{escape(str(value))}</code></li>")
            body.append("</ul>")

        for section in sections:
            body.append(f"<h2>{escape(section.title)}</h2>")
            body.append(f"<p>{escape(section.summary)}</p>")
            if section.items:
                body.append("<ul>")
                for item in section.items:
                    body.append(f"<li>{escape(item)}</li>")
                body.append("</ul>")
            if section.table:
                headers = list(section.table[0].keys())
                body.append("<table><thead><tr>")
                body.extend(f"<th>{escape(str(header))}</th>" for header in headers)
                body.append("</tr></thead><tbody>")
                for row in section.table:
                    body.append("<tr>")
                    body.extend(f"<td>{escape(str(row.get(header, '')))}</td>" for header in headers)
                    body.append("</tr>")
                body.append("</tbody></table>")

        body.extend(["</body>", "</html>"])
        return "\n".join(body) + "\n"

    def _render_pdf(
        self,
        title: str,
        generated_at: str,
        sections: Iterable[ReportSection],
        metadata: Mapping[str, Any],
    ) -> bytes:
        """Render a simple PDF summary using built-in PDF primitives."""
        lines = [title, f"Generated: {generated_at}", ""]
        if metadata:
            lines.append("Metadata")
            lines.extend(f"{key}: {value}" for key, value in metadata.items())
            lines.append("")

        for section in sections:
            lines.extend([section.title, section.summary])
            lines.extend(f"- {item}" for item in section.items)
            for row in section.table:
                lines.append(" | ".join(f"{key}: {value}" for key, value in row.items()))
            lines.append("")

        wrapped_lines: List[str] = []
        for line in lines:
            wrapped_lines.extend(_wrap_pdf_line(line, width=92))

        lines_per_page = 52
        pages = [
            wrapped_lines[index : index + lines_per_page]
            for index in range(0, len(wrapped_lines), lines_per_page)
        ] or [[]]
        font_id = 3 + len(pages) * 2
        page_refs = [f"{3 + index * 2} 0 R" for index in range(len(pages))]
        objects = [
            "<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>",
        ]
        for index, page_lines in enumerate(pages):
            page_id = 3 + index * 2
            content_id = page_id + 1
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            )
            content = _pdf_content_stream(page_lines)
            objects.append(
                f"<< /Length {len(content.encode('latin-1'))} >>\n"
                f"stream\n{content}\nendstream"
            )
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

        return _build_pdf(objects)


def generate_backtest_report(
    *,
    title: str = "Phase 6 Backtest Report",
    performance_report: Optional[Mapping[str, Any]] = None,
    health_reports: Optional[Iterable[Mapping[str, Any]]] = None,
    accuracy_gates: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> BacktestReport:
    """Convenience wrapper for generating a backtest report."""
    return BacktestReportGenerator().generate(
        title=title,
        performance_report=performance_report,
        health_reports=health_reports,
        accuracy_gates=accuracy_gates,
        metadata=metadata,
    )


def _passed(payload: Optional[Mapping[str, Any]]) -> bool:
    """Interpret optional validation payload pass status."""
    if payload is None:
        return False
    return bool(payload.get("passed", False))


def _wrap_pdf_line(line: str, *, width: int) -> List[str]:
    """Wrap a line into PDF-safe text chunks."""
    clean_line = line.encode("latin-1", errors="replace").decode("latin-1")
    if not clean_line:
        return [""]
    chunks = []
    remaining = clean_line
    while len(remaining) > width:
        split_at = remaining.rfind(" ", 0, width)
        if split_at <= 0:
            split_at = width
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()
    chunks.append(remaining)
    return chunks


def _pdf_content_stream(lines: List[str]) -> str:
    """Build a PDF text content stream."""
    escaped_lines = [_escape_pdf_text(line) for line in lines]
    body = ["BT", "/F1 10 Tf", "50 760 Td", "14 TL"]
    body.extend(f"({line}) Tj T*" for line in escaped_lines)
    body.append("ET")
    return "\n".join(body)


def _escape_pdf_text(value: str) -> str:
    """Escape text for a PDF literal string."""
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(objects: List[str]) -> bytes:
    """Build a minimal valid PDF byte stream."""
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref_start = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(output)

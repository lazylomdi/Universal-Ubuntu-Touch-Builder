"""Plain-language summaries for the Markdown readiness report.

Kept independent of Qt so report parsing can be tested on headless systems.
"""
from __future__ import annotations

import re


def summarize_readiness_report(report: str, exit_code: int = 0) -> str:
    """Summarize the report's actual compatibility section without guessing."""
    text = report.strip()
    if not text:
        return (
            f"Inspection failed with exit code {exit_code}; no report content was produced."
            if exit_code else
            "No inspection report was produced. Check the technical output and try again."
        )

    title_match = re.search(r"^#\s+Ubuntu Touch readiness report:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    device = title_match.group(1).strip() if title_match else ""
    section_match = re.search(
        r"^##\s+Compatibility summary\s*$([\s\S]*?)(?=^##\s+|\Z)",
        text,
        re.MULTILINE | re.IGNORECASE,
    )
    section = section_match.group(1) if section_match else ""

    def bullet_value(label: str) -> str:
        match = re.search(
            rf"^\s*[-*]\s*\*\*{re.escape(label)}:\*\*\s*(.+?)\s*$",
            section,
            re.MULTILINE | re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    status = bullet_value("Status")
    next_step = bullet_value("Next step")
    assessment_match = re.search(r"^[-*]\s*\*\*Assessment:\*\*\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
    assessment = assessment_match.group(1).strip() if assessment_match else ""

    parts = []
    if exit_code:
        parts.append(f"Inspection finished with exit code {exit_code}; treat the report as potentially incomplete.")
    else:
        parts.append("Read-only inspection report loaded.")
    if device:
        parts.append(f"Device: {device}.")
    if status:
        parts.append(f"Compatibility: {status}.")
    else:
        parts.append("Compatibility: not established; this report has no readable compatibility summary.")
    if assessment:
        parts.append(f"Evidence assessment: {assessment}.")
    if next_step:
        parts.append(f"Next step: {next_step}")
    parts.append("ADB detection and device-reported properties do not prove port support, bootability, or working hardware.")
    return "\n".join(parts)

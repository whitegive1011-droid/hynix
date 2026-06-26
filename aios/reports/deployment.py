"""Deployment summary rendering."""

from __future__ import annotations

from pathlib import Path

from aios.app.models import RunMetadata


def write_deployment_summary(
    output_dir: str | Path,
    metadata: RunMetadata,
    test_result: str,
    deployment_status: str,
) -> Path:
    path = Path(output_dir) / "deployment_summary.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "AIOS Deployment Summary",
        "=======================",
        f"Execution Time: {metadata.execution_time_seconds:.2f}s",
        f"Provider Used: {metadata.provider_used}",
        f"Data Source: {metadata.data_source}",
        f"Data Quality: {metadata.data_quality}",
        f"Last Update: {metadata.last_update}",
        f"Fallback Used: {metadata.fallback_used}",
        f"Missing Tickers: {', '.join(metadata.missing_tickers) or 'None'}",
        f"Test Result: {test_result}",
        f"Deployment Status: {deployment_status}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

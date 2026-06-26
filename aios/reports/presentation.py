"""Presentation layer orchestration."""

from __future__ import annotations

from pathlib import Path

from aios.reports.excel import write_investment_dashboard
from aios.reports.html import write_dashboard_html
from aios.reports.json_exporter import write_latest_signal
from aios.reports.models import PresentationContext, PresentationOutputPaths


def generate_presentation_outputs(
    context: PresentationContext,
    output_dir: str | Path,
) -> PresentationOutputPaths:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    return PresentationOutputPaths(
        latest_signal=write_latest_signal(
            context,
            output_path / "latest_signal.json",
        ),
        excel_dashboard=write_investment_dashboard(
            context,
            output_path / "investment_dashboard.xlsx",
        ),
        html_dashboard=write_dashboard_html(
            context,
            output_path / "dashboard.html",
        ),
    )

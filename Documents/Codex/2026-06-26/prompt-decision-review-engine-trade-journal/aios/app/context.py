"""Runtime context models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aios.config.models import AiosConfig, PortfolioConfig


@dataclass(frozen=True)
class RunContext:
    """Immutable context shared by the application runner."""

    config: AiosConfig
    portfolio: PortfolioConfig
    config_path: Path
    portfolio_path: Path
    output_dir: Path
    interactive_input: bool
    manual_input_path: Path | None = None

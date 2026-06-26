"""Logging setup for AIOS."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def configure_logging(output_dir: Path, level_name: str = "INFO") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "execution.log"
    level = getattr(logging, level_name.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return log_path

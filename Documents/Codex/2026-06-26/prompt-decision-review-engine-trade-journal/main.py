"""AIOS command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aios.app.runner import AiosRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the AI Investment Operating System."
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the AIOS config YAML file.",
    )
    parser.add_argument(
        "--portfolio",
        default="portfolio.yaml",
        help="Path to the portfolio YAML file.",
    )
    parser.add_argument(
        "--mode",
        default=None,
        choices=["daily", "monthly"],
        help="Optional run mode override.",
    )
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Disable interactive Investment Coach input.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = AiosRunner(
        config_path=Path(args.config),
        portfolio_path=Path(args.portfolio),
        mode_override=args.mode,
        no_input=args.no_input,
    )
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())

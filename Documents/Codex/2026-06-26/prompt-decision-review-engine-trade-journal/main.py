"""AIOS command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aios.app.cache_seeder import (
    CacheSeeder,
    ManualCacheImporter,
    ManualCacheTemplate,
)
from aios.app.runner import AiosRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the AI Investment Operating System."
    )
    subparsers = parser.add_subparsers(dest="command")

    seed_parser = subparsers.add_parser(
        "seed-cache",
        help="Fetch configured tickers and upsert them into the CSV cache.",
    )
    seed_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the AIOS config YAML file.",
    )
    seed_parser.add_argument(
        "--provider",
        choices=["yfinance", "stooq", "alphavantage", "finnhub", "csv", "multi"],
        default="yfinance",
        help="Market data provider used for cache seeding.",
    )
    seed_parser.add_argument(
        "--output",
        default="data/cache/market_cache.csv",
        help="CSV cache path to upsert.",
    )

    template_parser = subparsers.add_parser(
        "cache-template",
        help="Create a CSV template for manual market data entry.",
    )
    template_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the AIOS config YAML file.",
    )
    template_parser.add_argument(
        "--output",
        default="data/cache/manual_prices_template.csv",
        help="Path for the manual price template CSV.",
    )

    import_parser = subparsers.add_parser(
        "import-cache",
        help="Import manually entered market data into the CSV cache.",
    )
    import_parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the AIOS config YAML file.",
    )
    import_parser.add_argument(
        "--input",
        required=True,
        help="Manual price CSV to import.",
    )
    import_parser.add_argument(
        "--output",
        default="data/cache/market_cache.csv",
        help="CSV cache path to upsert.",
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
        "--provider",
        choices=["multi", "yfinance", "stooq", "alphavantage", "finnhub", "csv"],
        default=None,
        help="Market data provider override.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Directory for generated reports and logs.",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pipeline without writing reports or history files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seed-cache":
        return CacheSeeder(
            config_path=Path(args.config),
            provider_name=args.provider,
            output_path=Path(args.output),
        ).run()
    if args.command == "cache-template":
        return ManualCacheTemplate(
            config_path=Path(args.config),
            output_path=Path(args.output),
        ).run()
    if args.command == "import-cache":
        return ManualCacheImporter(
            config_path=Path(args.config),
            input_path=Path(args.input),
            output_path=Path(args.output),
        ).run()

    runner = AiosRunner(
        config_path=Path(args.config),
        portfolio_path=Path(args.portfolio),
        mode_override=args.mode,
        provider_override=args.provider,
        output_dir_override=Path(args.output_dir),
        no_input=args.no_input,
        dry_run=args.dry_run,
    )
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())

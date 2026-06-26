"""Top-level application runner for AIOS."""

from __future__ import annotations

import logging
from pathlib import Path

from aios.app.context import RunContext
from aios.config.loader import load_config, load_portfolio
from aios.data.models import MarketDataRequest, prepare_history_frame
from aios.data.providers import create_market_data_provider
from aios.storage.csv_store import upsert_csv
from aios.storage.paths import ensure_output_dir
from aios.utils.dates import current_run_timestamp, run_id_from_timestamp
from aios.utils.logging import configure_logging


class AiosRunner:
    """Coordinate one AIOS run.

    Market data is fetched and stored in Milestone 2. Decision and review
    modules are added in later milestones.
    """

    def __init__(
        self,
        config_path: Path,
        portfolio_path: Path,
        mode_override: str | None = None,
        no_input: bool = False,
    ) -> None:
        self.config_path = config_path
        self.portfolio_path = portfolio_path
        self.mode_override = mode_override
        self.no_input = no_input

    def run(self) -> int:
        config = load_config(self.config_path)
        portfolio = load_portfolio(self.portfolio_path)

        if self.mode_override:
            config.app.run_mode = self.mode_override

        output_dir = ensure_output_dir(config.app.output_dir)
        configure_logging(output_dir, config.app.log_level)

        context = RunContext(
            config=config,
            portfolio=portfolio,
            config_path=self.config_path,
            portfolio_path=self.portfolio_path,
            output_dir=output_dir,
            interactive_input=(
                config.coach.interactive_input and not self.no_input
            ),
        )

        self._log_startup(context)
        self._fetch_and_store_market_history(context)
        logging.info("AIOS run completed.")
        return 0

    @staticmethod
    def _log_startup(context: RunContext) -> None:
        logging.info("AIOS run started.")
        logging.info("Config loaded from %s", context.config_path)
        logging.info("Portfolio loaded from %s", context.portfolio_path)
        logging.info("Output directory: %s", context.output_dir)
        logging.info("Run mode: %s", context.config.app.run_mode)
        logging.info("Interactive input: %s", context.interactive_input)
        logging.info(
            "Required tickers configured: %s",
            len(context.config.data.required_tickers),
        )
        logging.info(
            "Portfolio positions configured: %s",
            len(context.portfolio.positions),
        )

    @staticmethod
    def _fetch_and_store_market_history(context: RunContext) -> None:
        run_timestamp = current_run_timestamp(context.config.app.timezone)
        run_id = run_id_from_timestamp(run_timestamp)
        request = MarketDataRequest(
            tickers=context.config.data.required_tickers,
            lookback_days=context.config.data.lookback_days,
        )
        provider = create_market_data_provider(
            context.config.data.primary_provider,
            csv_path=context.config.data.csv_path,
        )

        logging.info(
            "Fetching market data from %s for %s tickers.",
            provider.source_name,
            len(request.tickers),
        )
        prices = provider.fetch(request)
        history = prepare_history_frame(
            prices=prices,
            run_id=run_id,
            run_timestamp=run_timestamp,
            source=provider.source_name,
        )
        history_path = context.output_dir / "history.csv"
        stored = upsert_csv(
            path=history_path,
            frame=history,
            key_columns=["date", "ticker", "source"],
        )
        logging.info(
            "Market history written to %s with %s rows.",
            history_path,
            len(stored),
        )

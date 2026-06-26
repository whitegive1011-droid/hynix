"""Top-level application runner for AIOS."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import replace
from pathlib import Path

from aios.app.context import RunContext
from aios.app.models import MarketState, PortfolioState, RunMetadata
from aios.config.loader import load_config, load_portfolio
from aios.config.models import PortfolioConfig
from aios.data.models import MarketDataRequest, prepare_history_frame
from aios.data.providers import create_market_data_provider
from aios.decision.engine import DecisionEngine
from aios.decision.models import (
    BasketSnapshot,
    DecisionInput,
    TechnicalSnapshot,
)
from aios.market.baskets import calculate_basket_metrics
from aios.market.indicators import add_technical_indicators
from aios.reports.models import build_presentation_context
from aios.reports.deployment import write_deployment_summary
from aios.reports.presentation import generate_presentation_outputs
from aios.storage.csv_store import upsert_csv
from aios.storage.paths import ensure_output_dir
from aios.utils.dates import current_run_timestamp, run_id_from_timestamp
from aios.utils.logging import configure_logging


class AiosRunner:
    """Coordinate one AIOS run.

    The runner is an application orchestrator. It connects existing modules
    without embedding indicator formulas or trading rules.
    """

    def __init__(
        self,
        config_path: Path,
        portfolio_path: Path,
        mode_override: str | None = None,
        provider_override: str | None = None,
        output_dir_override: Path | None = None,
        no_input: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.config_path = config_path
        self.portfolio_path = portfolio_path
        self.mode_override = mode_override
        self.provider_override = provider_override
        self.output_dir_override = output_dir_override
        self.no_input = no_input
        self.dry_run = dry_run

    def run(self) -> int:
        started = time.perf_counter()
        config = load_config(self.config_path)
        portfolio = self._load_portfolio_or_default(self.portfolio_path)

        if self.mode_override:
            config.app.run_mode = self.mode_override
        if self.output_dir_override:
            config.app.output_dir = self.output_dir_override
        if self.provider_override:
            config.data = replace(
                config.data,
                primary_provider=self.provider_override,
            )

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
        self._run_pipeline(context, started_at=started)
        logging.info("AIOS run completed.")
        return 0

    @staticmethod
    def _load_portfolio_or_default(portfolio_path: Path) -> PortfolioConfig:
        if portfolio_path.exists():
            return load_portfolio(portfolio_path)
        return PortfolioConfig()

    @staticmethod
    def _log_startup(context: RunContext) -> None:
        logging.info("AIOS run started.")
        logging.info("Config loaded from %s", context.config_path)
        if context.portfolio_path.exists():
            logging.info("Portfolio loaded from %s", context.portfolio_path)
        else:
            logging.warning(
                "Portfolio file %s not found. Using safe defaults.",
                context.portfolio_path,
            )
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

    def _run_pipeline(self, context: RunContext, started_at: float) -> None:
        run_timestamp = current_run_timestamp(context.config.app.timezone)
        run_id = run_id_from_timestamp(run_timestamp)
        prices, metadata = self._fetch_market_data(context)
        history = prepare_history_frame(
            prices=prices,
            run_id=run_id,
            run_timestamp=run_timestamp,
            source=metadata.provider_used,
        )

        if self.dry_run:
            logging.info("Dry run enabled. Skipping history and report writes.")
        else:
            self._store_history(context, history)

        market_state = self._build_market_state(context, prices)
        portfolio_state = self._build_portfolio_state(
            context,
            market_state.technical.ticker,
        )
        decision_input = DecisionInput(
            basket=market_state.basket,
            technical=market_state.technical,
            position=portfolio_state.to_position(),
        )
        decision = DecisionEngine(context.config.decision).decide(decision_input)
        presentation = build_presentation_context(
            decision=decision,
            basket=market_state.basket,
            technical=market_state.technical,
            portfolio=portfolio_state.to_position(),
            metadata=metadata,
        )

        if not self.dry_run:
            paths = generate_presentation_outputs(
                presentation,
                context.output_dir,
            )
            metadata = replace(
                metadata,
                execution_time_seconds=time.perf_counter() - started_at,
            )
            summary_path = write_deployment_summary(
                output_dir=context.output_dir,
                metadata=metadata,
                test_result=os.environ.get("AIOS_TEST_RESULT", "not_run"),
                deployment_status=os.environ.get(
                    "AIOS_DEPLOYMENT_STATUS",
                    "generated",
                ),
            )
            logging.info("Latest signal written to %s", paths.latest_signal)
            logging.info("Excel dashboard written to %s", paths.excel_dashboard)
            logging.info("HTML dashboard written to %s", paths.html_dashboard)
            logging.info("Deployment summary written to %s", summary_path)

        logging.info("Recommendation: %s", decision.recommendation)
        logging.info("Market mode: %s", decision.market_mode.value)
        logging.info("Confidence: %s", decision.confidence)

    def _fetch_market_data(self, context: RunContext):
        request = MarketDataRequest(
            tickers=context.config.data.required_tickers,
            lookback_days=context.config.data.lookback_days,
        )
        prices = self._fetch_with_retry(
            provider_name=context.config.data.primary_provider,
            request=request,
            csv_path=context.config.data.csv_path,
            attempts=max(1, context.config.data.retry_attempts),
            retry_delay_seconds=context.config.data.retry_delay_seconds,
        )

        provider_used = context.config.data.primary_provider
        fallback_used = False
        if prices.empty and context.config.data.primary_provider == "yfinance":
            fallback_path = self._resolve_csv_cache_path(context)
            logging.warning(
                "Primary provider returned no data. Falling back to CSV cache: %s",
                fallback_path,
            )
            prices = self._fetch_with_retry(
                provider_name=context.config.data.fallback_provider,
                request=request,
                csv_path=fallback_path,
                attempts=1,
                retry_delay_seconds=0,
            )
            provider_used = context.config.data.fallback_provider
            fallback_used = True

        metadata = self._build_run_metadata(
            prices=prices,
            provider_used=provider_used,
            required_tickers=context.config.data.required_tickers,
            fallback_used=fallback_used,
        )
        logging.info("Provider used: %s", metadata.provider_used)
        logging.info("Data quality: %s", metadata.data_quality)
        return prices, metadata

    def _fetch_with_retry(
        self,
        provider_name: str,
        request: MarketDataRequest,
        csv_path: Path | None,
        attempts: int,
        retry_delay_seconds: float,
    ):
        provider = create_market_data_provider(provider_name, csv_path=csv_path)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                logging.info(
                    "Fetching market data from %s for %s tickers. Attempt %s/%s.",
                    provider.source_name,
                    len(request.tickers),
                    attempt,
                    attempts,
                )
                prices = provider.fetch(request)
                if not prices.empty:
                    return prices
            except Exception as exc:  # pragma: no cover - defensive logging
                last_error = exc
                logging.warning(
                    "Market data fetch failed from %s on attempt %s/%s: %s",
                    provider.source_name,
                    attempt,
                    attempts,
                    exc,
                )
            if attempt < attempts and retry_delay_seconds > 0:
                time.sleep(retry_delay_seconds)

        if last_error is not None:
            logging.warning("All fetch attempts failed: %s", last_error)
        return provider.fetch(MarketDataRequest(tickers=[], lookback_days=0))

    @staticmethod
    def _resolve_csv_cache_path(context: RunContext) -> Path:
        if context.config.data.csv_path is not None:
            return context.config.data.csv_path
        return context.output_dir / "history.csv"

    @staticmethod
    def _build_run_metadata(
        prices,
        provider_used: str,
        required_tickers: list[str],
        fallback_used: bool,
    ) -> RunMetadata:
        if prices.empty:
            return RunMetadata(
                data_source=provider_used,
                provider_used=provider_used,
                last_update="N/A",
                data_quality="Failed",
                missing_tickers=required_tickers,
                fallback_used=fallback_used,
            )

        available_tickers = set(prices["ticker"].astype(str).unique())
        missing_tickers = [
            ticker for ticker in required_tickers if ticker not in available_tickers
        ]
        last_update = str(max(prices["date"].astype(str)))
        if missing_tickers:
            data_quality = "Degraded"
        elif fallback_used:
            data_quality = "Fallback"
        else:
            data_quality = "OK"

        return RunMetadata(
            data_source=provider_used,
            provider_used=provider_used,
            last_update=last_update,
            data_quality=data_quality,
            missing_tickers=missing_tickers,
            fallback_used=fallback_used,
        )

    @staticmethod
    def _store_history(context: RunContext, history) -> None:
        history_path = context.output_dir / "history.csv"
        stored = upsert_csv(
            path=history_path,
            frame=history,
            key_columns=["date", "ticker"],
        )
        logging.info(
            "Market history written to %s with %s rows.",
            history_path,
            len(stored),
        )

    def _build_market_state(self, context: RunContext, prices) -> MarketState:
        if prices.empty:
            raise ValueError("No market data available for orchestration.")

        basket_metrics = calculate_basket_metrics(
            prices=prices,
            ai_tickers=list(context.config.baskets.ai.keys()),
            hbm_weights=context.config.baskets.hbm,
        )
        if basket_metrics.empty:
            raise ValueError("Basket metrics are empty.")

        technicals = add_technical_indicators(
            prices,
            ma_windows=context.config.indicators.moving_averages,
            ema_windows=context.config.indicators.moving_averages,
            rsi_period=context.config.indicators.rsi_period,
            atr_period=context.config.indicators.atr_period,
            adx_period=context.config.indicators.adx_period,
            bollinger_period=context.config.indicators.bollinger_period,
            bollinger_std=context.config.indicators.bollinger_std,
        )
        target_ticker = self._select_primary_ticker(context, technicals)
        ticker_technicals = technicals[technicals["ticker"] == target_ticker]
        if ticker_technicals.empty:
            raise ValueError(f"No technical indicators available for {target_ticker}.")

        return MarketState(
            basket=BasketSnapshot.from_row(basket_metrics.iloc[-1]),
            technical=TechnicalSnapshot.from_row(ticker_technicals.iloc[-1]),
        )

    @staticmethod
    def _select_primary_ticker(context: RunContext, technicals) -> str:
        available = set(technicals["ticker"].astype(str).unique())
        for ticker in context.portfolio.positions:
            if ticker in available:
                return ticker
        for ticker in context.config.data.required_tickers:
            if ticker in available:
                return ticker
        raise ValueError("No ticker with technical indicators is available.")

    @staticmethod
    def _build_portfolio_state(
        context: RunContext,
        primary_ticker: str,
    ) -> PortfolioState:
        position = context.portfolio.positions.get(primary_ticker)
        current_shares = int(round(position.shares)) if position else 0
        return PortfolioState(
            primary_ticker=primary_ticker,
            current_shares=current_shares,
        )

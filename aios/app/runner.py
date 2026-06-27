"""Top-level application runner for AIOS."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from aios.app.context import RunContext
from aios.app.models import MarketState, PortfolioState, RunMetadata
from aios.config.loader import load_config, load_portfolio
from aios.config.models import PortfolioConfig
from aios.data.models import (
    CacheCoverageReport,
    MarketDataRequest,
    PRICE_COLUMNS,
    prepare_history_frame,
)
from aios.data.providers import create_market_data_provider
from aios.data.quality import build_cache_coverage_report, data_quality_label
from aios.decision.engine import DecisionEngine
from aios.decision.models import (
    BasketSnapshot,
    DecisionDataQuality,
    DecisionInput,
    TechnicalSnapshot,
)
from aios.market.baskets import calculate_basket_metrics
from aios.market.indicators import add_technical_indicators
from aios.proxy.models import PROXY_PRICE_COLUMNS, ProxyPriceRequest, ProxySignalSnapshot
from aios.proxy.providers import create_tradable_proxy_price_provider
from aios.proxy.signal import ProxySignalEngine
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
        csv_path_override: Path | None = None,
        manual_input_path_override: Path | None = None,
    ) -> None:
        self.config_path = config_path
        self.portfolio_path = portfolio_path
        self.mode_override = mode_override
        self.provider_override = provider_override
        self.output_dir_override = output_dir_override
        self.no_input = no_input
        self.dry_run = dry_run
        self.csv_path_override = csv_path_override
        self.manual_input_path_override = manual_input_path_override

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
        if self.csv_path_override:
            config.data = replace(config.data, csv_path=self.csv_path_override)

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
            manual_input_path=self.manual_input_path_override,
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
        proxy_prices = self._fetch_proxy_prices(context)
        proxy_latest_date = _proxy_latest_date(proxy_prices)
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
            self._store_proxy_prices(context, proxy_prices)

        market_state = self._build_market_state(
            context,
            prices,
            fallback_date=proxy_latest_date or run_timestamp[:10],
        )
        decision_data_quality = self._decision_data_quality(context, metadata)
        if decision_data_quality.required_basket_tickers_missing:
            market_state = replace(
                market_state,
                basket=self._mask_incomplete_basket_metrics(market_state.basket),
            )
        portfolio_state = self._build_portfolio_state(
            context,
            market_state.technical.ticker,
        )
        proxy_signal = self._build_proxy_signal(
            context=context,
            proxy_prices=proxy_prices,
            official_basket=market_state.basket,
            manual_tickers=metadata.manual_tickers_used,
        )
        decision_input = DecisionInput(
            basket=market_state.basket,
            technical=market_state.technical,
            position=portfolio_state.to_position(),
            data_quality=decision_data_quality,
            proxy_signal=proxy_signal,
        )
        decision = DecisionEngine(
            context.config.decision,
            context.config.proxy,
        ).decide(decision_input)
        if decision.proxy_influenced:
            proxy_signal = replace(proxy_signal, decision_influenced=True)
        presentation = build_presentation_context(
            decision=decision,
            basket=market_state.basket,
            technical=market_state.technical,
            portfolio=portfolio_state.to_position(),
            metadata=metadata,
            proxy_signal=proxy_signal,
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
        manual_metadata = self._manual_input_metadata(context)
        if context.config.data.primary_provider == "multi":
            provider = create_market_data_provider(
                "multi",
                csv_path=self._resolve_csv_cache_path(context),
            )
            logging.info(
                "Fetching market data from multi-source provider for %s tickers.",
                len(request.tickers),
            )
            if hasattr(provider, "fetch_result"):
                result = provider.fetch_result(request)
                prices = self._apply_manual_official_priority(
                    context,
                    result.prices,
                )
                metadata = self._build_run_metadata(
                    prices=prices,
                    provider_used=result.provider_mix,
                    required_tickers=context.config.data.required_tickers,
                    fallback_used=result.provider_mix not in {"none", "yfinance"},
                    provider_by_ticker=result.provider_by_ticker,
                    manual_metadata=manual_metadata,
                )
                logging.info("Provider used: %s", metadata.provider_used)
                logging.info("Data quality: %s", metadata.data_quality)
                return prices, metadata

        prices = self._fetch_with_retry(
            provider_name=context.config.data.primary_provider,
            request=request,
            csv_path=context.config.data.csv_path,
            attempts=max(1, context.config.data.retry_attempts),
            retry_delay_seconds=context.config.data.retry_delay_seconds,
        )

        provider_used = context.config.data.primary_provider
        fallback_used = False
        missing_tickers = self._missing_tickers(
            prices,
            context.config.data.required_tickers,
        )
        if missing_tickers and context.config.data.primary_provider == "yfinance":
            fallback_path = self._resolve_csv_cache_path(context)
            logging.warning(
                "Primary provider missing %s tickers. Falling back to CSV cache: %s",
                len(missing_tickers),
                fallback_path,
            )
            fallback_request = MarketDataRequest(
                tickers=missing_tickers,
                lookback_days=context.config.data.lookback_days,
            )
            fallback_prices = self._fetch_with_retry(
                provider_name=context.config.data.fallback_provider,
                request=fallback_request,
                csv_path=fallback_path,
                attempts=1,
                retry_delay_seconds=0,
            )
            if prices.empty:
                prices = fallback_prices
                provider_used = context.config.data.fallback_provider
            elif not fallback_prices.empty:
                prices = self._merge_price_frames(prices, fallback_prices)
                provider_used = (
                    f"{context.config.data.primary_provider}+"
                    f"{context.config.data.fallback_provider}"
                )
            fallback_used = True

        prices = self._apply_manual_official_priority(context, prices)

        metadata = self._build_run_metadata(
            prices=prices,
            provider_used=provider_used,
            required_tickers=context.config.data.required_tickers,
            fallback_used=fallback_used,
            manual_metadata=manual_metadata,
        )
        logging.info("Provider used: %s", metadata.provider_used)
        logging.info("Data quality: %s", metadata.data_quality)
        return prices, metadata

    def _fetch_proxy_prices(self, context: RunContext) -> pd.DataFrame:
        if not context.config.proxy.enabled:
            return pd.DataFrame(columns=PROXY_PRICE_COLUMNS)
        symbols = {
            ticker: symbol
            for ticker, symbol in context.config.proxy.symbols.items()
            if str(symbol).strip()
        }
        if not symbols:
            return pd.DataFrame(columns=PROXY_PRICE_COLUMNS)
        provider = create_tradable_proxy_price_provider(context.config.proxy)
        request = ProxyPriceRequest(
            symbols=symbols,
            provider_priority=context.config.proxy.provider_priority,
        )
        return provider.fetch(request)

    @staticmethod
    def _build_proxy_signal(
        context: RunContext,
        proxy_prices: pd.DataFrame,
        official_basket: BasketSnapshot,
        manual_tickers: list[str],
    ) -> ProxySignalSnapshot:
        return ProxySignalEngine(
            ai_tickers=list(context.config.baskets.ai),
            hbm_weights=context.config.baskets.hbm,
            manual_official_tickers=manual_tickers,
        ).build(proxy_prices, official_basket=official_basket)

    def _apply_manual_official_priority(
        self,
        context: RunContext,
        prices: pd.DataFrame,
    ) -> pd.DataFrame:
        manual_prices = self._manual_official_prices(context)
        if manual_prices.empty:
            return prices
        return self._merge_price_frames(manual_prices, prices)

    def _manual_official_prices(self, context: RunContext) -> pd.DataFrame:
        manual_path = self._manual_input_path(context)
        if not manual_path.exists():
            return pd.DataFrame(columns=PRICE_COLUMNS)
        try:
            frame = pd.read_csv(manual_path)
        except Exception:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        required_columns = {"date", "ticker", "close"}
        if frame.empty or not required_columns.issubset(frame.columns):
            return pd.DataFrame(columns=PRICE_COLUMNS)

        manual = frame.copy()
        manual["date"] = pd.to_datetime(
            manual["date"],
            errors="coerce",
        ).dt.date.astype(str)
        manual["ticker"] = manual["ticker"].astype(str)
        manual["close"] = pd.to_numeric(manual["close"], errors="coerce")
        manual = manual.dropna(subset=["date", "ticker", "close"])
        manual = manual[manual["date"] != "NaT"]
        if manual.empty:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        return pd.DataFrame(
            {
                "date": manual["date"],
                "ticker": manual["ticker"],
                "open": manual["close"],
                "high": manual["close"],
                "low": manual["close"],
                "close": manual["close"],
                "adj_close": manual["close"],
                "volume": 0,
            }
        )[PRICE_COLUMNS]

    @staticmethod
    def _missing_tickers(prices, required_tickers: list[str]) -> list[str]:
        if prices.empty:
            return list(required_tickers)
        available_tickers = set(prices["ticker"].astype(str).unique())
        return [ticker for ticker in required_tickers if ticker not in available_tickers]

    @staticmethod
    def _merge_price_frames(primary_prices, fallback_prices):
        if primary_prices.empty:
            return fallback_prices
        if fallback_prices.empty:
            return primary_prices

        combined = pd.concat(
            [primary_prices[PRICE_COLUMNS], fallback_prices[PRICE_COLUMNS]],
            ignore_index=True,
        )
        combined["date"] = pd.to_datetime(combined["date"]).dt.date.astype(str)
        combined["ticker"] = combined["ticker"].astype(str)
        return (
            combined.sort_values(["ticker", "date"])
            .drop_duplicates(subset=["date", "ticker"], keep="first")
            .reset_index(drop=True)
        )

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
    def _manual_input_metadata(context: RunContext) -> dict[str, object]:
        manual_path = AiosRunner._manual_input_path(context)
        if not manual_path.exists():
            return _default_manual_metadata()

        try:
            frame = pd.read_csv(manual_path)
        except Exception as exc:  # pragma: no cover - defensive metadata guard
            logging.warning("Could not read manual input metadata: %s", exc)
            return _default_manual_metadata()

        if frame.empty or "date" not in frame.columns or "ticker" not in frame.columns:
            return _default_manual_metadata()

        normalized = frame.copy()
        normalized["date"] = pd.to_datetime(
            normalized["date"],
            errors="coerce",
        ).dt.date.astype(str)
        normalized = normalized[normalized["date"] != "NaT"]
        if normalized.empty:
            return _default_manual_metadata()

        latest_date = max(normalized["date"].astype(str))
        latest_rows = normalized[normalized["date"].astype(str) == latest_date]
        tickers = sorted(latest_rows["ticker"].astype(str).unique())
        source = "GitHub Issue"
        if "input_source" in latest_rows.columns:
            sources = [
                str(value).strip()
                for value in latest_rows["input_source"].dropna().unique()
                if str(value).strip()
            ]
            if sources:
                source = "+".join(sorted(set(sources)))

        return {
            "used": True,
            "latest_date": latest_date,
            "tickers": tickers,
            "source": source,
        }

    @staticmethod
    def _manual_input_path(context: RunContext) -> Path:
        if context.manual_input_path is not None:
            return context.manual_input_path
        cache_path = AiosRunner._resolve_csv_cache_path(context)
        if cache_path.parent.name == "cache":
            return cache_path.parent.parent / "manual" / "daily_manual_prices.csv"
        return cache_path.parent / "manual" / "daily_manual_prices.csv"

    @staticmethod
    def _build_run_metadata(
        prices,
        provider_used: str,
        required_tickers: list[str],
        fallback_used: bool,
        provider_by_ticker: dict[str, str] | None = None,
        coverage: CacheCoverageReport | None = None,
        manual_metadata: dict[str, object] | None = None,
    ) -> RunMetadata:
        provider_by_ticker = provider_by_ticker or {}
        manual_metadata = manual_metadata or _default_manual_metadata()
        coverage = coverage or build_cache_coverage_report(
            prices=prices,
            required_tickers=required_tickers,
            provider_by_ticker=provider_by_ticker,
        )
        provider_map = dict(coverage.provider_by_ticker)
        manual_tickers = [
            str(ticker) for ticker in manual_metadata.get("tickers", [])
        ]
        if manual_metadata.get("used"):
            for ticker in manual_tickers:
                if ticker in provider_map:
                    provider_map[ticker] = "GitHub Issue"
        if prices.empty:
            return RunMetadata(
                data_source=provider_used,
                provider_used=provider_used,
                last_update="N/A",
                data_quality="Failed",
                missing_tickers=required_tickers,
                fallback_used=fallback_used,
                provider_by_ticker={},
                stale_tickers=[],
                cache_coverage_percentage=0.0,
                data_quality_score=0,
                recommendation_degraded=True,
                manual_mobile_input_used=bool(manual_metadata.get("used")),
                latest_manual_input_date=str(
                    manual_metadata.get("latest_date", "N/A")
                ),
                manual_tickers_used=manual_tickers,
                manual_source=str(manual_metadata.get("source", "None")),
            )

        last_update = (
            max(coverage.last_available_dates.values())
            if coverage.last_available_dates
            else str(max(prices["date"].astype(str)))
        )
        quality = data_quality_label(
            coverage.data_quality_score,
            coverage.missing_tickers,
        )
        if fallback_used and quality == "OK":
            quality = "Fallback"

        return RunMetadata(
            data_source=provider_used,
            provider_used=provider_used,
            last_update=last_update,
            data_quality=quality,
            missing_tickers=coverage.missing_tickers,
            fallback_used=fallback_used,
            provider_by_ticker=provider_map,
            stale_tickers=coverage.stale_tickers,
            cache_coverage_percentage=coverage.coverage_percentage,
            data_quality_score=coverage.data_quality_score,
            recommendation_degraded=(
                bool(coverage.missing_tickers)
                or bool(coverage.stale_tickers)
                or coverage.data_quality_score < 90
            ),
            manual_mobile_input_used=bool(manual_metadata.get("used")),
            latest_manual_input_date=str(
                manual_metadata.get("latest_date", "N/A")
            ),
            manual_tickers_used=manual_tickers,
            manual_source=str(manual_metadata.get("source", "None")),
        )

    @staticmethod
    def _decision_data_quality(
        context: RunContext,
        metadata: RunMetadata,
    ) -> DecisionDataQuality:
        basket_tickers = set(context.config.baskets.ai) | set(context.config.baskets.hbm)
        missing = set(metadata.missing_tickers)
        return DecisionDataQuality(
            missing_tickers=metadata.missing_tickers,
            stale_tickers=metadata.stale_tickers or [],
            data_quality_score=metadata.data_quality_score,
            required_basket_tickers_missing=bool(basket_tickers & missing),
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

    @staticmethod
    def _store_proxy_prices(context: RunContext, proxy_prices: pd.DataFrame) -> None:
        if proxy_prices.empty:
            return
        stored = upsert_csv(
            path=context.config.proxy.output_path,
            frame=proxy_prices[PROXY_PRICE_COLUMNS],
            key_columns=["date", "ticker", "provider"],
        )
        logging.info(
            "Tradable proxy prices written to %s with %s rows.",
            context.config.proxy.output_path,
            len(stored),
        )

    def _build_market_state(
        self,
        context: RunContext,
        prices,
        fallback_date: str,
    ) -> MarketState:
        if prices.empty:
            return self._empty_market_state(context, fallback_date)

        basket_metrics = calculate_basket_metrics(
            prices=prices,
            ai_tickers=list(context.config.baskets.ai.keys()),
            hbm_weights=context.config.baskets.hbm,
        )
        if basket_metrics.empty:
            return self._empty_market_state(context, fallback_date)

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
    def _empty_market_state(context: RunContext, date_value: str) -> MarketState:
        ticker = next(iter(context.portfolio.positions), None)
        if ticker is None:
            ticker = (
                context.config.data.required_tickers[0]
                if context.config.data.required_tickers
                else "N/A"
            )
        return MarketState(
            basket=BasketSnapshot(date=date_value),
            technical=TechnicalSnapshot(date=date_value, ticker=ticker),
        )

    @staticmethod
    def _mask_incomplete_basket_metrics(basket: BasketSnapshot) -> BasketSnapshot:
        return BasketSnapshot(date=basket.date)

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


def _default_manual_metadata() -> dict[str, object]:
    return {
        "used": False,
        "latest_date": "N/A",
        "tickers": [],
        "source": "None",
    }


def _proxy_latest_date(proxy_prices: pd.DataFrame) -> str | None:
    if proxy_prices.empty or "date" not in proxy_prices.columns:
        return None
    dates = pd.to_datetime(proxy_prices["date"], errors="coerce").dropna()
    if dates.empty:
        return None
    return dates.max().date().isoformat()

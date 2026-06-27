"""Cache seeding command for market data."""

from __future__ import annotations

from pathlib import Path

from aios.config.loader import load_config
from aios.data.models import MarketDataRequest
from aios.data.providers import create_market_data_provider
from aios.data.quality import build_cache_coverage_report
from aios.storage.csv_store import upsert_csv


class CacheSeeder:
    """Fetch configured tickers and upsert them into the CSV market cache."""

    def __init__(
        self,
        config_path: Path,
        provider_name: str,
        output_path: Path,
    ) -> None:
        self.config_path = config_path
        self.provider_name = provider_name
        self.output_path = output_path

    def run(self) -> int:
        config = load_config(self.config_path)
        cache_path = config.data.csv_path or self.output_path
        provider = create_market_data_provider(
            self.provider_name,
            csv_path=cache_path if self.provider_name in {"csv", "multi"} else None,
        )
        request = MarketDataRequest(
            tickers=config.data.required_tickers,
            lookback_days=config.data.lookback_days,
        )
        prices = provider.fetch(request)
        stored = upsert_csv(
            path=self.output_path,
            frame=prices,
            key_columns=["date", "ticker"],
        )

        provider_by_ticker = getattr(provider, "last_result", None)
        attribution = (
            provider_by_ticker.provider_by_ticker
            if provider_by_ticker is not None
            else {ticker: provider.source_name for ticker in prices["ticker"].unique()}
            if not prices.empty
            else {}
        )
        report = build_cache_coverage_report(
            prices=stored,
            required_tickers=config.data.required_tickers,
            provider_by_ticker=attribution,
            stale_price_days=config.data_quality.stale_price_days,
        )
        self._print_report(report)
        return 0

    def _print_report(self, report) -> None:
        print("AIOS Cache Coverage Report")
        print("==========================")
        print(f"Output: {self.output_path}")
        print(f"Provider: {self.provider_name}")
        print(f"Required tickers: {', '.join(report.required_tickers) or 'None'}")
        print(f"Available tickers: {', '.join(report.available_tickers) or 'None'}")
        print(f"Missing tickers: {', '.join(report.missing_tickers) or 'None'}")
        print(f"Stale tickers: {', '.join(report.stale_tickers) or 'None'}")
        print(f"Coverage: {report.coverage_percentage:.2f}%")
        print(f"Data Quality Score: {report.data_quality_score}")
        print("Date ranges:")
        for ticker in report.required_tickers:
            date_range = report.date_ranges.get(ticker)
            provider = report.provider_by_ticker.get(ticker, "missing")
            if date_range is None:
                print(f"  {ticker}: missing")
            else:
                print(f"  {ticker}: {date_range[0]} -> {date_range[1]} ({provider})")

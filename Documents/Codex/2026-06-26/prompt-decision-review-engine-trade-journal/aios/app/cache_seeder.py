"""Cache seeding command for market data."""

from __future__ import annotations

from pathlib import Path

from aios.config.loader import load_config
import pandas as pd

from aios.data.models import MarketDataRequest, PRICE_COLUMNS
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


class ManualCacheTemplate:
    """Create a CSV template for manually entered market data."""

    def __init__(self, config_path: Path, output_path: Path) -> None:
        self.config_path = config_path
        self.output_path = output_path

    def run(self) -> int:
        config = load_config(self.config_path)
        rows = [
            {
                "date": "",
                "ticker": ticker,
                "close": "",
                "open": "",
                "high": "",
                "low": "",
                "adj_close": "",
                "volume": "",
            }
            for ticker in config.data.required_tickers
        ]
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(self.output_path, index=False)
        print(f"Manual cache template written to {self.output_path}")
        print("Required columns: date, ticker, close")
        print("Optional columns: open, high, low, adj_close, volume")
        return 0


class ManualCacheImporter:
    """Import manually entered market prices into the cache."""

    def __init__(
        self,
        config_path: Path,
        input_path: Path,
        output_path: Path,
    ) -> None:
        self.config_path = config_path
        self.input_path = input_path
        self.output_path = output_path

    def run(self) -> int:
        config = load_config(self.config_path)
        prices = _read_manual_prices(self.input_path)
        required = set(config.data.required_tickers)
        prices = prices[prices["ticker"].isin(required)].reset_index(drop=True)
        stored = upsert_csv(
            path=self.output_path,
            frame=prices,
            key_columns=["date", "ticker"],
        )
        report = build_cache_coverage_report(
            prices=stored,
            required_tickers=config.data.required_tickers,
            provider_by_ticker={
                ticker: "manual" for ticker in prices["ticker"].unique()
            },
            stale_price_days=config.data_quality.stale_price_days,
        )
        self._print_import_summary(prices, report)
        return 0

    def _print_import_summary(self, prices, report) -> None:
        print("AIOS Manual Cache Import")
        print("========================")
        print(f"Input: {self.input_path}")
        print(f"Output: {self.output_path}")
        print(f"Imported rows: {len(prices)}")
        print(f"Imported tickers: {', '.join(sorted(prices['ticker'].unique())) or 'None'}")
        print(f"Missing tickers after import: {', '.join(report.missing_tickers) or 'None'}")
        print(f"Coverage: {report.coverage_percentage:.2f}%")
        print(f"Data Quality Score: {report.data_quality_score}")


def _read_manual_prices(input_path: Path) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(f"Manual price CSV not found: {input_path}")

    frame = pd.read_csv(input_path)
    missing_required = [
        column for column in ["date", "ticker", "close"] if column not in frame.columns
    ]
    if missing_required:
        raise ValueError(
            "Manual price CSV missing required columns: "
            + ", ".join(missing_required)
        )

    prices = frame.copy()
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce").dt.date.astype(str)
    prices["ticker"] = prices["ticker"].astype(str)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.dropna(subset=["date", "ticker", "close"])
    prices = prices[prices["date"] != "NaT"]

    for column in ["open", "high", "low", "adj_close"]:
        if column not in prices.columns:
            prices[column] = prices["close"]
        else:
            prices[column] = pd.to_numeric(prices[column], errors="coerce").fillna(
                prices["close"]
            )

    if "volume" not in prices.columns:
        prices["volume"] = 0
    prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce").fillna(0)

    prices = prices[PRICE_COLUMNS].drop_duplicates(
        subset=["date", "ticker"],
        keep="last",
    )
    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)

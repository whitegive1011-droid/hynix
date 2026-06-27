from __future__ import annotations

from pathlib import Path

import pandas as pd

from aios.data.models import MarketDataRequest, prepare_history_frame
from aios.data.providers import (
    AlphaVantageProvider,
    CsvMarketDataProvider,
    FinnhubProvider,
    MultiSourceMarketDataProvider,
    StooqProvider,
    create_market_data_provider,
)


def test_csv_market_data_provider_filters_tickers() -> None:
    provider = CsvMarketDataProvider(
        Path("tests/fixtures/market_prices_sample.csv")
    )

    frame = provider.fetch(
        MarketDataRequest(tickers=["7709.HK"], lookback_days=5)
    )

    assert set(frame["ticker"]) == {"7709.HK"}
    assert len(frame) == 5
    assert {"date", "ticker", "close"}.issubset(frame.columns)


def test_provider_factory_creates_csv_provider() -> None:
    provider = create_market_data_provider(
        "csv",
        csv_path=Path("tests/fixtures/market_prices_sample.csv"),
    )

    frame = provider.fetch(
        MarketDataRequest(tickers=["NVDA"], lookback_days=5)
    )

    assert provider.source_name == "csv"
    assert set(frame["ticker"]) == {"NVDA"}


def test_prepare_history_frame_adds_returns_and_metadata() -> None:
    provider = CsvMarketDataProvider(
        Path("tests/fixtures/market_prices_sample.csv")
    )
    prices = provider.fetch(
        MarketDataRequest(tickers=["7709.HK"], lookback_days=5)
    )

    history = prepare_history_frame(
        prices=prices,
        run_id="test-run",
        run_timestamp="2026-06-26T15:20:00+08:00",
        source="csv",
    )

    latest = history.iloc[-1]
    assert latest["run_id"] == "test-run"
    assert latest["source"] == "csv"
    assert latest["data_quality_status"] == "unchecked"
    assert round(latest["return_1d"], 4) == 8.3333


def test_multi_source_provider_merges_partial_results_with_attribution() -> None:
    primary = FixtureProvider(
        "primary",
        [
            _row("2026-01-02", "AI1", 102),
            _row("2026-01-02", "HBM1", 999),
        ],
        only_tickers=["AI1"],
    )
    fallback = FixtureProvider(
        "fallback",
        [
            _row("2026-01-01", "AI1", 99),
            _row("2026-01-02", "AI1", 999),
            _row("2026-01-02", "HBM1", 110),
        ],
    )
    provider = MultiSourceMarketDataProvider([primary, fallback])

    result = provider.fetch_result(
        MarketDataRequest(tickers=["AI1", "HBM1"], lookback_days=20)
    )

    latest_ai = result.prices[
        (result.prices["ticker"] == "AI1") & (result.prices["date"] == "2026-01-02")
    ].iloc[0]
    assert latest_ai["close"] == 102
    assert result.provider_mix == "primary+fallback"
    assert result.provider_by_ticker == {"AI1": "primary", "HBM1": "fallback"}
    assert result.coverage.missing_tickers == []
    assert result.coverage.coverage_percentage == 100.0


def test_stooq_provider_uses_symbol_mapping_and_skips_unsupported_tickers() -> None:
    class FixtureStooqProvider(StooqProvider):
        def _download_stooq_csv(self, symbol: str) -> pd.DataFrame:
            assert symbol == "msft.us"
            return pd.DataFrame(
                [
                    {
                        "Date": "2026-01-02",
                        "Open": 100,
                        "High": 101,
                        "Low": 99,
                        "Close": 100,
                        "Volume": 1000,
                    }
                ]
            )

    provider = FixtureStooqProvider(symbol_map={"MSFT": "msft.us"})
    frame = provider.fetch(
        MarketDataRequest(tickers=["MSFT", "000660.KS"], lookback_days=20)
    )

    assert set(frame["ticker"]) == {"MSFT"}
    assert frame.iloc[0]["adj_close"] == 100


def test_optional_api_key_providers_disable_gracefully(monkeypatch) -> None:
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    request = MarketDataRequest(tickers=["MSFT"], lookback_days=5)

    assert AlphaVantageProvider().fetch(request).empty
    assert FinnhubProvider().fetch(request).empty


class FixtureProvider:
    def __init__(
        self,
        source_name: str,
        rows: list[dict[str, object]],
        only_tickers: list[str] | None = None,
    ) -> None:
        self.source_name = source_name
        self.rows = rows
        self.only_tickers = only_tickers

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        frame = pd.DataFrame(self.rows)
        frame = frame[frame["ticker"].isin(request.tickers)]
        if self.only_tickers is not None:
            frame = frame[frame["ticker"].isin(self.only_tickers)]
        return frame.reset_index(drop=True)


def _row(date_value: str, ticker: str, close: float) -> dict[str, object]:
    return {
        "date": date_value,
        "ticker": ticker,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "adj_close": close,
        "volume": 1000,
    }

from pathlib import Path

from aios.data.models import MarketDataRequest, prepare_history_frame
from aios.data.providers import CsvMarketDataProvider, create_market_data_provider


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

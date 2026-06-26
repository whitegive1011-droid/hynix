from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from aios.data.models import MarketDataRequest
from aios.data.providers import CsvMarketDataProvider
from aios.market.indicators import add_technical_indicators


def test_add_technical_indicators_from_csv_fixture(tmp_path: Path) -> None:
    csv_path = _write_indicator_fixture(tmp_path)
    prices = CsvMarketDataProvider(csv_path).fetch(
        MarketDataRequest(tickers=["TEST"], lookback_days=35)
    )

    enriched = add_technical_indicators(
        prices,
        ma_windows=[5],
        ema_windows=[5],
    )

    latest = enriched.iloc[-1]
    last_five_mean = sum([131, 132, 133, 134, 135]) / 5
    last_twenty_mean = sum(range(116, 136)) / 20

    assert latest["sma_5"] == pytest.approx(last_five_mean)
    assert latest["ma_5"] == pytest.approx(latest["sma_5"])
    assert pd.notna(latest["ema_5"])
    assert latest["rsi14"] == pytest.approx(100)
    assert latest["macd"] > 0
    assert pd.notna(latest["macd_signal"])
    assert pd.notna(latest["macd_histogram"])
    assert latest["bollinger_middle"] == pytest.approx(last_twenty_mean)
    assert latest["bollinger_upper"] > latest["bollinger_middle"]
    assert latest["bollinger_middle"] > latest["bollinger_lower"]
    assert latest["atr14"] > 0
    assert latest["adx14"] >= 0


def _write_indicator_fixture(tmp_path: Path) -> Path:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(35):
        close = 101 + offset
        rows.append(
            {
                "date": start + timedelta(days=offset),
                "ticker": "TEST",
                "open": close - 1,
                "high": close + 2,
                "low": close - 2,
                "close": close,
                "adj_close": close,
                "volume": 1000 + offset,
            }
        )

    csv_path = tmp_path / "indicator_prices.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path

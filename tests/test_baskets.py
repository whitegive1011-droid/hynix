from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from aios.data.models import MarketDataRequest
from aios.data.providers import CsvMarketDataProvider
from aios.market.baskets import calculate_basket_metrics


def test_calculate_basket_metrics_from_csv_fixture(tmp_path: Path) -> None:
    csv_path = _write_basket_fixture(tmp_path)
    prices = CsvMarketDataProvider(csv_path).fetch(
        MarketDataRequest(
            tickers=["AI1", "AI2", "HBM1", "HBM2"],
            lookback_days=25,
        )
    )

    metrics = calculate_basket_metrics(
        prices,
        ai_tickers=["AI1", "AI2"],
        hbm_weights={"HBM1": 0.5, "HBM2": 0.5},
    )

    latest = metrics.iloc[-1]
    ai_latest = 124.0
    hbm_latest = (172.0 + 124.0) / 2
    hbm_previous = (169.0 + 123.0) / 2
    ai_1d = (124.0 / 123.0 - 1) * 100
    hbm_1d = (hbm_latest / hbm_previous - 1) * 100
    ai_5d = (124.0 / 119.0 - 1) * 100
    hbm_5d = (hbm_latest / ((157.0 + 119.0) / 2) - 1) * 100
    ai_20d = (124.0 / 104.0 - 1) * 100
    hbm_20d = (hbm_latest / ((112.0 + 104.0) / 2) - 1) * 100
    d1 = hbm_1d - ai_1d
    d5 = hbm_5d - ai_5d
    d20 = hbm_20d - ai_20d
    risk_score = max(0.0, -ai_5d) + max(0.0, hbm_5d) + max(0.0, d5 - 10.0)

    assert latest["AI_Basket"] == pytest.approx(ai_latest)
    assert latest["HBM_Basket"] == pytest.approx(hbm_latest)
    assert latest["AI_1D"] == pytest.approx(ai_1d)
    assert latest["HBM_1D"] == pytest.approx(hbm_1d)
    assert latest["AI_5D"] == pytest.approx(ai_5d)
    assert latest["AI_20D"] == pytest.approx(ai_20d)
    assert latest["HBM_5D"] == pytest.approx(hbm_5d)
    assert latest["HBM_20D"] == pytest.approx(hbm_20d)
    assert latest["D1"] == pytest.approx(d1)
    assert latest["D5"] == pytest.approx(d5)
    assert latest["D20"] == pytest.approx(d20)
    assert latest["Relative_Ratio"] == pytest.approx(hbm_latest / ai_latest)
    assert latest["Risk_Score"] == pytest.approx(risk_score)


def test_risk_score_is_nan_when_forward_inputs_are_missing() -> None:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(5):
        rows.extend(
            [
                _row(start, offset, "AI1", 100 + offset),
                _row(start, offset, "HBM1", 110 + offset),
            ]
        )
    prices = pd.DataFrame(rows)

    metrics = calculate_basket_metrics(
        prices,
        ai_tickers=["AI1"],
        hbm_weights={"HBM1": 1.0},
    )
    latest = metrics.iloc[-1]

    assert pd.isna(latest["AI_5D"])
    assert pd.isna(latest["HBM_5D"])
    assert pd.isna(latest["D5"])
    assert pd.isna(latest["Risk_Score"])


def test_one_day_returns_use_manual_change_pct_when_price_units_change() -> None:
    prices = pd.DataFrame(
        [
            _row(date(2026, 6, 27), 0, "000660.KS", 2673000.0),
            _row(date(2026, 6, 27), 0, "005930.KS", 226.7),
            _row(date(2026, 6, 27), 0, "MU", 1143.47),
            _row(date(2026, 6, 27), 0, "MSFT", 375.61),
            _row(date(2026, 6, 27), 0, "GOOGL", 340.28),
            _row(date(2026, 6, 27), 0, "AMZN", 233.49),
            _row(date(2026, 6, 27), 0, "AAPL", 281.57),
            _row(date(2026, 6, 27), 0, "TSLA", 380.66),
            _row(date(2026, 6, 28), 0, "000660.KS", 1768.32, 0.63),
            _row(date(2026, 6, 28), 0, "005930.KS", 226.96, 2.41),
            _row(date(2026, 6, 28), 0, "MU", 1142.69, -1.28),
            _row(date(2026, 6, 28), 0, "MSFT", 376.11, 1.58),
            _row(date(2026, 6, 28), 0, "GOOGL", 340.25, -0.43),
            _row(date(2026, 6, 28), 0, "AMZN", 233.71, 1.07),
            _row(date(2026, 6, 28), 0, "META", 554.58, 0.03),
            _row(date(2026, 6, 28), 0, "AAPL", 282.28, 0.84),
            _row(date(2026, 6, 28), 0, "TSLA", 381.21, 0.28),
        ]
    )

    metrics = calculate_basket_metrics(
        prices,
        ai_tickers=["MSFT", "GOOGL", "AMZN", "META", "AAPL", "TSLA"],
        hbm_weights={"000660.KS": 0.5, "MU": 0.25, "005930.KS": 0.25},
    )

    latest = metrics.iloc[-1]
    ai_1d = (1.58 - 0.43 + 1.07 + 0.03 + 0.84 + 0.28) / 6
    hbm_1d = (0.63 * 0.5) + (-1.28 * 0.25) + (2.41 * 0.25)
    ai_basket = (101.58 + 99.57 + 101.07 + 100.0 + 100.84 + 100.28) / 6
    hbm_basket = (100.63 * 0.5) + (98.72 * 0.25) + (102.41 * 0.25)

    assert latest["AI_Basket"] == pytest.approx(ai_basket)
    assert latest["HBM_Basket"] == pytest.approx(hbm_basket)
    assert latest["AI_1D"] == pytest.approx(ai_1d)
    assert latest["HBM_1D"] == pytest.approx(hbm_1d)
    assert latest["D1"] == pytest.approx(hbm_1d - ai_1d)
    assert latest["Relative_Ratio"] == pytest.approx(hbm_basket / ai_basket)
    assert latest["HBM_1D"] > -1.0
    assert latest["HBM_Basket"] > 99.0


def _write_basket_fixture(tmp_path: Path) -> Path:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(25):
        rows.extend(
            [
                _row(start, offset, "AI1", 100 + offset),
                _row(start, offset, "AI2", 200 + (offset * 2)),
                _row(start, offset, "HBM1", 100 + (offset * 3)),
                _row(start, offset, "HBM2", 100 + offset),
            ]
        )

    csv_path = tmp_path / "basket_prices.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


def _row(
    start: date,
    offset: int,
    ticker: str,
    close: float,
    change_pct: float | None = None,
) -> dict[str, object]:
    return {
        "date": start + timedelta(days=offset),
        "ticker": ticker,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "adj_close": close,
        "volume": 1000 + offset,
        "change_pct": change_pct,
    }

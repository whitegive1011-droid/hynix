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
    ai_5d = (124.0 / 119.0 - 1) * 100
    hbm_5d = (hbm_latest / ((157.0 + 119.0) / 2) - 1) * 100
    ai_20d = (124.0 / 104.0 - 1) * 100
    hbm_20d = (hbm_latest / ((112.0 + 104.0) / 2) - 1) * 100
    d5 = hbm_5d - ai_5d
    d20 = hbm_20d - ai_20d
    risk_score = max(0.0, -ai_5d) + max(0.0, hbm_5d) + max(0.0, d5 - 10.0)

    assert latest["AI_Basket"] == pytest.approx(ai_latest)
    assert latest["HBM_Basket"] == pytest.approx(hbm_latest)
    assert latest["AI_1D"] == pytest.approx((124.0 / 123.0 - 1) * 100)
    assert latest["AI_5D"] == pytest.approx(ai_5d)
    assert latest["AI_20D"] == pytest.approx(ai_20d)
    assert latest["HBM_5D"] == pytest.approx(hbm_5d)
    assert latest["HBM_20D"] == pytest.approx(hbm_20d)
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


def _row(start: date, offset: int, ticker: str, close: float) -> dict[str, object]:
    return {
        "date": start + timedelta(days=offset),
        "ticker": ticker,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "adj_close": close,
        "volume": 1000 + offset,
    }

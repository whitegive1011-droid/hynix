"""Market data models and frame helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


PRICE_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
]

HISTORY_COLUMNS = [
    "run_id",
    "run_timestamp",
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "return_1d",
    "return_5d",
    "return_20d",
    "source",
    "data_quality_status",
]


@dataclass(frozen=True)
class MarketDataRequest:
    """Request sent to a market data provider."""

    tickers: list[str]
    lookback_days: int


@dataclass(frozen=True)
class TickerCoverage:
    """Coverage details for one ticker in a cache or fetch result."""

    ticker: str
    rows: int
    first_date: str
    last_date: str
    provider: str = "unknown"


@dataclass(frozen=True)
class CacheCoverageReport:
    """Coverage and freshness report for required market data."""

    required_tickers: list[str]
    available_tickers: list[str]
    missing_tickers: list[str]
    stale_tickers: list[str]
    coverage_percentage: float
    data_quality_score: int
    date_ranges: dict[str, tuple[str, str]] = field(default_factory=dict)
    last_available_dates: dict[str, str] = field(default_factory=dict)
    provider_by_ticker: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketDataResult:
    """Market data plus operational metadata from one or more providers."""

    prices: pd.DataFrame
    provider_mix: str
    provider_by_ticker: dict[str, str]
    coverage: CacheCoverageReport


def prepare_history_frame(
    prices: pd.DataFrame,
    run_id: str,
    run_timestamp: str,
    source: str,
) -> pd.DataFrame:
    """Add run metadata and return columns to normalized price data."""

    missing_columns = [col for col in PRICE_COLUMNS if col not in prices.columns]
    if missing_columns:
        raise ValueError(f"Price data missing columns: {missing_columns}")

    if prices.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)

    history = prices.copy()
    history["date"] = pd.to_datetime(history["date"]).dt.date.astype(str)
    history["ticker"] = history["ticker"].astype(str)
    history = history.sort_values(["ticker", "date"]).reset_index(drop=True)

    price_for_return = history["adj_close"].where(
        history["adj_close"].notna(),
        history["close"],
    )
    grouped_price = price_for_return.groupby(history["ticker"])
    history["return_1d"] = grouped_price.pct_change(1) * 100
    history["return_5d"] = grouped_price.pct_change(5) * 100
    history["return_20d"] = grouped_price.pct_change(20) * 100

    history.insert(0, "run_timestamp", run_timestamp)
    history.insert(0, "run_id", run_id)
    history["source"] = source
    history["data_quality_status"] = "unchecked"

    return history[HISTORY_COLUMNS]

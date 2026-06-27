"""Market data coverage and quality helpers."""

from __future__ import annotations

import pandas as pd

from aios.data.models import CacheCoverageReport, PRICE_COLUMNS


def build_cache_coverage_report(
    prices: pd.DataFrame,
    required_tickers: list[str],
    provider_by_ticker: dict[str, str] | None = None,
    stale_price_days: int = 3,
) -> CacheCoverageReport:
    """Summarize ticker coverage, date ranges, freshness, and quality score."""

    provider_by_ticker = provider_by_ticker or {}
    required = [str(ticker) for ticker in required_tickers]
    if prices.empty:
        return CacheCoverageReport(
            required_tickers=required,
            available_tickers=[],
            missing_tickers=required,
            stale_tickers=[],
            coverage_percentage=0.0,
            data_quality_score=0,
            provider_by_ticker={},
        )

    _validate_price_frame(prices)
    frame = prices[PRICE_COLUMNS].copy()
    frame["ticker"] = frame["ticker"].astype(str)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date.astype(str)

    available = sorted(
        ticker
        for ticker in frame["ticker"].unique()
        if ticker in set(required)
    )
    missing = [ticker for ticker in required if ticker not in set(available)]

    date_ranges: dict[str, tuple[str, str]] = {}
    last_dates: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    for ticker, group in frame.groupby("ticker"):
        if ticker not in set(required):
            continue
        dates = sorted(group["date"].astype(str))
        if not dates:
            continue
        date_ranges[ticker] = (dates[0], dates[-1])
        last_dates[ticker] = dates[-1]
        row_counts[ticker] = len(group)

    stale = _stale_tickers(last_dates, stale_price_days)
    coverage_percentage = (
        (len(available) / len(required)) * 100.0 if required else 100.0
    )
    missing_penalty = (len(missing) / len(required)) * 100.0 if required else 0.0
    stale_penalty = (len(stale) / len(required)) * 25.0 if required else 0.0
    sparse_penalty = _sparse_data_penalty(row_counts, required)
    data_quality_score = int(
        max(0.0, min(100.0, 100.0 - missing_penalty - stale_penalty - sparse_penalty))
    )

    return CacheCoverageReport(
        required_tickers=required,
        available_tickers=available,
        missing_tickers=missing,
        stale_tickers=stale,
        coverage_percentage=round(coverage_percentage, 2),
        data_quality_score=data_quality_score,
        date_ranges=date_ranges,
        last_available_dates=last_dates,
        row_counts=row_counts,
        provider_by_ticker={
            ticker: provider_by_ticker.get(ticker, "unknown")
            for ticker in available
        },
    )


def data_quality_label(score: int, missing_tickers: list[str]) -> str:
    if score <= 0:
        return "Failed"
    if missing_tickers or score < 90:
        return "Degraded"
    return "OK"


def _validate_price_frame(prices: pd.DataFrame) -> None:
    missing_columns = [column for column in PRICE_COLUMNS if column not in prices.columns]
    if missing_columns:
        raise ValueError(f"Price data missing columns: {missing_columns}")


def _stale_tickers(
    last_dates: dict[str, str],
    stale_price_days: int,
) -> list[str]:
    if not last_dates:
        return []

    latest = max(pd.to_datetime(list(last_dates.values())))
    cutoff = latest - pd.Timedelta(days=stale_price_days)
    return sorted(
        ticker
        for ticker, last_date in last_dates.items()
        if pd.to_datetime(last_date) < cutoff
    )


def _sparse_data_penalty(row_counts: dict[str, int], required_tickers: list[str]) -> float:
    if not required_tickers:
        return 0.0
    sparse = [
        ticker
        for ticker in required_tickers
        if ticker in row_counts and row_counts[ticker] < 21
    ]
    return (len(sparse) / len(required_tickers)) * 10.0

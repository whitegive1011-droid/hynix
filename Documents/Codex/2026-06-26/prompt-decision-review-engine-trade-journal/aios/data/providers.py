"""Market data provider implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from aios.data.models import MarketDataRequest, PRICE_COLUMNS


class MarketDataProvider(Protocol):
    """Interface implemented by market data providers."""

    source_name: str

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        """Return normalized OHLCV data with PRICE_COLUMNS."""


class YFinanceProvider:
    """Market data provider backed by yfinance."""

    source_name = "yfinance"

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError(
                "yfinance is required for the yfinance provider. "
                "Install dependencies with "
                "`python3 -m pip install -r requirements.txt`."
            ) from exc

        if not request.tickers:
            return pd.DataFrame(columns=PRICE_COLUMNS)

        frames: list[pd.DataFrame] = []
        period = f"{request.lookback_days}d"

        for ticker in request.tickers:
            raw = yf.download(
                ticker,
                period=period,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            normalized = normalize_yfinance_frame(raw, ticker)
            if not normalized.empty:
                frames.append(normalized)

        if not frames:
            return pd.DataFrame(columns=PRICE_COLUMNS)

        return pd.concat(frames, ignore_index=True)[PRICE_COLUMNS]


class CsvMarketDataProvider:
    """Provider used by tests and future local fallback/cache loading."""

    source_name = "csv"

    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        frame = pd.read_csv(self.csv_path)
        missing_columns = [col for col in PRICE_COLUMNS if col not in frame.columns]
        if missing_columns:
            raise ValueError(
                f"CSV market data missing columns: {missing_columns}"
            )

        frame = frame[PRICE_COLUMNS].copy()
        frame["ticker"] = frame["ticker"].astype(str)
        if request.tickers:
            frame = frame[frame["ticker"].isin(request.tickers)]

        return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


def create_market_data_provider(
    name: str,
    csv_path: str | Path | None = None,
) -> MarketDataProvider:
    provider_name = name.lower()
    if provider_name == "yfinance":
        return YFinanceProvider()
    if provider_name == "csv":
        if csv_path is None:
            raise ValueError("CSV provider requires data.csv_path")
        return CsvMarketDataProvider(csv_path)
    raise ValueError(f"Unsupported market data provider: {name}")


def normalize_yfinance_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    frame = raw.reset_index()
    frame.columns = [str(column).lower().replace(" ", "_") for column in frame.columns]

    rename_map = {
        "date": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "adj_close": "adj_close",
        "volume": "volume",
    }
    frame = frame.rename(columns=rename_map)

    if "adj_close" not in frame.columns:
        frame["adj_close"] = frame.get("close")

    frame["ticker"] = ticker

    for column in ["open", "high", "low", "close", "adj_close", "volume"]:
        if column not in frame.columns:
            frame[column] = pd.NA

    return frame[PRICE_COLUMNS].dropna(subset=["date", "close"])

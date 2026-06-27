"""Market data provider implementations."""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
import time
from typing import Protocol
import urllib.parse
import urllib.request

import pandas as pd

from aios.data.models import MarketDataRequest, MarketDataResult, PRICE_COLUMNS
from aios.data.quality import build_cache_coverage_report


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


STOOQ_SYMBOL_MAP = {
    "MSFT": "msft.us",
    "GOOGL": "googl.us",
    "AMZN": "amzn.us",
    "META": "meta.us",
    "AAPL": "aapl.us",
    "TSLA": "tsla.us",
    "NVDA": "nvda.us",
    "QQQ": "qqq.us",
    "SOXX": "soxx.us",
    "MU": "mu.us",
}


class StooqProvider:
    """Free Stooq CSV provider for supported symbols."""

    source_name = "stooq"

    def __init__(
        self,
        symbol_map: dict[str, str] | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.symbol_map = STOOQ_SYMBOL_MAP if symbol_map is None else symbol_map
        self.timeout_seconds = timeout_seconds

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for ticker in request.tickers:
            symbol = self.symbol_map.get(ticker)
            if symbol is None:
                logging.info("Stooq does not support ticker mapping for %s", ticker)
                continue

            raw = self._download_stooq_csv(symbol)
            normalized = normalize_stooq_frame(raw, ticker)
            normalized = _limit_lookback(normalized, request.lookback_days)
            if not normalized.empty:
                frames.append(normalized)

        if not frames:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        return pd.concat(frames, ignore_index=True)[PRICE_COLUMNS]

    def _download_stooq_csv(self, symbol: str) -> pd.DataFrame:
        query = urllib.parse.urlencode({"s": symbol, "i": "d"})
        url = f"https://stooq.com/q/d/l/?{query}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            payload = response.read()
        return pd.read_csv(io.BytesIO(payload))


class AlphaVantageProvider:
    """Optional Alpha Vantage daily provider enabled by environment key."""

    source_name = "alphavantage"

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: int = 20,
        max_requests_per_fetch: int = 5,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(
            "ALPHAVANTAGE_API_KEY"
        )
        self.timeout_seconds = timeout_seconds
        self.max_requests_per_fetch = max_requests_per_fetch

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        if not self.api_key:
            logging.info("Alpha Vantage provider disabled; API key is missing.")
            return pd.DataFrame(columns=PRICE_COLUMNS)

        frames: list[pd.DataFrame] = []
        for ticker in _us_tickers(request.tickers)[: self.max_requests_per_fetch]:
            raw = self._download_alpha_vantage(ticker, request.lookback_days)
            normalized = normalize_alpha_vantage_payload(raw, ticker)
            normalized = _limit_lookback(normalized, request.lookback_days)
            if not normalized.empty:
                frames.append(normalized)

        if not frames:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        return pd.concat(frames, ignore_index=True)[PRICE_COLUMNS]

    def _download_alpha_vantage(self, ticker: str, lookback_days: int) -> dict:
        outputsize = "full" if lookback_days > 100 else "compact"
        query = urllib.parse.urlencode(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": outputsize,
                "apikey": self.api_key,
            }
        )
        url = f"https://www.alphavantage.co/query?{query}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class FinnhubProvider:
    """Optional Finnhub daily candle provider enabled by environment key."""

    source_name = "finnhub"

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: int = 20,
        max_requests_per_fetch: int = 5,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get(
            "FINNHUB_API_KEY"
        )
        self.timeout_seconds = timeout_seconds
        self.max_requests_per_fetch = max_requests_per_fetch

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        if not self.api_key:
            logging.info("Finnhub provider disabled; API key is missing.")
            return pd.DataFrame(columns=PRICE_COLUMNS)

        frames: list[pd.DataFrame] = []
        for ticker in _us_tickers(request.tickers)[: self.max_requests_per_fetch]:
            raw = self._download_finnhub(ticker, request.lookback_days)
            normalized = normalize_finnhub_payload(raw, ticker)
            if not normalized.empty:
                frames.append(normalized)

        if not frames:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        return pd.concat(frames, ignore_index=True)[PRICE_COLUMNS]

    def _download_finnhub(self, ticker: str, lookback_days: int) -> dict:
        to_timestamp = int(time.time())
        from_timestamp = to_timestamp - (max(1, lookback_days) * 86400)
        query = urllib.parse.urlencode(
            {
                "symbol": ticker,
                "resolution": "D",
                "from": from_timestamp,
                "to": to_timestamp,
                "token": self.api_key,
            }
        )
        url = f"https://finnhub.io/api/v1/stock/candle?{query}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


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


class MultiSourceMarketDataProvider:
    """Try multiple providers, merge partial data, and report coverage."""

    source_name = "multi"

    def __init__(
        self,
        providers: list[MarketDataProvider],
        stale_price_days: int = 3,
    ) -> None:
        self.providers = providers
        self.stale_price_days = stale_price_days
        self.last_result: MarketDataResult | None = None

    def fetch(self, request: MarketDataRequest) -> pd.DataFrame:
        result = self.fetch_result(request)
        self.last_result = result
        return result.prices

    def fetch_result(self, request: MarketDataRequest) -> MarketDataResult:
        combined = pd.DataFrame(columns=[*PRICE_COLUMNS, "_source", "_priority"])
        used_sources: list[str] = []

        for priority, provider in enumerate(self.providers):
            provider_tickers = self._tickers_for_provider(
                provider,
                request.tickers,
                combined,
            )
            if not provider_tickers:
                continue

            provider_request = MarketDataRequest(
                tickers=provider_tickers,
                lookback_days=request.lookback_days,
            )
            try:
                fetched = provider.fetch(provider_request)
            except Exception as exc:  # pragma: no cover - defensive live-provider guard
                logging.warning("Provider %s failed: %s", provider.source_name, exc)
                continue
            if fetched.empty:
                continue

            before_rows = len(combined)
            sourced = _with_source_columns(fetched, provider.source_name, priority)
            combined = _merge_sourced_frames(combined, sourced)
            if len(combined) > before_rows and provider.source_name not in used_sources:
                used_sources.append(provider.source_name)

        prices = (
            combined[PRICE_COLUMNS].copy()
            if not combined.empty
            else pd.DataFrame(columns=PRICE_COLUMNS)
        )
        provider_by_ticker = _provider_by_latest_ticker(combined)
        coverage = build_cache_coverage_report(
            prices=prices,
            required_tickers=request.tickers,
            provider_by_ticker=provider_by_ticker,
            stale_price_days=self.stale_price_days,
        )
        provider_mix = "+".join(used_sources) if used_sources else "none"
        return MarketDataResult(
            prices=prices,
            provider_mix=provider_mix,
            provider_by_ticker=provider_by_ticker,
            coverage=coverage,
        )

    @staticmethod
    def _tickers_for_provider(
        provider: MarketDataProvider,
        required_tickers: list[str],
        combined: pd.DataFrame,
    ) -> list[str]:
        if provider.source_name in {"alphavantage", "finnhub"}:
            existing = (
                set(combined["ticker"].astype(str).unique())
                if not combined.empty
                else set()
            )
            return [ticker for ticker in required_tickers if ticker not in existing]
        return list(required_tickers)


def create_market_data_provider(
    name: str,
    csv_path: str | Path | None = None,
) -> MarketDataProvider:
    provider_name = name.lower()
    if provider_name == "multi":
        providers: list[MarketDataProvider] = [
            YFinanceProvider(),
            StooqProvider(),
            AlphaVantageProvider(),
            FinnhubProvider(),
        ]
        if csv_path is not None:
            providers.append(CsvMarketDataProvider(csv_path))
        return MultiSourceMarketDataProvider(providers)
    if provider_name == "yfinance":
        return YFinanceProvider()
    if provider_name == "stooq":
        return StooqProvider()
    if provider_name == "alphavantage":
        return AlphaVantageProvider()
    if provider_name == "finnhub":
        return FinnhubProvider()
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


def normalize_stooq_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if raw.empty or "Date" not in raw.columns:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    frame = raw.rename(
        columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    frame["ticker"] = ticker
    frame["adj_close"] = frame["close"]
    for column in ["open", "high", "low", "close", "adj_close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[PRICE_COLUMNS].dropna(subset=["date", "close"])


def normalize_alpha_vantage_payload(payload: dict, ticker: str) -> pd.DataFrame:
    series = payload.get("Time Series (Daily)", {})
    if not isinstance(series, dict) or not series:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    rows = []
    for date_value, values in series.items():
        rows.append(
            {
                "date": date_value,
                "ticker": ticker,
                "open": values.get("1. open"),
                "high": values.get("2. high"),
                "low": values.get("3. low"),
                "close": values.get("4. close"),
                "adj_close": values.get("5. adjusted close", values.get("4. close")),
                "volume": values.get("6. volume"),
            }
        )
    return _coerce_price_frame(pd.DataFrame(rows))


def normalize_finnhub_payload(payload: dict, ticker: str) -> pd.DataFrame:
    if payload.get("s") != "ok":
        return pd.DataFrame(columns=PRICE_COLUMNS)

    rows = []
    timestamps = payload.get("t", [])
    for index, timestamp in enumerate(timestamps):
        close = payload.get("c", [])[index]
        rows.append(
            {
                "date": pd.to_datetime(timestamp, unit="s").date().isoformat(),
                "ticker": ticker,
                "open": payload.get("o", [])[index],
                "high": payload.get("h", [])[index],
                "low": payload.get("l", [])[index],
                "close": close,
                "adj_close": close,
                "volume": payload.get("v", [])[index],
            }
        )
    return _coerce_price_frame(pd.DataFrame(rows))


def _coerce_price_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    for column in ["open", "high", "low", "close", "adj_close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[PRICE_COLUMNS].dropna(subset=["date", "close"])


def _limit_lookback(frame: pd.DataFrame, lookback_days: int) -> pd.DataFrame:
    if frame.empty or lookback_days <= 0:
        return frame
    limited = frame.copy()
    limited["date"] = pd.to_datetime(limited["date"])
    cutoff = limited["date"].max() - pd.Timedelta(days=lookback_days)
    limited = limited[limited["date"] >= cutoff]
    limited["date"] = limited["date"].dt.date.astype(str)
    return limited[PRICE_COLUMNS].reset_index(drop=True)


def _with_source_columns(
    frame: pd.DataFrame,
    source: str,
    priority: int,
) -> pd.DataFrame:
    sourced = frame[PRICE_COLUMNS].copy()
    sourced["ticker"] = sourced["ticker"].astype(str)
    sourced["date"] = pd.to_datetime(sourced["date"]).dt.date.astype(str)
    sourced["_source"] = source
    sourced["_priority"] = priority
    return sourced


def _merge_sourced_frames(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    combined = pd.concat([existing, incoming], ignore_index=True)
    if combined.empty:
        return combined
    combined["date"] = pd.to_datetime(combined["date"]).dt.date.astype(str)
    combined["ticker"] = combined["ticker"].astype(str)
    return (
        combined.sort_values(["ticker", "date", "_priority"])
        .drop_duplicates(subset=["date", "ticker"], keep="first")
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )


def _provider_by_latest_ticker(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    sorted_frame = frame.copy()
    sorted_frame["date"] = pd.to_datetime(sorted_frame["date"])
    latest = sorted_frame.sort_values(["ticker", "date"]).groupby("ticker").tail(1)
    return {
        str(row["ticker"]): str(row["_source"])
        for _, row in latest.iterrows()
    }


def _us_tickers(tickers: list[str]) -> list[str]:
    return [ticker for ticker in tickers if "." not in ticker]

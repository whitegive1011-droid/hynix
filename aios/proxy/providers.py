"""Tradable proxy price provider implementations."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Protocol
import urllib.parse
import urllib.request

import pandas as pd

from aios.config.models import ProxyConfig
from aios.proxy.models import (
    PROXY_PRICE_COLUMNS,
    PROXY_WARNING,
    ProxyPriceRequest,
    normalize_proxy_frame,
)


BINANCE_FUTURES_TICKER_URLS = [
    "https://www.binance.com/fapi/v1/ticker/24hr",
    "https://fapi.binance.com/fapi/v1/ticker/24hr",
]
BINANCE_FUTURES_TICKER_URL = BINANCE_FUTURES_TICKER_URLS[0]
BINANCE_SPOT_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"


class ProxyPriceProvider(Protocol):
    source_name: str

    def fetch(self, request: ProxyPriceRequest) -> pd.DataFrame:
        """Return normalized proxy price data."""


class TradableProxyPriceProvider:
    """Fetch proxy prices from configured providers in priority order."""

    source_name = "tradable_proxy"

    def __init__(self, providers: list[ProxyPriceProvider]) -> None:
        self.providers = providers

    def fetch(self, request: ProxyPriceRequest) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        covered: set[str] = set()
        for provider in self.providers:
            remaining_symbols = {
                ticker: symbol
                for ticker, symbol in request.symbols.items()
                if ticker not in covered and symbol
            }
            if not remaining_symbols:
                continue

            fetched = provider.fetch(
                ProxyPriceRequest(
                    symbols=remaining_symbols,
                    provider_priority=request.provider_priority,
                    session=request.session,
                )
            )
            if fetched.empty:
                continue
            normalized = normalize_proxy_frame(fetched)
            if normalized.empty:
                continue

            frames.append(normalized)
            covered.update(normalized["ticker"].astype(str).unique())

        if not frames:
            return pd.DataFrame(columns=PROXY_PRICE_COLUMNS)
        combined = pd.concat(frames, ignore_index=True)
        return (
            combined[PROXY_PRICE_COLUMNS]
            .drop_duplicates(subset=["date", "ticker"], keep="first")
            .sort_values(["ticker", "date"])
            .reset_index(drop=True)
        )


class OkxProxyPriceProvider:
    """Read-only OKX market ticker provider for configured proxy instruments."""

    source_name = "okx"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(self, request: ProxyPriceRequest) -> pd.DataFrame:
        rows = []
        for ticker, symbol in request.symbols.items():
            if not symbol:
                continue
            try:
                payload = self._download(symbol)
            except Exception:
                continue
            row = _okx_payload_to_row(payload, ticker, symbol, request.session)
            if row is not None:
                rows.append(row)
        return normalize_proxy_frame(pd.DataFrame(rows))

    def _download(self, symbol: str) -> dict:
        query = urllib.parse.urlencode({"instId": symbol})
        url = f"https://www.okx.com/api/v5/market/ticker?{query}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class BinanceProxyPriceProvider:
    """Read-only Binance 24hr ticker provider for configured proxy symbols."""

    source_name = "binance"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(self, request: ProxyPriceRequest) -> pd.DataFrame:
        rows = []
        for ticker, symbol in request.symbols.items():
            if not symbol:
                continue
            try:
                payload = self._download(symbol)
            except Exception as exc:
                logging.warning(
                    "Binance proxy fetch failed for %s (%s): %s",
                    ticker,
                    symbol,
                    exc,
                )
                continue
            row = _binance_payload_to_row(payload, ticker, symbol, request.session)
            if row is not None:
                rows.append(row)
        return normalize_proxy_frame(pd.DataFrame(rows))

    def _download(self, symbol: str) -> dict:
        last_error: Exception | None = None
        endpoint_order = [
            *[("USD-M futures", url) for url in BINANCE_FUTURES_TICKER_URLS],
            ("spot", BINANCE_SPOT_TICKER_URL),
        ]
        for market_type, base_url in endpoint_order:
            try:
                payload = self._download_from_url(base_url, symbol)
            except Exception as exc:
                last_error = exc
                logging.info(
                    "Binance proxy endpoint failed for %s via %s: %s",
                    symbol,
                    base_url,
                    exc,
                )
                continue
            payload["_aios_market_type"] = market_type
            return payload
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"No Binance endpoint configured for {symbol}.")

    def _download_from_url(self, base_url: str, symbol: str) -> dict:
        query = urllib.parse.urlencode({"symbol": symbol})
        url = f"{base_url}?{query}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class FixtureProxyPriceProvider:
    """Offline provider used by tests."""

    source_name = "fixture"

    def __init__(
        self,
        frame: pd.DataFrame | None = None,
        csv_path: str | Path | None = None,
    ) -> None:
        self.frame = frame
        self.csv_path = Path(csv_path) if csv_path is not None else None

    def fetch(self, request: ProxyPriceRequest) -> pd.DataFrame:
        if self.frame is not None:
            frame = self.frame.copy()
        elif self.csv_path is not None and self.csv_path.exists():
            frame = pd.read_csv(self.csv_path)
        else:
            return pd.DataFrame(columns=PROXY_PRICE_COLUMNS)

        normalized = normalize_proxy_frame(frame)
        if request.symbols:
            normalized = normalized[
                normalized["ticker"].astype(str).isin(request.symbols)
            ]
        return normalized.reset_index(drop=True)


def create_tradable_proxy_price_provider(
    config: ProxyConfig,
    fixture_frame: pd.DataFrame | None = None,
) -> TradableProxyPriceProvider:
    providers: list[ProxyPriceProvider] = []
    for name in config.provider_priority:
        provider_name = name.lower()
        if provider_name == "okx":
            providers.append(OkxProxyPriceProvider())
        elif provider_name == "binance":
            providers.append(BinanceProxyPriceProvider())
        elif provider_name == "fixture":
            providers.append(
                FixtureProxyPriceProvider(
                    frame=fixture_frame,
                    csv_path=config.fixture_path,
                )
            )
    return TradableProxyPriceProvider(providers)


def _okx_payload_to_row(
    payload: dict,
    ticker: str,
    symbol: str,
    session: str,
) -> dict | None:
    data = payload.get("data", [])
    if not data:
        return None
    ticker_data = data[0]
    price = _to_float(ticker_data.get("last"))
    if price is None or price <= 0:
        return None
    open_price = _to_float(ticker_data.get("open24h") or ticker_data.get("sodUtc0"))
    change_pct = _change_pct(price, open_price)
    timestamp = _timestamp_from_millis(ticker_data.get("ts"))
    return _proxy_row(
        ticker=ticker,
        symbol=symbol,
        price=price,
        change_pct=change_pct,
        source="OKX public market ticker",
        provider="okx",
        timestamp=timestamp,
        session=session,
    )


def _binance_payload_to_row(
    payload: dict,
    ticker: str,
    symbol: str,
    session: str,
) -> dict | None:
    price = _to_float(payload.get("lastPrice"))
    if price is None or price <= 0:
        return None
    timestamp = _timestamp_from_millis(payload.get("closeTime"))
    market_type = str(payload.get("_aios_market_type", "public"))
    return _proxy_row(
        ticker=ticker,
        symbol=symbol,
        price=price,
        change_pct=_to_float(payload.get("priceChangePercent")),
        source=f"Binance public {market_type} 24hr ticker",
        provider="binance",
        timestamp=timestamp,
        session=session,
    )


def _proxy_row(
    ticker: str,
    symbol: str,
    price: float,
    change_pct: float | None,
    source: str,
    provider: str,
    timestamp: str,
    session: str,
) -> dict:
    date_value = pd.to_datetime(timestamp).date().isoformat()
    return {
        "date": date_value,
        "ticker": ticker,
        "proxy_symbol": symbol,
        "proxy_price": price,
        "proxy_change_pct": change_pct,
        "source": source,
        "provider": provider,
        "timestamp": timestamp,
        "session": session,
        "warning": PROXY_WARNING,
    }


def _timestamp_from_millis(value: object) -> str:
    millis = _to_float(value)
    if millis is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    return datetime.fromtimestamp(millis / 1000, timezone.utc).isoformat(
        timespec="seconds"
    )


def _change_pct(price: float, open_price: float | None) -> float | None:
    if open_price is None or open_price <= 0:
        return None
    return ((price / open_price) - 1) * 100


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

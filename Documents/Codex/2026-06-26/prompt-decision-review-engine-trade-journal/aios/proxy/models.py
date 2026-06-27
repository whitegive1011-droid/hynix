"""Models for tradable proxy prices and intraday proxy signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


PROXY_WARNING = "Tradable proxy price is not official equity market data."

PROXY_PRICE_COLUMNS = [
    "date",
    "ticker",
    "proxy_symbol",
    "proxy_price",
    "proxy_change_pct",
    "source",
    "provider",
    "timestamp",
    "session",
    "warning",
]


@dataclass(frozen=True)
class ProxyPriceRequest:
    symbols: dict[str, str]
    provider_priority: list[str]
    session: str = "intraday"


@dataclass(frozen=True)
class ProxySignalSnapshot:
    available: bool = False
    provider_used: str = "none"
    symbols_used: dict[str, str] = field(default_factory=dict)
    tickers_covered: list[str] = field(default_factory=list)
    proxy_ai_1d_change: float | None = None
    proxy_hbm_1d_change: float | None = None
    proxy_risk_level: str = "N/A"
    proxy_data_quality: str = "Missing"
    proxy_official_conflict_flag: bool = False
    warning: str = PROXY_WARNING
    decision_influenced: bool = False

    @classmethod
    def empty(cls) -> "ProxySignalSnapshot":
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "provider_used": self.provider_used,
            "symbols_used": self.symbols_used,
            "tickers_covered": self.tickers_covered,
            "proxy_ai_1d_change": self.proxy_ai_1d_change,
            "proxy_hbm_1d_change": self.proxy_hbm_1d_change,
            "proxy_risk_level": self.proxy_risk_level,
            "proxy_data_quality": self.proxy_data_quality,
            "proxy_official_conflict_flag": self.proxy_official_conflict_flag,
            "warning": self.warning,
            "decision_influenced": self.decision_influenced,
        }


def normalize_proxy_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized proxy price frame with required columns."""

    if frame.empty:
        return pd.DataFrame(columns=PROXY_PRICE_COLUMNS)

    normalized = frame.copy()
    for column in PROXY_PRICE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized["date"] = pd.to_datetime(
        normalized["date"],
        errors="coerce",
    ).dt.date.astype(str)
    normalized["ticker"] = normalized["ticker"].astype(str)
    normalized["proxy_symbol"] = normalized["proxy_symbol"].astype(str)
    normalized["proxy_price"] = pd.to_numeric(
        normalized["proxy_price"],
        errors="coerce",
    )
    normalized["proxy_change_pct"] = pd.to_numeric(
        normalized["proxy_change_pct"],
        errors="coerce",
    )
    normalized["warning"] = PROXY_WARNING
    normalized = normalized.dropna(subset=["date", "ticker", "proxy_price"])
    normalized = normalized[normalized["date"] != "NaT"]
    normalized["_timestamp_sort"] = pd.to_datetime(
        normalized["timestamp"],
        errors="coerce",
    )
    return normalized.sort_values(
        ["ticker", "date", "provider", "_timestamp_sort"],
        na_position="first",
    )[PROXY_PRICE_COLUMNS].drop_duplicates(
        subset=["date", "ticker", "provider"],
        keep="last",
    )

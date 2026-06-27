"""Decision engine data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isnan
from typing import Any

import pandas as pd


class MarketMode(str, Enum):
    UPTREND = "Uptrend"
    RANGE = "Range"
    DOWNTREND = "Downtrend"
    MIXED = "Mixed"
    CAPITULATION = "Capitulation"
    RECOVERY = "Recovery"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass(frozen=True)
class BasketSnapshot:
    date: str
    ai_1d: float | None = None
    ai_5d: float | None = None
    ai_20d: float | None = None
    hbm_1d: float | None = None
    hbm_5d: float | None = None
    hbm_20d: float | None = None
    d5: float | None = None
    d20: float | None = None
    relative_ratio: float | None = None
    risk_score: float | None = None

    @classmethod
    def from_row(cls, row: pd.Series | dict[str, Any]) -> "BasketSnapshot":
        return cls(
            date=str(_get(row, "date")),
            ai_1d=_optional_float(_get(row, "AI_1D")),
            ai_5d=_optional_float(_get(row, "AI_5D")),
            ai_20d=_optional_float(_get(row, "AI_20D")),
            hbm_1d=_optional_float(_get(row, "HBM_1D")),
            hbm_5d=_optional_float(_get(row, "HBM_5D")),
            hbm_20d=_optional_float(_get(row, "HBM_20D")),
            d5=_optional_float(_get(row, "D5")),
            d20=_optional_float(_get(row, "D20")),
            relative_ratio=_optional_float(_get(row, "Relative_Ratio")),
            risk_score=_optional_float(_get(row, "Risk_Score")),
        )


@dataclass(frozen=True)
class TechnicalSnapshot:
    date: str
    ticker: str
    close: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    ema_20: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None
    adx14: float | None = None

    @classmethod
    def from_row(cls, row: pd.Series | dict[str, Any]) -> "TechnicalSnapshot":
        return cls(
            date=str(_get(row, "date")),
            ticker=str(_get(row, "ticker")),
            close=_optional_float(_get(row, "close")),
            sma_20=_optional_float(_get(row, "sma_20")),
            sma_50=_optional_float(_get(row, "sma_50")),
            ema_20=_optional_float(_get(row, "ema_20")),
            rsi14=_optional_float(_get(row, "rsi14")),
            macd=_optional_float(_get(row, "macd")),
            macd_signal=_optional_float(_get(row, "macd_signal")),
            bollinger_upper=_optional_float(_get(row, "bollinger_upper")),
            bollinger_lower=_optional_float(_get(row, "bollinger_lower")),
            adx14=_optional_float(_get(row, "adx14")),
        )


@dataclass(frozen=True)
class PortfolioPosition:
    ticker: str
    current_shares: int


@dataclass(frozen=True)
class DecisionDataQuality:
    """Data quality context used to guard recommendations."""

    missing_tickers: list[str] = field(default_factory=list)
    stale_tickers: list[str] = field(default_factory=list)
    data_quality_score: int = 100
    required_basket_tickers_missing: bool = False


@dataclass(frozen=True)
class DecisionInput:
    basket: BasketSnapshot
    technical: TechnicalSnapshot
    position: PortfolioPosition
    data_quality: DecisionDataQuality = field(default_factory=DecisionDataQuality)


@dataclass(frozen=True)
class DecisionResult:
    date: str
    market_mode: MarketMode
    recommendation: str
    confidence: int
    reasons: list[str]
    risk_level: RiskLevel
    current_position: int
    suggested_position: int
    position_delta: int
    triggered_rules: list[str] = field(default_factory=list)


def _get(row: pd.Series | dict[str, Any], key: str) -> Any:
    if isinstance(row, pd.Series):
        return row.get(key)
    return row.get(key)


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    result = float(value)
    if isnan(result):
        return None
    return result

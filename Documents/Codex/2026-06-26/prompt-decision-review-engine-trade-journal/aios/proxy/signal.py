"""Proxy intraday market signal calculation."""

from __future__ import annotations

import pandas as pd

from aios.decision.models import BasketSnapshot
from aios.proxy.models import (
    PROXY_PRICE_COLUMNS,
    ProxySignalSnapshot,
    normalize_proxy_frame,
)


class ProxySignalEngine:
    """Build an intraday proxy signal without altering official metrics."""

    def __init__(
        self,
        ai_tickers: list[str],
        hbm_weights: dict[str, float],
        manual_official_tickers: list[str] | None = None,
    ) -> None:
        self.ai_tickers = [str(ticker) for ticker in ai_tickers]
        self.hbm_tickers = sorted({*hbm_weights.keys(), "MU", "NVDA"})
        self.manual_official_tickers = set(manual_official_tickers or [])

    def build(
        self,
        proxy_prices: pd.DataFrame,
        official_basket: BasketSnapshot | None = None,
    ) -> ProxySignalSnapshot:
        if proxy_prices.empty:
            return ProxySignalSnapshot.empty()

        frame = normalize_proxy_frame(proxy_prices)
        if frame.empty:
            return ProxySignalSnapshot.empty()
        if self.manual_official_tickers:
            frame = frame[
                ~frame["ticker"].astype(str).isin(self.manual_official_tickers)
            ]
        if frame.empty:
            return ProxySignalSnapshot.empty()

        latest = _latest_proxy_rows(frame)
        ai_change = _mean_change(latest, self.ai_tickers)
        hbm_change = _mean_change(latest, self.hbm_tickers)
        risk_level = _proxy_risk_level(ai_change, hbm_change)
        conflict = _official_conflict(
            proxy_ai_change=ai_change,
            proxy_hbm_change=hbm_change,
            proxy_risk_level=risk_level,
            official_basket=official_basket,
        )
        providers = sorted(latest["provider"].astype(str).unique())
        symbols_used = {
            str(row["ticker"]): str(row["proxy_symbol"])
            for _, row in latest.iterrows()
        }
        tickers_covered = sorted(latest["ticker"].astype(str).unique())

        return ProxySignalSnapshot(
            available=bool(tickers_covered),
            provider_used="+".join(providers) if providers else "none",
            symbols_used=symbols_used,
            tickers_covered=tickers_covered,
            proxy_ai_1d_change=ai_change,
            proxy_hbm_1d_change=hbm_change,
            proxy_risk_level=risk_level,
            proxy_data_quality=_proxy_data_quality(ai_change, hbm_change),
            proxy_official_conflict_flag=conflict,
        )


def _latest_proxy_rows(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame[PROXY_PRICE_COLUMNS].copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        errors="coerce",
    )
    normalized = normalized.sort_values(["ticker", "timestamp"])
    return normalized.groupby("ticker", as_index=False).tail(1).reset_index(drop=True)


def _mean_change(frame: pd.DataFrame, tickers: list[str]) -> float | None:
    selected = frame[frame["ticker"].astype(str).isin(tickers)]
    if selected.empty:
        return None
    values = pd.to_numeric(selected["proxy_change_pct"], errors="coerce").dropna()
    if values.empty:
        return None
    return round(float(values.mean()), 4)


def _proxy_risk_level(
    ai_change: float | None,
    hbm_change: float | None,
) -> str:
    if hbm_change is not None and hbm_change <= -5.0:
        return "Strong Risk-Off"
    if hbm_change is not None and hbm_change <= -3.0:
        return "Risk-Off"
    if (
        ai_change is not None
        and hbm_change is not None
        and ai_change >= 2.0
        and hbm_change >= 2.0
    ):
        return "Risk-On"
    return "Neutral"


def _proxy_data_quality(
    ai_change: float | None,
    hbm_change: float | None,
) -> str:
    if ai_change is None and hbm_change is None:
        return "Missing"
    if ai_change is None or hbm_change is None:
        return "Partial"
    return "OK"


def _official_conflict(
    proxy_ai_change: float | None,
    proxy_hbm_change: float | None,
    proxy_risk_level: str,
    official_basket: BasketSnapshot | None,
) -> bool:
    if official_basket is None:
        return False

    official_ai = official_basket.ai_1d
    official_hbm = official_basket.hbm_1d
    if official_ai is None and official_hbm is None:
        return False

    if proxy_risk_level in {"Risk-Off", "Strong Risk-Off"}:
        return _gte_any([official_ai, official_hbm], 2.0)
    if proxy_risk_level == "Risk-On":
        return _lte_any([official_ai, official_hbm], -2.0)

    if proxy_hbm_change is not None and official_hbm is not None:
        return abs(proxy_hbm_change - official_hbm) >= 5.0
    if proxy_ai_change is not None and official_ai is not None:
        return abs(proxy_ai_change - official_ai) >= 5.0
    return False


def _gte_any(values: list[float | None], threshold: float) -> bool:
    return any(value is not None and value >= threshold for value in values)


def _lte_any(values: list[float | None], threshold: float) -> bool:
    return any(value is not None and value <= threshold for value in values)


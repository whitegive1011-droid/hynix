"""Basket metric calculations for AIOS."""

from __future__ import annotations

import numpy as np
import pandas as pd

from aios.data.models import PRICE_COLUMNS


BASKET_COLUMNS = [
    "date",
    "AI_Basket",
    "HBM_Basket",
    "AI_1D",
    "AI_5D",
    "AI_20D",
    "HBM_1D",
    "HBM_5D",
    "HBM_20D",
    "D1",
    "D5",
    "D20",
    "Relative_Ratio",
    "Risk_Score",
]


def calculate_basket_metrics(
    prices: pd.DataFrame,
    ai_tickers: list[str],
    hbm_weights: dict[str, float],
) -> pd.DataFrame:
    """Calculate AI/HBM basket indexes, returns, spread, and risk score."""

    _validate_price_columns(prices)
    if prices.empty:
        return pd.DataFrame(columns=BASKET_COLUMNS)

    indexed_prices = _indexed_price_pivot(prices)
    ai_basket = _equal_weight_basket(indexed_prices, ai_tickers)
    hbm_basket = _weighted_basket(indexed_prices, hbm_weights)
    daily_change_pct = _daily_change_pct_pivot(prices).reindex(indexed_prices.index)

    metrics = pd.DataFrame(
        {
            "date": indexed_prices.index,
            "AI_Basket": ai_basket,
            "HBM_Basket": hbm_basket,
        }
    ).reset_index(drop=True)

    for horizon in [1, 5, 20]:
        metrics[f"AI_{horizon}D"] = (
            metrics["AI_Basket"].pct_change(horizon, fill_method=None) * 100
        )
        metrics[f"HBM_{horizon}D"] = (
            metrics["HBM_Basket"].pct_change(horizon, fill_method=None) * 100
        )

    if not daily_change_pct.empty:
        ai_1d_override = _equal_weight_basket(daily_change_pct, ai_tickers)
        hbm_1d_override = _weighted_basket(daily_change_pct, hbm_weights)
        metrics["AI_1D"] = _override_by_date(
            metrics,
            "AI_1D",
            ai_1d_override,
        )
        metrics["HBM_1D"] = _override_by_date(
            metrics,
            "HBM_1D",
            hbm_1d_override,
        )

    metrics["D1"] = metrics["HBM_1D"] - metrics["AI_1D"]
    metrics["D5"] = metrics["HBM_5D"] - metrics["AI_5D"]
    metrics["D20"] = metrics["HBM_20D"] - metrics["AI_20D"]
    metrics["Relative_Ratio"] = metrics["HBM_Basket"] / metrics["AI_Basket"]
    metrics["Risk_Score"] = (
        (-metrics["AI_5D"]).clip(lower=0)
        + metrics["HBM_5D"].clip(lower=0)
        + (metrics["D5"] - 10.0).clip(lower=0)
    )
    metrics["Risk_Score"] = metrics["Risk_Score"].replace([np.inf, -np.inf], np.nan)

    metrics["date"] = pd.to_datetime(metrics["date"]).dt.date.astype(str)
    return metrics[BASKET_COLUMNS]


def _validate_price_columns(prices: pd.DataFrame) -> None:
    missing_columns = [col for col in PRICE_COLUMNS if col not in prices.columns]
    if missing_columns:
        raise ValueError(f"Price data missing columns: {missing_columns}")


def _indexed_price_pivot(prices: pd.DataFrame) -> pd.DataFrame:
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["ticker"] = frame["ticker"].astype(str)
    frame["price"] = frame["adj_close"].where(frame["adj_close"].notna(), frame["close"])
    pivot = (
        frame.pivot_table(
            index="date",
            columns="ticker",
            values="price",
            aggfunc="last",
        )
        .sort_index()
        .astype(float)
    )
    indexed = (
        pivot.divide(pivot.apply(lambda series: series.dropna().iloc[0]), axis=1) * 100
    )
    return _apply_manual_change_pct_index(indexed, frame)


def _apply_manual_change_pct_index(
    indexed_prices: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    daily_change_pct = _daily_change_pct_pivot(prices).reindex(indexed_prices.index)
    if daily_change_pct.empty:
        return indexed_prices

    adjusted = indexed_prices.copy()
    for ticker in adjusted.columns:
        if ticker not in daily_change_pct.columns:
            continue
        ticker_changes = daily_change_pct[ticker]
        ticker_index = adjusted[ticker].copy()
        for position in range(1, len(ticker_index)):
            if pd.isna(ticker_index.iloc[position - 1]):
                continue
            change_pct = ticker_changes.iloc[position]
            if pd.notna(change_pct):
                ticker_index.iloc[position] = ticker_index.iloc[position - 1] * (
                    1 + (change_pct / 100)
                )
        adjusted[ticker] = ticker_index
    return adjusted


def _daily_change_pct_pivot(prices: pd.DataFrame) -> pd.DataFrame:
    if "change_pct" not in prices.columns:
        return pd.DataFrame()

    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["ticker"] = frame["ticker"].astype(str)
    frame["change_pct"] = pd.to_numeric(frame["change_pct"], errors="coerce")
    if frame["change_pct"].isna().all():
        return pd.DataFrame()

    return (
        frame.pivot_table(
            index="date",
            columns="ticker",
            values="change_pct",
            aggfunc="last",
        )
        .sort_index()
        .astype(float)
    )


def _override_by_date(
    metrics: pd.DataFrame,
    column: str,
    override: pd.Series,
) -> pd.Series:
    override_values = pd.to_datetime(metrics["date"]).map(override)
    return override_values.combine_first(metrics[column])


def _equal_weight_basket(indexed_prices: pd.DataFrame, tickers: list[str]) -> pd.Series:
    available = [ticker for ticker in tickers if ticker in indexed_prices.columns]
    if not available:
        return pd.Series(np.nan, index=indexed_prices.index)
    return indexed_prices[available].mean(axis=1)


def _weighted_basket(
    indexed_prices: pd.DataFrame,
    weights: dict[str, float],
) -> pd.Series:
    available_weights = {
        ticker: float(weight)
        for ticker, weight in weights.items()
        if ticker in indexed_prices.columns
    }
    if not available_weights:
        return pd.Series(np.nan, index=indexed_prices.index)

    selected = indexed_prices[list(available_weights)]
    weight_series = pd.Series(available_weights, dtype=float)
    weighted_sum = selected.mul(weight_series, axis=1).sum(axis=1, min_count=1)
    available_weight_sum = selected.notna().mul(weight_series, axis=1).sum(axis=1)
    return weighted_sum / available_weight_sum.replace(0, np.nan)

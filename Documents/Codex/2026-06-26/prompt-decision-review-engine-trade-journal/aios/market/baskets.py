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

    metrics = pd.DataFrame(
        {
            "date": indexed_prices.index,
            "AI_Basket": ai_basket,
            "HBM_Basket": hbm_basket,
        }
    ).reset_index(drop=True)

    for horizon in [1, 5, 20]:
        metrics[f"AI_{horizon}D"] = metrics["AI_Basket"].pct_change(horizon) * 100
        metrics[f"HBM_{horizon}D"] = (
            metrics["HBM_Basket"].pct_change(horizon) * 100
        )

    metrics["D5"] = metrics["HBM_5D"] - metrics["AI_5D"]
    metrics["D20"] = metrics["HBM_20D"] - metrics["AI_20D"]
    metrics["Relative_Ratio"] = metrics["HBM_Basket"] / metrics["AI_Basket"]
    metrics["Risk_Score"] = (
        metrics["AI_5D"].apply(lambda value: max(0.0, -value))
        + metrics["HBM_5D"].apply(lambda value: max(0.0, value))
        + metrics["D5"].apply(lambda value: max(0.0, value - 10.0))
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
    return pivot.divide(pivot.apply(lambda series: series.dropna().iloc[0]), axis=1) * 100


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

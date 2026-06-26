"""Technical indicator calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from aios.data.models import PRICE_COLUMNS


def add_technical_indicators(
    prices: pd.DataFrame,
    ma_windows: list[int] | None = None,
    ema_windows: list[int] | None = None,
    rsi_period: int = 14,
    atr_period: int = 14,
    adx_period: int = 14,
    bollinger_period: int = 20,
    bollinger_std: float = 2.0,
) -> pd.DataFrame:
    """Return price data enriched with common technical indicators."""

    _validate_price_columns(prices)
    ma_windows = ma_windows or [20, 50, 100, 200]
    ema_windows = ema_windows or [20, 50, 100, 200]

    if prices.empty:
        return prices.copy()

    enriched = (
        prices.copy()
        .assign(date=lambda frame: pd.to_datetime(frame["date"]))
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )

    groups = enriched.groupby("ticker", group_keys=False)
    for window in ma_windows:
        enriched[f"sma_{window}"] = groups["close"].transform(
            lambda series: series.rolling(window=window).mean()
        )
        enriched[f"ma_{window}"] = enriched[f"sma_{window}"]

    for window in ema_windows:
        enriched[f"ema_{window}"] = groups["close"].transform(
            lambda series: series.ewm(span=window, adjust=False).mean()
        )

    enriched["rsi14"] = groups["close"].transform(
        lambda series: _rsi(series, period=rsi_period)
    )
    enriched = _apply_by_ticker(enriched, _add_macd)
    enriched = _apply_by_ticker(
        enriched,
        lambda frame: _add_bollinger_bands(
            frame,
            period=bollinger_period,
            std_multiplier=bollinger_std,
        )
    )
    enriched = _apply_by_ticker(
        enriched,
        lambda frame: _add_atr_adx(
            frame,
            atr_period=atr_period,
            adx_period=adx_period,
        )
    )
    enriched["date"] = enriched["date"].dt.date.astype(str)

    return enriched


def _validate_price_columns(prices: pd.DataFrame) -> None:
    missing_columns = [col for col in PRICE_COLUMNS if col not in prices.columns]
    if missing_columns:
        raise ValueError(f"Price data missing columns: {missing_columns}")


def _apply_by_ticker(
    prices: pd.DataFrame,
    transform,
) -> pd.DataFrame:
    frames = [
        transform(group.copy())
        for _, group in prices.groupby("ticker", sort=False)
    ]
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["ticker", "date"])
        .reset_index(drop=True)
    )


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    average_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative_strength))
    return rsi.fillna(100).where(average_loss != 0, 100)


def _add_macd(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"]
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    frame = frame.copy()
    frame["macd"] = ema_12 - ema_26
    frame["macd_signal"] = frame["macd"].ewm(span=9, adjust=False).mean()
    frame["macd_histogram"] = frame["macd"] - frame["macd_signal"]
    return frame


def _add_bollinger_bands(
    frame: pd.DataFrame,
    period: int,
    std_multiplier: float,
) -> pd.DataFrame:
    close = frame["close"]
    middle = close.rolling(window=period).mean()
    rolling_std = close.rolling(window=period).std()
    frame = frame.copy()
    frame["bollinger_middle"] = middle
    frame["bollinger_upper"] = middle + (rolling_std * std_multiplier)
    frame["bollinger_lower"] = middle - (rolling_std * std_multiplier)
    return frame


def _add_atr_adx(
    frame: pd.DataFrame,
    atr_period: int,
    adx_period: int,
) -> pd.DataFrame:
    frame = frame.copy()
    high = frame["high"]
    low = frame["low"]
    close = frame["close"]
    previous_close = close.shift(1)

    high_low = high - low
    high_previous_close = (high - previous_close).abs()
    low_previous_close = (low - previous_close).abs()
    true_range = pd.concat(
        [high_low, high_previous_close, low_previous_close],
        axis=1,
    ).max(axis=1)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=frame.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=frame.index,
    )

    atr = true_range.ewm(alpha=1 / atr_period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / adx_period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / adx_period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)

    frame["atr14"] = atr
    frame["plus_di14"] = plus_di.replace([np.inf, -np.inf], np.nan)
    frame["minus_di14"] = minus_di.replace([np.inf, -np.inf], np.nan)
    frame["adx14"] = dx.ewm(alpha=1 / adx_period, adjust=False).mean()
    frame["adx14"] = frame["adx14"].replace([np.inf, -np.inf], np.nan)
    return frame

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from aios.config.loader import load_config
from aios.data.models import MarketDataRequest
from aios.data.providers import CsvMarketDataProvider
from aios.decision.engine import DecisionEngine
from aios.decision.models import (
    BasketSnapshot,
    DecisionDataQuality,
    DecisionInput,
    MarketMode,
    PortfolioPosition,
    RiskLevel,
    TechnicalSnapshot,
)
from aios.market.baskets import calculate_basket_metrics
from aios.market.indicators import add_technical_indicators
from aios.proxy.models import ProxySignalSnapshot


def test_decision_config_loads_rule_thresholds() -> None:
    config = load_config("config.yaml")

    assert config.decision.max_single_adjustment_shares == 100
    assert config.decision.capitulation_min_risk_score == 80
    assert config.decision.confidence_by_mode["Mixed"] == 38


def test_uptrend_recommends_hold() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(),
            technical=_technical(
                close=120,
                sma_20=110,
                sma_50=100,
                rsi14=62,
                macd=3,
                macd_signal=1,
                adx14=28,
            ),
            shares=300,
        )
    )

    assert result.market_mode == MarketMode.UPTREND
    assert result.recommendation == "Hold"
    assert result.suggested_position == 300
    assert result.position_delta == 0
    assert result.risk_level == RiskLevel.LOW
    assert result.reasons


def test_downtrend_recommends_gradual_reduce() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(risk_score=60),
            technical=_technical(
                close=88,
                sma_20=100,
                sma_50=105,
                rsi14=38,
                macd=-2,
                macd_signal=-1,
                adx14=30,
            ),
            shares=300,
        )
    )

    assert result.market_mode == MarketMode.DOWNTREND
    assert result.recommendation == "Reduce 100 Shares"
    assert result.suggested_position == 200
    assert result.position_delta == -100


def test_capitulation_is_high_risk_and_reduces_if_holding() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(ai_5d=-9, hbm_5d=-13, risk_score=85),
            technical=_technical(close=80, sma_20=100, sma_50=110),
            shares=300,
        )
    )

    assert result.market_mode == MarketMode.CAPITULATION
    assert result.risk_level == RiskLevel.HIGH
    assert result.recommendation == "Reduce 100 Shares"
    assert result.suggested_position == 200


def test_recovery_recommends_add_back() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(ai_5d=2, hbm_5d=5, relative_ratio=1.04),
            technical=_technical(
                close=115,
                sma_20=108,
                sma_50=100,
                rsi14=58,
                macd=2,
                macd_signal=1,
                adx14=22,
            ),
            shares=200,
        )
    )

    assert result.market_mode == MarketMode.RECOVERY
    assert result.recommendation == "Add Back 100 Shares"
    assert result.suggested_position == 300
    assert result.position_delta == 100


def test_range_sell_signal_recommends_reduce() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(),
            technical=_technical(
                close=110,
                sma_20=105,
                sma_50=103,
                rsi14=65,
                macd=0,
                macd_signal=1,
                bollinger_upper=110,
                bollinger_lower=90,
                adx14=16,
            ),
            shares=300,
        )
    )

    assert result.market_mode == MarketMode.RANGE
    assert result.recommendation == "Reduce 100 Shares"
    assert result.suggested_position == 200


def test_range_buy_signal_recommends_add_back() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(),
            technical=_technical(
                close=90,
                sma_20=91,
                sma_50=85,
                rsi14=35,
                macd=0,
                macd_signal=1,
                bollinger_upper=110,
                bollinger_lower=90,
                adx14=14,
            ),
            shares=200,
        )
    )

    assert result.market_mode == MarketMode.RANGE
    assert result.recommendation == "Add Back 100 Shares"
    assert result.suggested_position == 300


def test_mixed_recommends_uncertain() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(),
            technical=_technical(
                close=100,
                sma_20=100,
                sma_50=100,
                rsi14=72,
                macd=0,
                macd_signal=0,
                adx14=12,
            ),
            shares=300,
        )
    )

    assert result.market_mode == MarketMode.MIXED
    assert result.recommendation == "Uncertain"
    assert result.confidence < load_config("config.yaml").decision.uncertain_confidence_below


def test_low_data_quality_forces_uncertain_without_position_change() -> None:
    result = _engine().decide(
        _input(
            basket=_basket(),
            technical=_technical(
                close=120,
                sma_20=110,
                sma_50=100,
                rsi14=62,
                macd=3,
                macd_signal=1,
                adx14=28,
            ),
            shares=300,
            data_quality=DecisionDataQuality(
                missing_tickers=["AI1"],
                data_quality_score=40,
                required_basket_tickers_missing=True,
            ),
        )
    )

    assert result.market_mode == MarketMode.MIXED
    assert result.recommendation == "Uncertain"
    assert result.suggested_position == 300
    assert result.position_delta == 0
    assert "data_quality.insufficient" in result.triggered_rules


def test_missing_official_and_missing_proxy_remains_uncertain() -> None:
    result = _engine().decide(
        _input(
            basket=BasketSnapshot(date="2026-06-26"),
            technical=TechnicalSnapshot(date="2026-06-26", ticker="7709.HK"),
            shares=300,
            data_quality=DecisionDataQuality(
                missing_tickers=["MSFT", "MU"],
                data_quality_score=0,
                required_basket_tickers_missing=True,
            ),
            proxy_signal=ProxySignalSnapshot.empty(),
        )
    )

    assert result.recommendation == "Uncertain"
    assert result.suggested_position == 300
    assert result.position_delta == 0
    assert result.proxy_influenced is False


def test_proxy_only_neutral_signal_produces_watch_with_capped_confidence() -> None:
    config = load_config("config.yaml")
    result = _engine().decide(
        _input(
            basket=BasketSnapshot(date="2026-06-26"),
            technical=TechnicalSnapshot(date="2026-06-26", ticker="7709.HK"),
            shares=300,
            data_quality=DecisionDataQuality(
                missing_tickers=["MSFT", "MU"],
                data_quality_score=35,
                required_basket_tickers_missing=True,
            ),
            proxy_signal=ProxySignalSnapshot(
                available=True,
                provider_used="fixture",
                tickers_covered=["AAPL", "MSFT", "MU", "NVDA", "TSLA"],
                proxy_ai_1d_change=0.5,
                proxy_hbm_1d_change=0.2,
                proxy_risk_level="Neutral",
                proxy_data_quality="OK",
            ),
        )
    )

    assert result.recommendation == "Proxy-Based Watch"
    assert result.confidence <= config.proxy.max_confidence_when_proxy_only
    assert result.proxy_influenced is True
    assert "Official equity data is incomplete." in result.reasons
    assert (
        "Tradable proxy data is used for intraday risk assessment only."
        in result.reasons
    )
    assert "Proxy data is not official equity market data." in result.reasons


def test_proxy_only_strong_risk_off_can_reduce_with_capped_confidence() -> None:
    config = load_config("config.yaml")
    result = _engine().decide(
        _input(
            basket=BasketSnapshot(date="2026-06-26"),
            technical=TechnicalSnapshot(date="2026-06-26", ticker="7709.HK"),
            shares=300,
            data_quality=DecisionDataQuality(
                missing_tickers=["MSFT", "MU"],
                data_quality_score=35,
                required_basket_tickers_missing=True,
            ),
            proxy_signal=ProxySignalSnapshot(
                available=True,
                provider_used="fixture",
                tickers_covered=["AAPL", "MSFT", "MU", "NVDA", "TSLA"],
                proxy_ai_1d_change=-2.5,
                proxy_hbm_1d_change=-6.2,
                proxy_risk_level="Strong Risk-Off",
                proxy_data_quality="OK",
            ),
        )
    )

    assert result.recommendation == "Reduce 100 Shares"
    assert result.suggested_position == 200
    assert result.position_delta == -100
    assert result.risk_level == RiskLevel.HIGH
    assert result.confidence <= config.proxy.max_confidence_when_proxy_only


def test_proxy_official_conflict_caps_confidence_when_official_data_complete() -> None:
    config = load_config("config.yaml")
    result = _engine().decide(
        _input(
            basket=_basket(),
            technical=_technical(
                close=120,
                sma_20=110,
                sma_50=100,
                rsi14=62,
                macd=3,
                macd_signal=1,
                adx14=28,
            ),
            shares=300,
            proxy_signal=ProxySignalSnapshot(
                available=True,
                provider_used="fixture",
                tickers_covered=["AAPL", "MSFT", "MU", "NVDA", "TSLA"],
                proxy_ai_1d_change=-2.0,
                proxy_hbm_1d_change=-6.0,
                proxy_risk_level="Strong Risk-Off",
                proxy_data_quality="OK",
                proxy_official_conflict_flag=True,
            ),
        )
    )

    assert result.recommendation == "Hold"
    assert result.confidence <= config.proxy.max_confidence_when_proxy_conflict
    assert result.proxy_influenced is True
    assert "proxy.official_conflict" in result.triggered_rules


def test_decision_engine_accepts_csv_provider_outputs(tmp_path: Path) -> None:
    csv_path = _write_decision_fixture(tmp_path)
    prices = CsvMarketDataProvider(csv_path).fetch(
        MarketDataRequest(
            tickers=["AI1", "AI2", "HBM1", "HBM2"],
            lookback_days=60,
        )
    )
    basket_metrics = calculate_basket_metrics(
        prices,
        ai_tickers=["AI1", "AI2"],
        hbm_weights={"HBM1": 0.5, "HBM2": 0.5},
    )
    technicals = add_technical_indicators(
        prices[prices["ticker"] == "HBM1"],
        ma_windows=[20, 50],
        ema_windows=[20],
    )

    result = _engine().decide(
        _input(
            basket=BasketSnapshot.from_row(basket_metrics.iloc[-1]),
            technical=TechnicalSnapshot.from_row(technicals.iloc[-1]),
            shares=200,
        )
    )

    assert result.recommendation in {
        "Hold",
        "Add Back 100 Shares",
        "Reduce 100 Shares",
        "Watch",
        "Uncertain",
        "High Risk",
    }
    assert result.reasons
    assert isinstance(result.suggested_position, int)


def _engine() -> DecisionEngine:
    config = load_config("config.yaml")
    return DecisionEngine(config.decision, config.proxy)


def _input(
    basket: BasketSnapshot,
    technical: TechnicalSnapshot,
    shares: int,
    data_quality: DecisionDataQuality | None = None,
    proxy_signal: ProxySignalSnapshot | None = None,
) -> DecisionInput:
    return DecisionInput(
        basket=basket,
        technical=technical,
        position=PortfolioPosition(ticker="7709.HK", current_shares=shares),
        data_quality=data_quality or DecisionDataQuality(),
        proxy_signal=proxy_signal or ProxySignalSnapshot.empty(),
    )


def _basket(
    ai_5d: float = 0,
    hbm_5d: float = 0,
    risk_score: float = 0,
    relative_ratio: float = 1,
) -> BasketSnapshot:
    return BasketSnapshot(
        date="2026-06-26",
        ai_1d=0,
        ai_5d=ai_5d,
        ai_20d=0,
        hbm_1d=0,
        hbm_5d=hbm_5d,
        hbm_20d=0,
        d5=hbm_5d - ai_5d,
        d20=0,
        relative_ratio=relative_ratio,
        risk_score=risk_score,
    )


def _technical(
    close: float,
    sma_20: float,
    sma_50: float,
    rsi14: float = 50,
    macd: float = 0,
    macd_signal: float = 0,
    bollinger_upper: float = 130,
    bollinger_lower: float = 90,
    adx14: float = 20,
) -> TechnicalSnapshot:
    return TechnicalSnapshot(
        date="2026-06-26",
        ticker="7709.HK",
        close=close,
        sma_20=sma_20,
        sma_50=sma_50,
        ema_20=sma_20,
        rsi14=rsi14,
        macd=macd,
        macd_signal=macd_signal,
        bollinger_upper=bollinger_upper,
        bollinger_lower=bollinger_lower,
        adx14=adx14,
    )


def _write_decision_fixture(tmp_path: Path) -> Path:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(60):
        rows.extend(
            [
                _row(start, offset, "AI1", 100 + offset),
                _row(start, offset, "AI2", 100 + offset),
                _row(start, offset, "HBM1", 100 + (offset * 1.5)),
                _row(start, offset, "HBM2", 100 + offset),
            ]
        )

    csv_path = tmp_path / "decision_prices.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


def _row(start: date, offset: int, ticker: str, close: float) -> dict[str, object]:
    return {
        "date": start + timedelta(days=offset),
        "ticker": ticker,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "adj_close": close,
        "volume": 1000 + offset,
    }

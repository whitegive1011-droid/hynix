"""Typed configuration models for AIOS."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _as_float(value: Any, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


@dataclass
class AppConfig:
    timezone: str = "Asia/Shanghai"
    output_dir: Path = Path("outputs")
    log_level: str = "INFO"
    run_mode: str = "daily"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            timezone=str(data.get("timezone", cls.timezone)),
            output_dir=Path(data.get("output_dir", "outputs")),
            log_level=str(data.get("log_level", cls.log_level)).upper(),
            run_mode=str(data.get("run_mode", cls.run_mode)),
        )


@dataclass(frozen=True)
class DataConfig:
    primary_provider: str = "yfinance"
    fallback_provider: str = "cache"
    lookback_days: int = 260
    required_tickers: list[str] = field(default_factory=list)
    csv_path: Path | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "DataConfig":
        tickers = data.get("required_tickers", [])
        if not isinstance(tickers, list):
            raise ValueError("data.required_tickers must be a list")
        return cls(
            primary_provider=str(
                data.get("primary_provider", cls.primary_provider)
            ),
            fallback_provider=str(
                data.get("fallback_provider", cls.fallback_provider)
            ),
            lookback_days=_as_int(data.get("lookback_days"), cls.lookback_days),
            required_tickers=[str(ticker) for ticker in tickers],
            csv_path=(
                Path(data["csv_path"])
                if data.get("csv_path") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class DataQualityConfig:
    max_data_age_hours: int = 36
    max_missing_data_ratio: float = 0.05
    stale_price_days: int = 3
    abnormal_daily_move_pct: float = 20.0
    confidence_penalty: dict[str, int] = field(
        default_factory=lambda: {"warning": 10, "degraded": 25, "failed": 50}
    )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "DataQualityConfig":
        penalties = data.get("confidence_penalty", None)
        if penalties is None:
            penalties = cls().confidence_penalty
        if not isinstance(penalties, dict):
            raise ValueError("data_quality.confidence_penalty must be a mapping")

        return cls(
            max_data_age_hours=_as_int(
                data.get("max_data_age_hours"), cls.max_data_age_hours
            ),
            max_missing_data_ratio=_as_float(
                data.get("max_missing_data_ratio"),
                cls.max_missing_data_ratio,
            ),
            stale_price_days=_as_int(
                data.get("stale_price_days"), cls.stale_price_days
            ),
            abnormal_daily_move_pct=_as_float(
                data.get("abnormal_daily_move_pct"),
                cls.abnormal_daily_move_pct,
            ),
            confidence_penalty={
                str(key): int(value) for key, value in penalties.items()
            },
        )


@dataclass(frozen=True)
class BasketsConfig:
    ai: dict[str, float] = field(default_factory=dict)
    hbm: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "BasketsConfig":
        return cls(
            ai=_weights_from_mapping(data.get("ai", {}), "baskets.ai"),
            hbm=_weights_from_mapping(data.get("hbm", {}), "baskets.hbm"),
        )


@dataclass(frozen=True)
class IndicatorsConfig:
    rsi_period: int = 14
    adx_period: int = 14
    atr_period: int = 14
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    moving_averages: list[int] = field(
        default_factory=lambda: [20, 50, 100, 200]
    )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "IndicatorsConfig":
        return cls(
            rsi_period=_as_int(data.get("rsi_period"), cls.rsi_period),
            adx_period=_as_int(data.get("adx_period"), cls.adx_period),
            atr_period=_as_int(data.get("atr_period"), cls.atr_period),
            bollinger_period=_as_int(
                data.get("bollinger_period"), cls.bollinger_period
            ),
            bollinger_std=_as_float(
                data.get("bollinger_std"), cls.bollinger_std
            ),
            moving_averages=[
                int(value)
                for value in data.get("moving_averages", [20, 50, 100, 200])
            ],
        )


@dataclass(frozen=True)
class DecisionConfig:
    max_single_adjustment_shares: int = 100
    min_confidence_to_add: int = 65
    min_confidence_to_reduce: int = 55
    high_risk_score: int = 75
    uncertain_confidence_below: int = 45
    base_confidence: int = 50
    confidence_by_mode: dict[str, int] = field(
        default_factory=lambda: {
            "Uptrend": 72,
            "Range": 62,
            "Downtrend": 68,
            "Mixed": 38,
            "Capitulation": 75,
            "Recovery": 66,
        }
    )
    uptrend_min_rsi: float = 50.0
    uptrend_min_adx: float = 18.0
    downtrend_max_rsi: float = 45.0
    downtrend_min_risk_score: float = 55.0
    range_min_rsi: float = 35.0
    range_max_rsi: float = 65.0
    range_buy_rsi: float = 35.0
    range_sell_rsi: float = 65.0
    range_max_adx: float = 25.0
    capitulation_min_risk_score: float = 80.0
    capitulation_ai_5d_max: float = -8.0
    capitulation_hbm_5d_max: float = -12.0
    recovery_ai_5d_min: float = 1.0
    recovery_hbm_5d_min: float = 3.0
    recovery_relative_ratio_min: float = 1.0
    high_risk_level_score: float = 70.0
    medium_risk_level_score: float = 35.0
    max_confidence: int = 95
    min_confidence: int = 5

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "DecisionConfig":
        defaults = cls()
        confidence_by_mode = data.get(
            "confidence_by_mode",
            defaults.confidence_by_mode,
        )
        if not isinstance(confidence_by_mode, dict):
            raise ValueError("decision.confidence_by_mode must be a mapping")

        return cls(
            max_single_adjustment_shares=_as_int(
                data.get("max_single_adjustment_shares"),
                cls.max_single_adjustment_shares,
            ),
            min_confidence_to_add=_as_int(
                data.get("min_confidence_to_add"),
                cls.min_confidence_to_add,
            ),
            min_confidence_to_reduce=_as_int(
                data.get("min_confidence_to_reduce"),
                cls.min_confidence_to_reduce,
            ),
            high_risk_score=_as_int(
                data.get("high_risk_score"), cls.high_risk_score
            ),
            uncertain_confidence_below=_as_int(
                data.get("uncertain_confidence_below"),
                cls.uncertain_confidence_below,
            ),
            base_confidence=_as_int(
                data.get("base_confidence"),
                cls.base_confidence,
            ),
            confidence_by_mode={
                str(mode): int(confidence)
                for mode, confidence in confidence_by_mode.items()
            },
            uptrend_min_rsi=_as_float(
                data.get("uptrend_min_rsi"),
                cls.uptrend_min_rsi,
            ),
            uptrend_min_adx=_as_float(
                data.get("uptrend_min_adx"),
                cls.uptrend_min_adx,
            ),
            downtrend_max_rsi=_as_float(
                data.get("downtrend_max_rsi"),
                cls.downtrend_max_rsi,
            ),
            downtrend_min_risk_score=_as_float(
                data.get("downtrend_min_risk_score"),
                cls.downtrend_min_risk_score,
            ),
            range_min_rsi=_as_float(
                data.get("range_min_rsi"),
                cls.range_min_rsi,
            ),
            range_max_rsi=_as_float(
                data.get("range_max_rsi"),
                cls.range_max_rsi,
            ),
            range_buy_rsi=_as_float(
                data.get("range_buy_rsi"),
                cls.range_buy_rsi,
            ),
            range_sell_rsi=_as_float(
                data.get("range_sell_rsi"),
                cls.range_sell_rsi,
            ),
            range_max_adx=_as_float(
                data.get("range_max_adx"),
                cls.range_max_adx,
            ),
            capitulation_min_risk_score=_as_float(
                data.get("capitulation_min_risk_score"),
                cls.capitulation_min_risk_score,
            ),
            capitulation_ai_5d_max=_as_float(
                data.get("capitulation_ai_5d_max"),
                cls.capitulation_ai_5d_max,
            ),
            capitulation_hbm_5d_max=_as_float(
                data.get("capitulation_hbm_5d_max"),
                cls.capitulation_hbm_5d_max,
            ),
            recovery_ai_5d_min=_as_float(
                data.get("recovery_ai_5d_min"),
                cls.recovery_ai_5d_min,
            ),
            recovery_hbm_5d_min=_as_float(
                data.get("recovery_hbm_5d_min"),
                cls.recovery_hbm_5d_min,
            ),
            recovery_relative_ratio_min=_as_float(
                data.get("recovery_relative_ratio_min"),
                cls.recovery_relative_ratio_min,
            ),
            high_risk_level_score=_as_float(
                data.get("high_risk_level_score"),
                cls.high_risk_level_score,
            ),
            medium_risk_level_score=_as_float(
                data.get("medium_risk_level_score"),
                cls.medium_risk_level_score,
            ),
            max_confidence=_as_int(
                data.get("max_confidence"),
                cls.max_confidence,
            ),
            min_confidence=_as_int(
                data.get("min_confidence"),
                cls.min_confidence,
            ),
        )


@dataclass(frozen=True)
class ReviewConfig:
    forward_return_days: list[int] = field(default_factory=lambda: [1, 5, 20])
    reduce_success_threshold_pct: float = -2.0
    reduce_missed_opportunity_threshold_pct: float = 3.0
    hold_failure_threshold_pct: float = -5.0
    add_success_threshold_pct: float = 3.0

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ReviewConfig":
        return cls(
            forward_return_days=[
                int(value) for value in data.get("forward_return_days", [1, 5, 20])
            ],
            reduce_success_threshold_pct=_as_float(
                data.get("reduce_success_threshold_pct"),
                cls.reduce_success_threshold_pct,
            ),
            reduce_missed_opportunity_threshold_pct=_as_float(
                data.get("reduce_missed_opportunity_threshold_pct"),
                cls.reduce_missed_opportunity_threshold_pct,
            ),
            hold_failure_threshold_pct=_as_float(
                data.get("hold_failure_threshold_pct"),
                cls.hold_failure_threshold_pct,
            ),
            add_success_threshold_pct=_as_float(
                data.get("add_success_threshold_pct"),
                cls.add_success_threshold_pct,
            ),
        )


@dataclass(frozen=True)
class CoachConfig:
    interactive_input: bool = True
    ask_reason_when_not_followed: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "CoachConfig":
        return cls(
            interactive_input=_as_bool(
                data.get("interactive_input"), cls.interactive_input
            ),
            ask_reason_when_not_followed=_as_bool(
                data.get("ask_reason_when_not_followed"),
                cls.ask_reason_when_not_followed,
            ),
        )


@dataclass(frozen=True)
class ReportsConfig:
    generate_excel: bool = True
    generate_html: bool = True
    generate_monthly: str = "auto"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ReportsConfig":
        return cls(
            generate_excel=_as_bool(
                data.get("generate_excel"), cls.generate_excel
            ),
            generate_html=_as_bool(data.get("generate_html"), cls.generate_html),
            generate_monthly=str(
                data.get("generate_monthly", cls.generate_monthly)
            ),
        )


@dataclass
class AiosConfig:
    app: AppConfig
    data: DataConfig
    data_quality: DataQualityConfig
    baskets: BasketsConfig
    indicators: IndicatorsConfig
    classification: dict[str, Any]
    decision: DecisionConfig
    review: ReviewConfig
    coach: CoachConfig
    reports: ReportsConfig


@dataclass(frozen=True)
class PositionConfig:
    shares: float = 0
    average_cost: float = 0

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "PositionConfig":
        return cls(
            shares=_as_float(data.get("shares"), cls.shares),
            average_cost=_as_float(data.get("average_cost"), cls.average_cost),
        )


@dataclass(frozen=True)
class PortfolioConfig:
    base_currency: str = "HKD"
    positions: dict[str, PositionConfig] = field(default_factory=dict)
    cash: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "PortfolioConfig":
        positions = data.get("positions", {})
        cash = data.get("cash", {})

        if not isinstance(positions, dict):
            raise ValueError("portfolio.positions must be a mapping")
        if not isinstance(cash, dict):
            raise ValueError("portfolio.cash must be a mapping")

        return cls(
            base_currency=str(data.get("base_currency", cls.base_currency)),
            positions={
                str(ticker): PositionConfig.from_mapping(value or {})
                for ticker, value in positions.items()
            },
            cash={
                str(currency): float(amount)
                for currency, amount in cash.items()
            },
        )


def _weights_from_mapping(data: Any, field_name: str) -> dict[str, float]:
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} must be a mapping")
    return {str(ticker): float(weight) for ticker, weight in data.items()}

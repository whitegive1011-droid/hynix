"""Explainable rule-based decision engine."""

from __future__ import annotations

from dataclasses import dataclass

from aios.config.models import DecisionConfig
from aios.decision.models import (
    BasketSnapshot,
    DecisionInput,
    DecisionResult,
    MarketMode,
    RiskLevel,
    TechnicalSnapshot,
)


@dataclass(frozen=True)
class DecisionEngine:
    """Generate today's rule-based recommendation."""

    config: DecisionConfig

    def decide(self, decision_input: DecisionInput) -> DecisionResult:
        mode, classification_reasons, triggered_rules = self.classify_market(
            decision_input.basket,
            decision_input.technical,
        )
        risk_level = self._risk_level(decision_input.basket)
        suggested_position, action_reason, action_rule = self._suggest_position(
            mode,
            risk_level,
            decision_input.technical,
            decision_input.position.current_shares,
        )
        position_delta = suggested_position - decision_input.position.current_shares
        recommendation = self._recommendation_text(
            mode=mode,
            position_delta=position_delta,
            suggested_position=suggested_position,
        )
        confidence = self._confidence(mode, risk_level)

        reasons = [
            f"Market classified as {mode.value}.",
            *classification_reasons,
            action_reason,
        ]
        if risk_level == RiskLevel.HIGH:
            reasons.append("Risk level is High based on configured risk thresholds.")
        if confidence < self.config.uncertain_confidence_below:
            reasons.append("Confidence is below the configured uncertainty threshold.")

        return DecisionResult(
            date=decision_input.basket.date,
            market_mode=mode,
            recommendation=recommendation,
            confidence=confidence,
            reasons=[reason for reason in reasons if reason],
            risk_level=risk_level,
            current_position=decision_input.position.current_shares,
            suggested_position=suggested_position,
            position_delta=position_delta,
            triggered_rules=[*triggered_rules, action_rule],
        )

    def classify_market(
        self,
        basket: BasketSnapshot,
        technical: TechnicalSnapshot,
    ) -> tuple[MarketMode, list[str], list[str]]:
        if self._is_capitulation(basket):
            return (
                MarketMode.CAPITULATION,
                [
                    "Risk score or 5D basket declines met capitulation thresholds.",
                ],
                ["classification.capitulation"],
            )

        if self._is_recovery(basket, technical):
            return (
                MarketMode.RECOVERY,
                [
                    "AI/HBM basket returns and relative ratio met recovery thresholds.",
                    "Technical momentum is improving.",
                ],
                ["classification.recovery"],
            )

        if self._is_downtrend(basket, technical):
            return (
                MarketMode.DOWNTREND,
                [
                    "Risk score or weak technical trend met downtrend thresholds.",
                ],
                ["classification.downtrend"],
            )

        if self._is_uptrend(technical):
            return (
                MarketMode.UPTREND,
                [
                    "Price, moving averages, momentum, and ADX support an uptrend.",
                ],
                ["classification.uptrend"],
            )

        if self._is_range(technical):
            return (
                MarketMode.RANGE,
                [
                    "RSI and ADX are within configured range-market thresholds.",
                ],
                ["classification.range"],
            )

        return (
            MarketMode.MIXED,
            ["Indicators do not align strongly enough for a directional mode."],
            ["classification.mixed"],
        )

    def _is_capitulation(self, basket: BasketSnapshot) -> bool:
        risk_score = _value(basket.risk_score)
        ai_5d = _value(basket.ai_5d)
        hbm_5d = _value(basket.hbm_5d)
        return (
            risk_score >= self.config.capitulation_min_risk_score
            or (
                ai_5d <= self.config.capitulation_ai_5d_max
                and hbm_5d <= self.config.capitulation_hbm_5d_max
            )
        )

    def _is_recovery(
        self,
        basket: BasketSnapshot,
        technical: TechnicalSnapshot,
    ) -> bool:
        return (
            _value(basket.ai_5d) >= self.config.recovery_ai_5d_min
            and _value(basket.hbm_5d) >= self.config.recovery_hbm_5d_min
            and _value(basket.relative_ratio)
            >= self.config.recovery_relative_ratio_min
            and self._has_positive_momentum(technical)
        )

    def _is_downtrend(
        self,
        basket: BasketSnapshot,
        technical: TechnicalSnapshot,
    ) -> bool:
        risk_downtrend = (
            _value(basket.risk_score) >= self.config.downtrend_min_risk_score
        )
        technical_downtrend = (
            _lt(technical.close, technical.sma_20)
            and _lt(technical.close, technical.sma_50)
            and _lt(technical.macd, technical.macd_signal)
            and _value(technical.rsi14) <= self.config.downtrend_max_rsi
        )
        return risk_downtrend or technical_downtrend

    def _is_uptrend(self, technical: TechnicalSnapshot) -> bool:
        return (
            _gt(technical.close, technical.sma_20)
            and _gt(technical.sma_20, technical.sma_50)
            and _gt(technical.macd, technical.macd_signal)
            and _value(technical.rsi14) >= self.config.uptrend_min_rsi
            and _value(technical.adx14) >= self.config.uptrend_min_adx
        )

    def _is_range(self, technical: TechnicalSnapshot) -> bool:
        rsi = _value(technical.rsi14)
        return (
            self.config.range_min_rsi <= rsi <= self.config.range_max_rsi
            and _value(technical.adx14) <= self.config.range_max_adx
            and _inside(
                technical.close,
                technical.bollinger_lower,
                technical.bollinger_upper,
            )
        )

    @staticmethod
    def _has_positive_momentum(technical: TechnicalSnapshot) -> bool:
        return _gt(technical.close, technical.sma_20) and _gt(
            technical.macd,
            technical.macd_signal,
        )

    def _risk_level(self, basket: BasketSnapshot) -> RiskLevel:
        risk_score = _value(basket.risk_score)
        if risk_score >= self.config.high_risk_level_score:
            return RiskLevel.HIGH
        if risk_score >= self.config.medium_risk_level_score:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _suggest_position(
        self,
        mode: MarketMode,
        risk_level: RiskLevel,
        technical: TechnicalSnapshot,
        current_position: int,
    ) -> tuple[int, str, str]:
        step = self.config.max_single_adjustment_shares

        if mode in {MarketMode.CAPITULATION, MarketMode.DOWNTREND}:
            if current_position <= 0:
                return (
                    current_position,
                    "No shares are currently held, so no reduction is possible.",
                    "position.no_holdings",
                )
            suggested = max(0, current_position - step)
            return (
                suggested,
                "Risk controls recommend a gradual reduction.",
                "position.reduce_risk",
            )

        if mode == MarketMode.RECOVERY:
            return (
                current_position + step,
                "Recovery rules allow adding back gradually.",
                "position.add_recovery",
            )

        if mode == MarketMode.RANGE:
            if self._range_sell_signal(technical) and current_position > 0:
                return (
                    max(0, current_position - step),
                    "Range rules detected upper-band/overbought conditions.",
                    "position.range_reduce",
                )
            if self._range_buy_signal(technical):
                return (
                    current_position + step,
                    "Range rules detected lower-band/oversold conditions.",
                    "position.range_add",
                )
            return (
                current_position,
                "Range rules do not require a position adjustment.",
                "position.hold_range",
            )

        if mode == MarketMode.MIXED or risk_level == RiskLevel.HIGH:
            return (
                current_position,
                "Conflicting signals favor watching instead of adjusting.",
                "position.watch_uncertain",
            )

        return (
            current_position,
            "Trend rules favor holding the current position.",
            "position.hold_trend",
        )

    def _range_sell_signal(self, technical: TechnicalSnapshot) -> bool:
        return (
            _value(technical.rsi14) >= self.config.range_sell_rsi
            and _gte(technical.close, technical.bollinger_upper)
        )

    def _range_buy_signal(self, technical: TechnicalSnapshot) -> bool:
        return (
            _value(technical.rsi14) <= self.config.range_buy_rsi
            and _lte(technical.close, technical.bollinger_lower)
        )

    def _recommendation_text(
        self,
        mode: MarketMode,
        position_delta: int,
        suggested_position: int,
    ) -> str:
        if position_delta < 0:
            return f"Reduce {abs(position_delta)} Shares"
        if position_delta > 0:
            return f"Add Back {position_delta} Shares"
        if mode == MarketMode.CAPITULATION:
            return "High Risk"
        if mode == MarketMode.MIXED:
            return "Uncertain"
        if mode == MarketMode.RANGE:
            return "Watch"
        return "Hold"

    def _confidence(self, mode: MarketMode, risk_level: RiskLevel) -> int:
        confidence = self.config.confidence_by_mode.get(
            mode.value,
            self.config.base_confidence,
        )
        if risk_level == RiskLevel.HIGH and mode not in {
            MarketMode.CAPITULATION,
            MarketMode.DOWNTREND,
        }:
            confidence -= 10
        return max(
            self.config.min_confidence,
            min(self.config.max_confidence, int(confidence)),
        )


def _value(value: float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _lt(left: float | None, right: float | None) -> bool:
    return left is not None and right is not None and left < right


def _lte(left: float | None, right: float | None) -> bool:
    return left is not None and right is not None and left <= right


def _gt(left: float | None, right: float | None) -> bool:
    return left is not None and right is not None and left > right


def _gte(left: float | None, right: float | None) -> bool:
    return left is not None and right is not None and left >= right


def _inside(
    value: float | None,
    lower: float | None,
    upper: float | None,
) -> bool:
    return value is not None and lower is not None and upper is not None and lower <= value <= upper

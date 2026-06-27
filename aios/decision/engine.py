"""Explainable rule-based decision engine."""

from __future__ import annotations

from dataclasses import dataclass

from aios.config.models import DecisionConfig, ProxyConfig
from aios.decision.models import (
    BasketSnapshot,
    DecisionDataQuality,
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
    proxy_config: ProxyConfig | None = None

    def decide(self, decision_input: DecisionInput) -> DecisionResult:
        if self._requires_uncertain_decision(decision_input.data_quality):
            if self._can_use_proxy_when_official_incomplete(decision_input):
                return self._proxy_based_decision(decision_input)
            return self._uncertain_for_data_quality(decision_input)

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
        confidence = self._cap_confidence_for_data_quality(
            self._confidence(mode, risk_level),
            decision_input.data_quality,
        )
        proxy_reasons, proxy_rules, proxy_influenced = self._official_proxy_context(
            decision_input,
        )
        confidence = self._cap_confidence_for_proxy_conflict(
            confidence,
            decision_input,
        )

        reasons = [
            f"Market classified as {mode.value}.",
            *classification_reasons,
            action_reason,
            *proxy_reasons,
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
            triggered_rules=[*triggered_rules, action_rule, *proxy_rules],
            proxy_influenced=proxy_influenced,
        )

    def _requires_uncertain_decision(self, data_quality: DecisionDataQuality) -> bool:
        return (
            data_quality.required_basket_tickers_missing
            or data_quality.data_quality_score < 50
        )

    def _uncertain_for_data_quality(
        self,
        decision_input: DecisionInput,
    ) -> DecisionResult:
        confidence = self._cap_confidence_for_data_quality(
            self.config.confidence_by_mode.get(
                MarketMode.MIXED.value,
                self.config.base_confidence,
            ),
            decision_input.data_quality,
        )
        reasons = [
            "Market classified as Mixed.",
            "Data quality is insufficient for a reliable basket decision.",
        ]
        if decision_input.data_quality.missing_tickers:
            reasons.append(
                "Missing required market data: "
                + ", ".join(decision_input.data_quality.missing_tickers)
            )
        if decision_input.data_quality.stale_tickers:
            reasons.append(
                "Stale market data detected: "
                + ", ".join(decision_input.data_quality.stale_tickers)
            )
        return DecisionResult(
            date=decision_input.basket.date,
            market_mode=MarketMode.MIXED,
            recommendation="Uncertain",
            confidence=confidence,
            reasons=reasons,
            risk_level=self._risk_level(decision_input.basket),
            current_position=decision_input.position.current_shares,
            suggested_position=decision_input.position.current_shares,
            position_delta=0,
            triggered_rules=[
                "data_quality.insufficient",
                "position.watch_uncertain",
            ],
        )

    def _can_use_proxy_when_official_incomplete(
        self,
        decision_input: DecisionInput,
    ) -> bool:
        proxy_config = self._proxy_config()
        return (
            proxy_config.allow_proxy_for_intraday_signal
            and decision_input.proxy_signal.available
            and decision_input.proxy_signal.proxy_data_quality != "Missing"
        )

    def _proxy_based_decision(
        self,
        decision_input: DecisionInput,
    ) -> DecisionResult:
        proxy_config = self._proxy_config()
        current_position = decision_input.position.current_shares
        step = self.config.max_single_adjustment_shares
        proxy_level = decision_input.proxy_signal.proxy_risk_level

        suggested_position = current_position
        recommendation = "Proxy-Based Watch"
        risk_level = RiskLevel.LOW
        action_rule = "position.proxy_watch"
        if proxy_level == "Strong Risk-Off":
            risk_level = RiskLevel.HIGH
            action_rule = "position.proxy_reduce_risk"
            if current_position > 0:
                suggested_position = max(0, current_position - step)
                recommendation = f"Reduce {current_position - suggested_position} Shares"
            else:
                recommendation = "Proxy-Based Watch"
        elif proxy_level == "Risk-Off":
            risk_level = RiskLevel.MEDIUM
            recommendation = "Cautious Hold"
            action_rule = "position.proxy_cautious_hold"
        elif proxy_level == "Risk-On":
            recommendation = "Cautious Hold"
            action_rule = "position.proxy_cautious_hold"

        confidence = min(
            proxy_config.max_confidence_when_proxy_only,
            self.config.confidence_by_mode.get(
                MarketMode.MIXED.value,
                self.config.base_confidence,
            )
            + 20,
        )
        reasons = [
            "Market classified as Mixed.",
            "Official equity data is incomplete.",
            "Tradable proxy data is used for intraday risk assessment only.",
            "Proxy data is not official equity market data.",
            f"Proxy intraday risk level is {proxy_level}.",
        ]
        if decision_input.proxy_signal.proxy_ai_1d_change is not None:
            reasons.append(
                "Proxy AI 1D change: "
                f"{decision_input.proxy_signal.proxy_ai_1d_change:.2f}%."
            )
        if decision_input.proxy_signal.proxy_hbm_1d_change is not None:
            reasons.append(
                "Proxy HBM 1D change: "
                f"{decision_input.proxy_signal.proxy_hbm_1d_change:.2f}%."
            )

        return DecisionResult(
            date=decision_input.basket.date,
            market_mode=MarketMode.MIXED,
            recommendation=recommendation,
            confidence=int(confidence),
            reasons=reasons,
            risk_level=risk_level,
            current_position=current_position,
            suggested_position=suggested_position,
            position_delta=suggested_position - current_position,
            triggered_rules=[
                "proxy.official_data_incomplete",
                "proxy.intraday_signal",
                action_rule,
            ],
            proxy_influenced=True,
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

    def _cap_confidence_for_data_quality(
        self,
        confidence: int,
        data_quality: DecisionDataQuality,
    ) -> int:
        if data_quality.data_quality_score < 50:
            confidence = min(confidence, self.config.uncertain_confidence_below - 1)
        elif data_quality.data_quality_score < 75 or data_quality.missing_tickers:
            confidence = min(confidence, 55)
        elif data_quality.stale_tickers:
            confidence = min(confidence, 65)
        return max(
            self.config.min_confidence,
            min(self.config.max_confidence, int(confidence)),
        )

    def _official_proxy_context(
        self,
        decision_input: DecisionInput,
    ) -> tuple[list[str], list[str], bool]:
        proxy = decision_input.proxy_signal
        if not proxy.available:
            return [], [], False

        reasons = [
            f"Proxy intraday risk level is {proxy.proxy_risk_level}.",
            "Tradable proxy data is supporting context only.",
            "Proxy data is not official equity market data.",
        ]
        rules = ["proxy.supporting_context"]
        proxy_influenced = False
        if proxy.proxy_official_conflict_flag:
            reasons.append(
                "Proxy signal conflicts with official market data; confidence is capped."
            )
            rules.append("proxy.official_conflict")
            proxy_influenced = True
        return reasons, rules, proxy_influenced

    def _cap_confidence_for_proxy_conflict(
        self,
        confidence: int,
        decision_input: DecisionInput,
    ) -> int:
        if not decision_input.proxy_signal.proxy_official_conflict_flag:
            return confidence
        conflict_cap = min(
            80,
            self._proxy_config().max_confidence_when_proxy_conflict,
        )
        return max(
            self.config.min_confidence,
            min(confidence, conflict_cap),
        )

    def _proxy_config(self) -> ProxyConfig:
        return self.proxy_config or ProxyConfig()


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

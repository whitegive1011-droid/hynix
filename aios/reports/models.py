"""Read-only presentation models."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any

from aios.decision.models import (
    BasketSnapshot,
    DecisionResult,
    PortfolioPosition,
    TechnicalSnapshot,
)
from aios.app.models import RunMetadata


@dataclass(frozen=True)
class KeyIndicator:
    label: str
    value: float | int | str | None
    display_value: str


@dataclass(frozen=True)
class PresentationContext:
    """All data needed by the presentation layer.

    This object should be built from upstream market, decision, and portfolio
    state. It must not calculate indicators or run trading rules.
    """

    decision: DecisionResult
    basket: BasketSnapshot
    technical: TechnicalSnapshot
    portfolio: PortfolioPosition
    metadata: RunMetadata
    key_indicators: list[KeyIndicator] = field(default_factory=list)

    @property
    def date(self) -> str:
        return self.decision.date

    @property
    def top_reasons(self) -> list[str]:
        return self.decision.reasons[:5]

    @property
    def data_warnings(self) -> list[str]:
        return _build_data_warnings(self)


@dataclass(frozen=True)
class PresentationOutputPaths:
    latest_signal: Path
    excel_dashboard: Path
    html_dashboard: Path


def build_presentation_context(
    decision: DecisionResult,
    basket: BasketSnapshot,
    technical: TechnicalSnapshot,
    portfolio: PortfolioPosition,
    metadata: RunMetadata | None = None,
) -> PresentationContext:
    """Assemble already-computed values for rendering."""

    metadata = metadata or RunMetadata(
        data_source="unknown",
        provider_used="unknown",
        last_update="N/A",
        data_quality="Unknown",
        missing_tickers=[],
    )
    key_indicators = [
        _indicator("Relative Ratio", basket.relative_ratio, precision=3),
        _indicator("Risk Score", basket.risk_score, precision=1),
        _indicator("AI 5D Return", basket.ai_5d, suffix="%", precision=1),
        _indicator("HBM 5D Return", basket.hbm_5d, suffix="%", precision=1),
        _indicator("D5", basket.d5, suffix="%", precision=1),
        _indicator("D20", basket.d20, suffix="%", precision=1),
        _indicator("RSI14", technical.rsi14, precision=1),
        _indicator("ADX14", technical.adx14, precision=1),
        _indicator("MACD", technical.macd, precision=2),
    ]
    return PresentationContext(
        decision=decision,
        basket=basket,
        technical=technical,
        portfolio=portfolio,
        metadata=metadata,
        key_indicators=key_indicators,
    )


def context_to_dict(context: PresentationContext) -> dict[str, Any]:
    """Convert presentation context to JSON/template-safe data."""

    decision = context.decision
    return {
        "date": context.date,
        "recommendation": decision.recommendation,
        "confidence": decision.confidence,
        "risk_level": decision.risk_level.value,
        "market_mode": decision.market_mode.value,
        "suggested_position": decision.suggested_position,
        "current_position": decision.current_position,
        "position_delta": decision.position_delta,
        "top_reasons": context.top_reasons,
        "triggered_rules": decision.triggered_rules,
        "relative_ratio": context.basket.relative_ratio,
        "risk_score": context.basket.risk_score,
        "relative_ratio_display": _indicator_display(context, "Relative Ratio"),
        "risk_score_display": _indicator_display(context, "Risk Score"),
        "data_source": context.metadata.data_source,
        "provider_used": context.metadata.provider_used,
        "last_update": context.metadata.last_update,
        "data_quality": context.metadata.data_quality,
        "fallback_used": context.metadata.fallback_used,
        "missing_tickers": context.metadata.missing_tickers,
        "stale_tickers": context.metadata.stale_tickers or [],
        "provider_by_ticker": context.metadata.provider_by_ticker or {},
        "cache_coverage_percentage": context.metadata.cache_coverage_percentage,
        "data_quality_score": context.metadata.data_quality_score,
        "recommendation_degraded": context.metadata.recommendation_degraded,
        "manual_mobile_input_used": context.metadata.manual_mobile_input_used,
        "latest_manual_input_date": context.metadata.latest_manual_input_date,
        "manual_tickers_used": context.metadata.manual_tickers_used,
        "manual_source": context.metadata.manual_source,
        "data_warnings": context.data_warnings,
        "key_indicators": [
            {
                "label": indicator.label,
                "value": indicator.value,
                "display_value": indicator.display_value,
            }
            for indicator in context.key_indicators
        ],
        "portfolio": {
            "ticker": context.portfolio.ticker,
            "current_shares": context.portfolio.current_shares,
        },
    }


def _indicator(
    label: str,
    value: float | int | str | None,
    suffix: str = "",
    precision: int = 1,
) -> KeyIndicator:
    if value is None:
        return KeyIndicator(label=label, value=None, display_value="N/A")
    if isinstance(value, str):
        return KeyIndicator(label=label, value=value, display_value=value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return KeyIndicator(label=label, value=None, display_value="N/A")
    return KeyIndicator(
        label=label,
        value=value,
        display_value=f"{value:.{precision}f}{suffix}",
    )


def _indicator_display(context: PresentationContext, label: str) -> str:
    for indicator in context.key_indicators:
        if indicator.label == label:
            return indicator.display_value
    return "N/A"


def _build_data_warnings(context: PresentationContext) -> list[str]:
    warnings: list[str] = []
    if context.metadata.fallback_used:
        warnings.append(
            "Fallback market data provider was used; review recommendation confidence."
        )
    if context.metadata.missing_tickers:
        warnings.append(
            "Missing market data for required tickers: "
            + ", ".join(context.metadata.missing_tickers)
        )
    if context.metadata.stale_tickers:
        warnings.append(
            "Stale market data detected for tickers: "
            + ", ".join(context.metadata.stale_tickers)
        )
    if context.metadata.recommendation_degraded:
        warnings.append(
            "Recommendation is degraded because data quality is below the target."
        )
    if context.metadata.manual_mobile_input_used:
        warnings.append(
            "Manual mobile input was used from "
            f"{context.metadata.manual_source} on "
            f"{context.metadata.latest_manual_input_date}."
        )

    unavailable_indicators = [
        indicator.label
        for indicator in context.key_indicators
        if indicator.value is None
    ]
    if unavailable_indicators:
        warnings.append(
            "Unavailable indicators due to insufficient source data: "
            + ", ".join(unavailable_indicators)
        )
    return warnings

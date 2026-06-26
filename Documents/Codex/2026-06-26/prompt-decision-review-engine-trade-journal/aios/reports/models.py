"""Read-only presentation models."""

from __future__ import annotations

from dataclasses import dataclass, field
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
        "data_source": context.metadata.data_source,
        "provider_used": context.metadata.provider_used,
        "last_update": context.metadata.last_update,
        "data_quality": context.metadata.data_quality,
        "fallback_used": context.metadata.fallback_used,
        "missing_tickers": context.metadata.missing_tickers,
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
    return KeyIndicator(
        label=label,
        value=value,
        display_value=f"{value:.{precision}f}{suffix}",
    )

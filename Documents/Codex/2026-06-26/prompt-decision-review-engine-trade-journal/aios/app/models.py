"""Application-level state models."""

from __future__ import annotations

from dataclasses import dataclass, field

from aios.decision.models import BasketSnapshot, PortfolioPosition, TechnicalSnapshot


@dataclass(frozen=True)
class MarketState:
    """Typed market state passed from market modules into decision logic."""

    basket: BasketSnapshot
    technical: TechnicalSnapshot


@dataclass(frozen=True)
class PortfolioState:
    """Typed portfolio state used by the application orchestrator."""

    primary_ticker: str
    current_shares: int

    def to_position(self) -> PortfolioPosition:
        return PortfolioPosition(
            ticker=self.primary_ticker,
            current_shares=self.current_shares,
        )


@dataclass(frozen=True)
class RunMetadata:
    """Operational metadata for dashboard and deployment reporting."""

    data_source: str
    provider_used: str
    last_update: str
    data_quality: str
    missing_tickers: list[str]
    fallback_used: bool = False
    execution_time_seconds: float = 0.0
    provider_by_ticker: dict[str, str] | None = None
    stale_tickers: list[str] | None = None
    cache_coverage_percentage: float = 0.0
    data_quality_score: int = 0
    recommendation_degraded: bool = False
    manual_mobile_input_used: bool = False
    latest_manual_input_date: str = "N/A"
    manual_tickers_used: list[str] = field(default_factory=list)
    manual_source: str = "None"

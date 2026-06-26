"""Application-level state models."""

from __future__ import annotations

from dataclasses import dataclass

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

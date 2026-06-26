from __future__ import annotations

import json
from pathlib import Path

from aios.decision.models import (
    BasketSnapshot,
    DecisionResult,
    MarketMode,
    PortfolioPosition,
    RiskLevel,
    TechnicalSnapshot,
)
from aios.reports.json_exporter import write_latest_signal
from aios.reports.models import build_presentation_context


def test_readme_contains_release_setup_and_usage_instructions() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    required_phrases = [
        "Local Setup",
        ".venv/bin/python -m pytest",
        ".venv/bin/python main.py --no-input",
        "GitHub Actions Deployment",
        "Settings -> Pages",
        "GitHub Actions",
        "No repository secrets are required",
        "data/cache/market_cache.csv",
    ]
    for phrase in required_phrases:
        assert phrase in readme


def test_latest_signal_export_is_strict_json_when_values_are_nan(tmp_path: Path) -> None:
    context = build_presentation_context(
        decision=DecisionResult(
            date="2026-06-26",
            market_mode=MarketMode.MIXED,
            recommendation="Uncertain",
            confidence=38,
            reasons=["Noisy data."],
            risk_level=RiskLevel.LOW,
            current_position=0,
            suggested_position=0,
            position_delta=0,
        ),
        basket=BasketSnapshot(
            date="2026-06-26",
            relative_ratio=float("nan"),
            risk_score=float("nan"),
        ),
        technical=TechnicalSnapshot(
            date="2026-06-26",
            ticker="7709.HK",
            rsi14=float("nan"),
        ),
        portfolio=PortfolioPosition(ticker="7709.HK", current_shares=0),
    )

    output = write_latest_signal(context, tmp_path / "latest_signal.json")
    raw = output.read_text(encoding="utf-8")

    assert "NaN" not in raw
    assert "Infinity" not in raw
    parsed = json.loads(raw)
    assert parsed["relative_ratio"] is None
    assert parsed["risk_score"] is None

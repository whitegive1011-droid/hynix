"""YAML configuration loading for AIOS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised before tests run
    raise RuntimeError(
        "PyYAML is required. Install dependencies with "
        "`python3 -m pip install -r requirements.txt`."
    ) from exc

from aios.config.models import (
    AiosConfig,
    AppConfig,
    BasketsConfig,
    CoachConfig,
    DataConfig,
    DataQualityConfig,
    DecisionConfig,
    IndicatorsConfig,
    PortfolioConfig,
    ProxyConfig,
    ReportsConfig,
    ReviewConfig,
)


def load_config(path: str | Path = "config.yaml") -> AiosConfig:
    data = _load_yaml_mapping(path)
    return AiosConfig(
        app=AppConfig.from_mapping(data.get("app", {})),
        data=DataConfig.from_mapping(data.get("data", {})),
        data_quality=DataQualityConfig.from_mapping(
            data.get("data_quality", {})
        ),
        baskets=BasketsConfig.from_mapping(data.get("baskets", {})),
        indicators=IndicatorsConfig.from_mapping(data.get("indicators", {})),
        classification=dict(data.get("classification", {})),
        decision=DecisionConfig.from_mapping(data.get("decision", {})),
        review=ReviewConfig.from_mapping(data.get("review", {})),
        coach=CoachConfig.from_mapping(data.get("coach", {})),
        reports=ReportsConfig.from_mapping(data.get("reports", {})),
        proxy=ProxyConfig.from_mapping(data.get("proxy", {})),
    )


def load_portfolio(path: str | Path = "portfolio.yaml") -> PortfolioConfig:
    data = _load_yaml_mapping(path)
    return PortfolioConfig.from_mapping(data)


def _load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}

    if not isinstance(loaded, dict):
        raise ValueError(f"YAML root must be a mapping: {yaml_path}")

    return loaded

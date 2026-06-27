from pathlib import Path

import pytest

from aios.config.loader import load_config, load_portfolio


def test_load_default_config_file() -> None:
    config = load_config(Path("config.yaml"))

    assert config.app.timezone == "Asia/Shanghai"
    assert config.app.output_dir == Path("outputs")
    assert config.data.primary_provider == "multi"
    assert config.data.fallback_provider == "csv"
    assert config.data.csv_path == Path("data/cache/market_cache.csv")
    assert config.data.retry_attempts == 2
    assert "7709.HK" in config.data.required_tickers
    assert config.data_quality.confidence_penalty["failed"] == 50
    assert config.baskets.hbm["000660.KS"] == 0.5
    assert config.review.forward_return_days == [1, 5, 20]
    assert config.proxy.enabled is True
    assert config.proxy.provider_priority == ["okx", "binance"]
    assert config.proxy.symbols["NVDA"] == ""
    assert config.proxy.allow_proxy_for_intraday_signal is True
    assert config.proxy.allow_proxy_for_core_metrics is False
    assert config.proxy.max_confidence_when_proxy_only == 65
    assert config.proxy.max_confidence_when_proxy_conflict == 55
    assert config.proxy.write_proxy_to_official_cache is False


def test_load_default_portfolio_file() -> None:
    portfolio = load_portfolio(Path("portfolio.yaml"))

    assert portfolio.base_currency == "HKD"
    assert "7709.HK" in portfolio.positions
    assert portfolio.positions["7709.HK"].shares >= 0
    assert portfolio.cash["HKD"] >= 0


def test_load_portfolio_values_from_yaml(tmp_path: Path) -> None:
    portfolio_path = tmp_path / "portfolio.yaml"
    portfolio_path.write_text(
        """
base_currency: HKD
positions:
  7709.HK:
    shares: 400
    average_cost: 149.55
cash:
  HKD: 20645
""".lstrip(),
        encoding="utf-8",
    )

    portfolio = load_portfolio(portfolio_path)

    assert portfolio.positions["7709.HK"].shares == 400
    assert portfolio.positions["7709.HK"].average_cost == 149.55
    assert portfolio.cash["HKD"] == 20645


def test_missing_yaml_file_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="YAML file not found"):
        load_config(tmp_path / "missing.yaml")

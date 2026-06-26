from pathlib import Path

import pytest

from aios.config.loader import load_config, load_portfolio


def test_load_default_config_file() -> None:
    config = load_config(Path("config.yaml"))

    assert config.app.timezone == "Asia/Shanghai"
    assert config.app.output_dir == Path("outputs")
    assert config.data.primary_provider == "yfinance"
    assert config.data.csv_path is None
    assert "7709.HK" in config.data.required_tickers
    assert config.data_quality.confidence_penalty["failed"] == 50
    assert config.baskets.hbm["000660.KS"] == 0.5
    assert config.review.forward_return_days == [1, 5, 20]


def test_load_default_portfolio_file() -> None:
    portfolio = load_portfolio(Path("portfolio.yaml"))

    assert portfolio.base_currency == "HKD"
    assert portfolio.positions["7709.HK"].shares == 300
    assert portfolio.cash["HKD"] == 0


def test_missing_yaml_file_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="YAML file not found"):
        load_config(tmp_path / "missing.yaml")

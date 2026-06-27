from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from aios.data.models import MarketDataRequest, PRICE_COLUMNS
from aios.data.providers import CsvMarketDataProvider
from main import main


def test_main_runs_end_to_end_with_csv_provider(tmp_path: Path) -> None:
    csv_path = _write_orchestrator_fixture(tmp_path)
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    output_dir = tmp_path / "reports"

    config_path.write_text(
        f"""
app:
  output_dir: {output_dir}
  log_level: INFO
data:
  primary_provider: csv
  csv_path: {csv_path}
  lookback_days: 60
  required_tickers:
    - HBM1
    - HBM2
    - AI1
    - AI2
baskets:
  ai:
    AI1: 0.5
    AI2: 0.5
  hbm:
    HBM1: 0.5
    HBM2: 0.5
coach:
  interactive_input: false
""",
        encoding="utf-8",
    )
    portfolio_path.write_text(
        """
base_currency: HKD
positions:
  HBM1:
    shares: 200
    average_cost: 10
cash:
  HKD: 0
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--portfolio",
            str(portfolio_path),
            "--provider",
            "csv",
            "--output-dir",
            str(output_dir),
            "--no-input",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "latest_signal.json").exists()
    assert (output_dir / "investment_dashboard.xlsx").exists()
    assert (output_dir / "dashboard.html").exists()
    assert (output_dir / "history.csv").exists()
    assert (output_dir / "execution.log").exists()
    assert (output_dir / "deployment_summary.txt").exists()

    signal = json.loads((output_dir / "latest_signal.json").read_text())
    assert signal["recommendation"] in {
        "Hold",
        "Add Back 100 Shares",
        "Reduce 100 Shares",
        "Watch",
        "Uncertain",
        "High Risk",
    }
    assert signal["current_position"] == 200
    assert signal["portfolio"]["ticker"] == "HBM1"
    assert signal["provider_used"] == "csv"
    assert signal["data_quality"] == "OK"
    assert signal["top_reasons"]

    html = (output_dir / "dashboard.html").read_text(encoding="utf-8")
    assert "AIOS Daily Dashboard" in html
    assert signal["recommendation"] in html

    workbook = load_workbook(output_dir / "investment_dashboard.xlsx")
    assert workbook["Dashboard"]["B4"].value == "csv"
    assert workbook["Dashboard"]["B18"].value == signal["recommendation"]

    history = pd.read_csv(output_dir / "history.csv")
    assert set(history["ticker"]) == {"HBM1", "HBM2", "AI1", "AI2"}
    first_history_rows = len(history)

    assert main(
        [
            "--config",
            str(config_path),
            "--portfolio",
            str(portfolio_path),
            "--provider",
            "csv",
            "--output-dir",
            str(output_dir),
            "--no-input",
        ]
    ) == 0
    history_after_second_run = pd.read_csv(output_dir / "history.csv")
    assert len(history_after_second_run) == first_history_rows

    summary = (output_dir / "deployment_summary.txt").read_text(encoding="utf-8")
    assert "Execution Time:" in summary
    assert "Provider Used: csv" in summary
    assert "Test Result:" in summary
    assert "Deployment Status:" in summary


def test_main_uses_safe_default_portfolio_when_missing(tmp_path: Path) -> None:
    csv_path = _write_orchestrator_fixture(tmp_path)
    config_path = tmp_path / "config.yaml"
    output_dir = tmp_path / "reports"

    config_path.write_text(
        f"""
app:
  output_dir: {output_dir}
  log_level: INFO
data:
  primary_provider: csv
  csv_path: {csv_path}
  lookback_days: 60
  required_tickers:
    - HBM1
    - AI1
baskets:
  ai:
    AI1: 1.0
  hbm:
    HBM1: 1.0
coach:
  interactive_input: false
""",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--portfolio",
            str(tmp_path / "missing_portfolio.yaml"),
            "--provider",
            "csv",
            "--output-dir",
            str(output_dir),
            "--no-input",
        ]
    )

    signal = json.loads((output_dir / "latest_signal.json").read_text())
    assert exit_code == 0
    assert signal["current_position"] == 0
    assert "Using safe defaults" in (output_dir / "execution.log").read_text(
        encoding="utf-8"
    )


def test_main_masks_basket_metrics_when_required_basket_ticker_is_missing(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "partial_prices.csv"
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    output_dir = tmp_path / "reports"
    start = date(2026, 1, 1)
    pd.DataFrame(
        [_row(start, offset, "AI1", 100 + offset) for offset in range(30)]
    ).to_csv(csv_path, index=False)

    config_path.write_text(
        f"""
app:
  output_dir: {output_dir}
data:
  primary_provider: csv
  csv_path: {csv_path}
  required_tickers:
    - AI1
    - HBM1
baskets:
  ai:
    AI1: 1.0
  hbm:
    HBM1: 1.0
proxy:
  enabled: false
  output_path: {tmp_path / "proxy" / "tradable_proxy_prices.csv"}
coach:
  interactive_input: false
""",
        encoding="utf-8",
    )
    portfolio_path.write_text(
        """
positions:
  HBM1:
    shares: 100
    average_cost: 10
""",
        encoding="utf-8",
    )

    assert main(
        [
            "--config",
            str(config_path),
            "--portfolio",
            str(portfolio_path),
            "--provider",
            "csv",
            "--output-dir",
            str(output_dir),
            "--no-input",
        ]
    ) == 0

    signal = json.loads((output_dir / "latest_signal.json").read_text())
    assert signal["recommendation"] == "Uncertain"
    assert signal["risk_score"] is None
    assert signal["risk_score_display"] == "N/A"
    assert signal["relative_ratio_display"] == "N/A"
    assert signal["missing_tickers"] == ["HBM1"]


def test_main_falls_back_to_csv_cache_when_yahoo_returns_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    csv_path = _write_orchestrator_fixture(tmp_path)
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    output_dir = tmp_path / "reports"

    config_path.write_text(
        f"""
app:
  output_dir: {output_dir}
  log_level: INFO
data:
  primary_provider: yfinance
  fallback_provider: csv
  csv_path: {csv_path}
  retry_attempts: 1
  retry_delay_seconds: 0
  lookback_days: 60
  required_tickers:
    - HBM1
    - AI1
baskets:
  ai:
    AI1: 1.0
  hbm:
    HBM1: 1.0
coach:
  interactive_input: false
""",
        encoding="utf-8",
    )
    portfolio_path.write_text(
        """
base_currency: HKD
positions:
  HBM1:
    shares: 200
    average_cost: 10
cash:
  HKD: 0
""",
        encoding="utf-8",
    )

    class EmptyYFinanceProvider:
        source_name = "yfinance"

        def fetch(self, request):
            return pd.DataFrame(columns=PRICE_COLUMNS)

    def fake_provider_factory(name, csv_path=None):
        if name == "yfinance":
            return EmptyYFinanceProvider()
        return CsvMarketDataProvider(csv_path)

    monkeypatch.setattr(
        "aios.app.runner.create_market_data_provider",
        fake_provider_factory,
    )

    assert main(
        [
            "--config",
            str(config_path),
            "--portfolio",
            str(portfolio_path),
            "--provider",
            "yfinance",
            "--output-dir",
            str(output_dir),
            "--no-input",
        ]
    ) == 0

    signal = json.loads((output_dir / "latest_signal.json").read_text())
    assert signal["provider_used"] == "csv"
    assert signal["fallback_used"] is True
    assert "Falling back to CSV cache" in (output_dir / "execution.log").read_text(
        encoding="utf-8"
    )


def test_main_merges_csv_cache_when_yahoo_returns_partial_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    csv_path = _write_orchestrator_fixture(tmp_path)
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    output_dir = tmp_path / "reports"

    config_path.write_text(
        f"""
app:
  output_dir: {output_dir}
  log_level: INFO
data:
  primary_provider: yfinance
  fallback_provider: csv
  csv_path: {csv_path}
  retry_attempts: 1
  retry_delay_seconds: 0
  lookback_days: 60
  required_tickers:
    - HBM1
    - AI1
baskets:
  ai:
    AI1: 1.0
  hbm:
    HBM1: 1.0
coach:
  interactive_input: false
""",
        encoding="utf-8",
    )
    portfolio_path.write_text(
        """
base_currency: HKD
positions:
  HBM1:
    shares: 200
    average_cost: 10
cash:
  HKD: 0
""",
        encoding="utf-8",
    )

    class PartialYFinanceProvider:
        source_name = "yfinance"

        def fetch(self, request):
            return CsvMarketDataProvider(csv_path).fetch(
                MarketDataRequest(tickers=["AI1"], lookback_days=request.lookback_days)
            )

    def fake_provider_factory(name, csv_path=None):
        if name == "yfinance":
            return PartialYFinanceProvider()
        return CsvMarketDataProvider(csv_path)

    monkeypatch.setattr(
        "aios.app.runner.create_market_data_provider",
        fake_provider_factory,
    )

    assert main(
        [
            "--config",
            str(config_path),
            "--portfolio",
            str(portfolio_path),
            "--provider",
            "yfinance",
            "--output-dir",
            str(output_dir),
            "--no-input",
        ]
    ) == 0

    signal = json.loads((output_dir / "latest_signal.json").read_text())
    assert signal["provider_used"] == "yfinance+csv"
    assert signal["fallback_used"] is True
    assert signal["missing_tickers"] == []
    history = pd.read_csv(output_dir / "history.csv")
    assert set(history["ticker"]) == {"HBM1", "AI1"}


def test_seed_cache_upserts_without_duplicate_rows(
    tmp_path: Path,
    capsys,
) -> None:
    source_csv = _write_orchestrator_fixture(tmp_path)
    cache_csv = tmp_path / "market_cache.csv"
    config_path = tmp_path / "config.yaml"

    config_path.write_text(
        f"""
data:
  primary_provider: csv
  csv_path: {source_csv}
  lookback_days: 60
  required_tickers:
    - HBM1
    - AI1
    - MISSING
""",
        encoding="utf-8",
    )

    args = [
        "seed-cache",
        "--config",
        str(config_path),
        "--provider",
        "csv",
        "--output",
        str(cache_csv),
    ]
    assert main(args) == 0
    assert main(args) == 0

    cache = pd.read_csv(cache_csv)
    assert set(cache["ticker"]) == {"HBM1", "AI1"}
    assert cache.duplicated(["date", "ticker"]).sum() == 0
    captured = capsys.readouterr()
    assert "Missing tickers: MISSING" in captured.out
    assert "Coverage: 66.67%" in captured.out


def test_manual_cache_template_and_import_close_only_csv(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "config.yaml"
    template_path = tmp_path / "manual_template.csv"
    cache_path = tmp_path / "market_cache.csv"
    manual_path = tmp_path / "manual_prices.csv"
    config_path.write_text(
        """
data:
  required_tickers:
    - AI1
    - HBM1
""",
        encoding="utf-8",
    )

    assert main(
        [
            "cache-template",
            "--config",
            str(config_path),
            "--output",
            str(template_path),
        ]
    ) == 0
    template = pd.read_csv(template_path)
    assert set(template["ticker"]) == {"AI1", "HBM1"}
    assert {"date", "ticker", "close"}.issubset(template.columns)

    manual_path.write_text(
        """
date,ticker,close
2026-01-01,AI1,100
2026-01-02,AI1,101
2026-01-01,HBM1,110
2026-01-02,HBM1,112
""".lstrip(),
        encoding="utf-8",
    )
    args = [
        "import-cache",
        "--config",
        str(config_path),
        "--input",
        str(manual_path),
        "--output",
        str(cache_path),
    ]
    assert main(args) == 0
    assert main(args) == 0

    cache = pd.read_csv(cache_path)
    assert list(cache.columns) == PRICE_COLUMNS
    assert cache.duplicated(["date", "ticker"]).sum() == 0
    assert set(cache["ticker"]) == {"AI1", "HBM1"}
    assert set(cache["open"]) == set(cache["close"])
    captured = capsys.readouterr()
    assert "Missing tickers after import: None" in captured.out
    assert "Coverage: 100.00%" in captured.out


def _write_orchestrator_fixture(tmp_path: Path) -> Path:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(60):
        rows.extend(
            [
                _row(start, offset, "AI1", 100 + offset),
                _row(start, offset, "AI2", 100 + offset),
                _row(start, offset, "HBM1", 100 + (offset * 1.4)),
                _row(start, offset, "HBM2", 100 + (offset * 1.1)),
            ]
        )

    csv_path = tmp_path / "orchestrator_prices.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


def _row(start: date, offset: int, ticker: str, close: float) -> dict[str, object]:
    return {
        "date": start + timedelta(days=offset),
        "ticker": ticker,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "adj_close": close,
        "volume": 1000 + offset,
    }

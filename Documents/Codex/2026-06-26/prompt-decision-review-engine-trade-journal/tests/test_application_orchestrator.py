from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

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
    assert signal["top_reasons"]

    html = (output_dir / "dashboard.html").read_text(encoding="utf-8")
    assert "AIOS Daily Dashboard" in html
    assert signal["recommendation"] in html

    workbook = load_workbook(output_dir / "investment_dashboard.xlsx")
    assert workbook["Dashboard"]["B4"].value == signal["recommendation"]

    history = pd.read_csv(output_dir / "history.csv")
    assert set(history["ticker"]) == {"HBM1", "HBM2", "AI1", "AI2"}


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

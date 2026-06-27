from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from aios.config.loader import load_config
from main import main


def test_proxy_config_is_disabled_by_default() -> None:
    config = load_config("config.yaml")

    assert config.proxy.enabled is False


def test_legacy_proxy_file_is_ignored_by_manual_only_runner(tmp_path: Path) -> None:
    official_cache = _write_official_cache(tmp_path)
    proxy_output = tmp_path / "data" / "proxy" / "tradable_proxy_prices.csv"
    output_dir = tmp_path / "reports"
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    proxy_output.parent.mkdir(parents=True, exist_ok=True)
    proxy_output.write_text(
        "date,ticker,proxy_symbol,proxy_price,proxy_change_pct,source,provider,timestamp,session,warning\n"
        "2026-01-30,MU,MUUSDT,1000,-5,legacy,binance,2026-01-30T00:00:00+00:00,manual,legacy\n",
        encoding="utf-8",
    )
    original_proxy_text = proxy_output.read_text(encoding="utf-8")

    config_path.write_text(
        f"""
app:
  output_dir: {output_dir}
data:
  primary_provider: csv
  csv_path: {official_cache}
  required_tickers:
    - AI1
    - HBM1
baskets:
  ai:
    AI1: 1.0
  hbm:
    HBM1: 1.0
proxy:
  enabled: true
  output_path: {proxy_output}
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

    assert "proxy_intraday_signal" not in signal
    assert proxy_output.read_text(encoding="utf-8") == original_proxy_text
    assert "Proxy Intraday Market Signal" not in (
        output_dir / "dashboard.html"
    ).read_text(encoding="utf-8")


def _write_official_cache(tmp_path: Path) -> Path:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(30):
        rows.extend(
            [
                _official_row(start, offset, "AI1", 100 + offset),
                _official_row(start, offset, "HBM1", 110 + offset),
            ]
        )
    path = tmp_path / "market_cache.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _official_row(
    start: date,
    offset: int,
    ticker: str,
    close: float,
) -> dict[str, object]:
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

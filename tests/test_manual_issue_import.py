from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from aios.data.models import PRICE_COLUMNS
from aios.manual.importer import ManualIssueImporter
from aios.manual.issue_parser import (
    ManualPriceIssueParseError,
    parse_manual_price_issue,
)
from main import main


def test_parse_valid_issue_body_normalizes_source() -> None:
    parsed = parse_manual_price_issue(_issue_body())

    assert parsed.trading_date == "2026-06-27"
    assert parsed.latest_date == "2026-06-27"
    assert parsed.tickers == ["000660.KS", "005930.KS", "7709.HK", "MU"]
    assert parsed.rows.loc[parsed.rows["ticker"] == "MU", "close"].iloc[0] == 1155.0
    assert set(parsed.rows["source"]) == {"manual_upload"}
    assert "Missing required basket tickers" in parsed.warnings[0]


def test_accepts_optional_columns_missing() -> None:
    body = _issue_body(
        "date,ticker,close\n"
        "2026-06-27,MU,1155",
    )

    parsed = parse_manual_price_issue(body)

    assert parsed.rows["ticker"].iloc[0] == "MU"
    assert parsed.rows["source"].iloc[0] == "manual_upload"
    assert parsed.rows["note"].iloc[0] == ""


def test_reject_missing_required_close_column() -> None:
    body = """
### Trading date
2026-06-27

### Price CSV
```csv
date,ticker
2026-06-27,MU
```
""".strip()

    with pytest.raises(ManualPriceIssueParseError, match="missing required columns"):
        parse_manual_price_issue(body)


def test_reject_invalid_price() -> None:
    body = _issue_body(
        "date,ticker,close,change_pct,market_cap,source,note\n"
        "2026-06-27,MU,-1,-4.8,,futu,bad price"
    )

    with pytest.raises(ManualPriceIssueParseError, match="greater than 0"):
        parse_manual_price_issue(body)


def test_duplicate_date_ticker_keeps_last_price() -> None:
    body = _issue_body(
        "date,ticker,close,change_pct,market_cap,source,note\n"
        "2026-06-27,MU,115.00,-4.8,,futu,first\n"
        "2026-06-27,MU,116.50,-3.7,,futu,corrected"
    )

    parsed = parse_manual_price_issue(body)

    assert len(parsed.rows) == 1
    assert parsed.rows["close"].iloc[0] == 116.5
    assert parsed.rows["note"].iloc[0] == "corrected"
    assert parsed.rows["source"].iloc[0] == "manual_upload"


def test_import_issue_upserts_all_sources_into_cache(tmp_path: Path) -> None:
    paths = _write_issue_import_files(tmp_path)
    _write_cache_fixture(paths["cache"], latest_offset=24)
    paths["issue"].write_text(
        _issue_body(
            "date,ticker,close,change_pct,market_cap,source,note\n"
            "2026-01-26,AI1,333.00,1.2,,binance_proxy,accepted\n"
            "2026-01-26,HBM1,444.00,2.4,,futu_official,accepted",
            trading_date="2026-01-26",
        ),
        encoding="utf-8",
    )

    importer = ManualIssueImporter(
        config_path=paths["config"],
        portfolio_path=paths["portfolio"],
        issue_body_file=paths["issue"],
        manual_output_path=paths["manual"],
        cache_output_path=paths["cache"],
        output_dir=paths["reports"],
    )

    summary = importer.import_prices()
    summary_again = importer.import_prices()

    assert summary.imported_tickers == ["AI1", "HBM1"]
    assert summary_again.imported_rows == 2
    assert not paths["proxy"].exists()

    manual = pd.read_csv(paths["manual"])
    cache = pd.read_csv(paths["cache"])
    assert manual.duplicated(["date", "ticker"]).sum() == 0
    assert cache.duplicated(["date", "ticker"]).sum() == 0
    assert set(manual["source"]) == {"manual_upload"}
    assert cache[(cache["date"] == "2026-01-26") & (cache["ticker"] == "AI1")][
        "close"
    ].iloc[0] == 333.0


def test_import_issue_command_regenerates_reports_with_manual_only_metadata(
    tmp_path: Path,
) -> None:
    paths = _write_issue_import_files(tmp_path)
    _write_cache_fixture(paths["cache"], latest_offset=24)
    paths["issue"].write_text(
        _issue_body(
            "date,ticker,close,change_pct,market_cap,source,note\n"
            "2026-01-26,AI1,333.00,1.2,,manual,AI latest\n"
            "2026-01-26,HBM1,444.00,2.4,,manual,HBM latest",
            trading_date="2026-01-26",
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "import-issue",
            "--config",
            str(paths["config"]),
            "--portfolio",
            str(paths["portfolio"]),
            "--issue-body-file",
            str(paths["issue"]),
            "--manual-output",
            str(paths["manual"]),
            "--cache-output",
            str(paths["cache"]),
            "--output-dir",
            str(paths["reports"]),
            "--no-input",
        ]
    ) == 0

    signal = json.loads((paths["reports"] / "latest_signal.json").read_text())
    assert signal["data_source"] == "Manual Upload Only"
    assert signal["manual_mobile_input_used"] is True
    assert signal["latest_manual_input_date"] == "2026-01-26"
    assert signal["manual_source"] == "manual_upload"
    assert signal["manual_tickers_used"] == ["AI1", "HBM1"]
    assert signal["provider_by_ticker"]["AI1"] == "manual_upload"
    assert "proxy_intraday_signal" not in signal
    assert (paths["reports"] / "dashboard.html").exists()
    assert (paths["reports"] / "investment_dashboard.xlsx").exists()


def test_missing_required_ticker_warning_is_non_fatal() -> None:
    parsed = parse_manual_price_issue(
        _issue_body(
            "date,ticker,close,change_pct,market_cap,source,note\n"
            "2026-06-27,MU,115.00,-4.8,,futu,only one ticker"
        )
    )

    assert parsed.tickers == ["MU"]
    assert any("MSFT" in warning for warning in parsed.warnings)


def test_missing_history_keeps_risk_score_na(tmp_path: Path) -> None:
    paths = _write_issue_import_files(tmp_path)
    paths["issue"].write_text(
        _issue_body(
            "date,ticker,close,change_pct,market_cap,source,note\n"
            "2026-01-01,AI1,100,1,,binance,one day\n"
            "2026-01-01,HBM1,120,1,,futu,one day",
            trading_date="2026-01-01",
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "import-issue",
            "--config",
            str(paths["config"]),
            "--portfolio",
            str(paths["portfolio"]),
            "--issue-body-file",
            str(paths["issue"]),
            "--manual-output",
            str(paths["manual"]),
            "--cache-output",
            str(paths["cache"]),
            "--output-dir",
            str(paths["reports"]),
            "--no-input",
        ]
    ) == 0

    signal = json.loads((paths["reports"] / "latest_signal.json").read_text())
    assert signal["recommendation"] == "Uncertain"
    assert signal["risk_score"] is None
    assert signal["risk_score_display"] == "N/A"
    assert signal["five_day_readiness"] == {"AI1": False, "HBM1": False}


def _issue_body(
    csv_text: str | None = None,
    trading_date: str = "2026-06-27",
) -> str:
    csv_text = csv_text or (
        "date,ticker,close,change_pct,market_cap,source,note\n"
        "2026-06-27,7709.HK,154.00,-14.20,,futu,\"HK intraday\"\n"
        "2026-06-27,000660.KS,2724000,-8.50,,naver,\"SK Hynix\"\n"
        "2026-06-27,005930.KS,343500,-4.00,,okx,\"Samsung\"\n"
        "2026-06-27,MU,1155.00,-4.80,,binance_proxy,\"overnight\""
    )
    return f"""
### Trading date
{trading_date}

### Price CSV
```csv
{csv_text}
```

### Optional market notes
Manual mobile input.
""".strip()


def _write_issue_import_files(tmp_path: Path) -> dict[str, Path]:
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    cache_path = data_dir / "cache" / "market_cache.csv"
    manual_path = data_dir / "manual" / "daily_manual_prices.csv"
    proxy_path = data_dir / "proxy" / "tradable_proxy_prices.csv"
    reports_dir = tmp_path / "reports"
    issue_path = tmp_path / "issue_body.txt"
    config_path.write_text(
        f"""
app:
  output_dir: {reports_dir}
  log_level: INFO
data:
  primary_provider: csv
  csv_path: {cache_path}
  lookback_days: 60
  required_tickers:
    - AI1
    - HBM1
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
    return {
        "config": config_path,
        "portfolio": portfolio_path,
        "cache": cache_path,
        "manual": manual_path,
        "proxy": proxy_path,
        "reports": reports_dir,
        "issue": issue_path,
    }


def _write_cache_fixture(cache_path: Path, latest_offset: int) -> Path:
    start = date(2026, 1, 1)
    rows = []
    for offset in range(latest_offset + 1):
        rows.append(_price_row(start, offset, "AI1", 100 + offset))
        rows.append(_price_row(start, offset, "HBM1", 120 + (offset * 1.5)))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(cache_path, index=False)
    return cache_path


def _price_row(
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

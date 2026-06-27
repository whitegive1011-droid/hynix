from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from aios.manual.importer import ManualIssueImporter
from aios.manual.issue_parser import (
    ManualPriceIssueParseError,
    parse_manual_price_issue,
)
from main import main


def test_parse_valid_issue_body() -> None:
    parsed = parse_manual_price_issue(_issue_body())

    assert parsed.trading_date == "2026-06-27"
    assert parsed.latest_date == "2026-06-27"
    assert parsed.tickers == ["000660.KS", "005930.KS", "7709.HK", "MU"]
    assert parsed.rows.loc[parsed.rows["ticker"] == "MU", "close"].iloc[0] == 1155.0
    assert "Missing required basket tickers" in parsed.warnings[0]


def test_reject_malformed_csv() -> None:
    body = """
### Trading date
2026-06-27

### Price CSV
```csv
date,ticker,close
2026-06-27,MU,1155
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


def test_import_issue_upserts_manual_rows_into_cache(tmp_path: Path) -> None:
    paths = _write_issue_import_files(tmp_path)
    initial_cache = _write_cache_fixture(paths["cache"], latest_offset=24)
    body_path = paths["issue"]
    body_path.write_text(
        _issue_body(
            "date,ticker,close,change_pct,market_cap,source,note\n"
            "2026-01-26,AI1,333.00,1.2,,manual,corrected AI\n"
            "2026-01-26,HBM1,444.00,2.4,,manual,corrected HBM",
            trading_date="2026-01-26",
        ),
        encoding="utf-8",
    )

    importer = ManualIssueImporter(
        config_path=paths["config"],
        portfolio_path=paths["portfolio"],
        issue_body_file=body_path,
        manual_output_path=paths["manual"],
        cache_output_path=initial_cache,
        output_dir=paths["reports"],
    )

    summary = importer.import_prices()
    summary_again = importer.import_prices()

    assert summary.imported_tickers == ["AI1", "HBM1"]
    assert summary_again.imported_rows == 2

    manual = pd.read_csv(paths["manual"])
    cache = pd.read_csv(paths["cache"])
    assert manual.duplicated(["date", "ticker"]).sum() == 0
    assert cache.duplicated(["date", "ticker"]).sum() == 0
    assert cache[(cache["date"] == "2026-01-26") & (cache["ticker"] == "AI1")][
        "close"
    ].iloc[0] == 333.0
    assert set(manual["input_source"]) == {"GitHub Issue"}


def test_import_issue_command_regenerates_reports_with_manual_metadata(
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
    assert signal["manual_mobile_input_used"] is True
    assert signal["latest_manual_input_date"] == "2026-01-26"
    assert signal["manual_source"] == "GitHub Issue"
    assert signal["manual_tickers_used"] == ["AI1", "HBM1"]
    assert signal["provider_by_ticker"]["AI1"] == "GitHub Issue"
    assert (paths["reports"] / "dashboard.html").exists()
    assert (paths["reports"] / "investment_dashboard.xlsx").exists()


def test_import_issue_proxy_rows_feed_proxy_signal_without_official_cache(
    tmp_path: Path,
) -> None:
    paths = _write_issue_import_files(tmp_path)
    _write_cache_fixture(paths["cache"], latest_offset=24)
    paths["config"].write_text(
        f"""
app:
  output_dir: {paths["reports"]}
  log_level: INFO
data:
  primary_provider: csv
  csv_path: {paths["cache"]}
  lookback_days: 60
  required_tickers:
    - AAPL
    - MSFT
    - TSLA
    - MU
baskets:
  ai:
    AAPL: 0.3333
    MSFT: 0.3333
    TSLA: 0.3334
  hbm:
    MU: 1.0
proxy:
  enabled: false
  symbols:
    NVDA: NVDAUSDT
    AAPL: AAPLUSDT
    MSFT: MSFTUSDT
    TSLA: TSLAUSDT
    MU: MUUSDT
  output_path: {paths["proxy"]}
coach:
  interactive_input: false
""",
        encoding="utf-8",
    )
    paths["issue"].write_text(
        _issue_body(
            "date,ticker,close,change_pct,market_cap,source,note\n"
            "2026-01-26,NVDA,193.69,-0.06,,binance_proxy,\"NVDAUSDT proxy\"\n"
            "2026-01-26,AAPL,281.38,1.88,,binance_proxy,\"AAPLUSDT proxy\"\n"
            "2026-01-26,MSFT,374.68,4.99,,binance_proxy,\"MSFTUSDT proxy\"\n"
            "2026-01-26,TSLA,380.47,2.41,,binance_proxy,\"TSLAUSDT proxy\"\n"
            "2026-01-26,MU,1138.19,-1.55,,binance_proxy,\"MUUSDT proxy\"",
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

    cache = pd.read_csv(paths["cache"])
    proxy_cache = pd.read_csv(paths["proxy"])
    signal = json.loads((paths["reports"] / "latest_signal.json").read_text())

    assert {"NVDA", "AAPL", "MSFT", "TSLA", "MU"}.isdisjoint(
        set(cache["ticker"])
    )
    assert set(proxy_cache["ticker"]) == {"NVDA", "AAPL", "MSFT", "TSLA", "MU"}
    assert signal["proxy_intraday_signal"]["available"] is True
    assert signal["proxy_intraday_signal"]["provider_used"] == "binance_proxy"
    assert signal["proxy_intraday_signal"]["proxy_data_quality"] == "OK"
    assert signal["proxy_intraday_signal"]["proxy_ai_1d_change"] is not None
    assert signal["proxy_intraday_signal"]["proxy_hbm_1d_change"] is not None


def test_missing_required_ticker_warning_is_non_fatal() -> None:
    parsed = parse_manual_price_issue(
        _issue_body(
            "date,ticker,close,change_pct,market_cap,source,note\n"
            "2026-06-27,MU,115.00,-4.8,,futu,only one ticker"
        )
    )

    assert parsed.tickers == ["MU"]
    assert any("MSFT" in warning for warning in parsed.warnings)


def _issue_body(
    csv_text: str | None = None,
    trading_date: str = "2026-06-27",
) -> str:
    csv_text = csv_text or (
        "date,ticker,close,change_pct,market_cap,source,note\n"
        "2026-06-27,7709.HK,154.00,-14.20,,futu,\"HK intraday\"\n"
        "2026-06-27,000660.KS,2724000,-8.50,,naver,\"SK Hynix\"\n"
        "2026-06-27,005930.KS,343500,-4.00,,naver,\"Samsung\"\n"
        "2026-06-27,MU,1155.00,-4.80,,futu,\"overnight\""
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
proxy:
  enabled: false
  symbols:
    NVDA: NVDAUSDT
    AAPL: AAPLUSDT
    MSFT: MSFTUSDT
    TSLA: TSLAUSDT
    MU: MUUSDT
  output_path: {data_dir / "proxy" / "tradable_proxy_prices.csv"}
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
        "proxy": data_dir / "proxy" / "tradable_proxy_prices.csv",
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

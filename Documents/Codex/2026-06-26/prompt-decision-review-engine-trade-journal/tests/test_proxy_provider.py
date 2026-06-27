from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from aios.data.models import PRICE_COLUMNS
from aios.proxy.models import PROXY_PRICE_COLUMNS, PROXY_WARNING, ProxyPriceRequest
from aios.proxy.providers import (
    BINANCE_FUTURES_TICKER_URL,
    BinanceProxyPriceProvider,
    FixtureProxyPriceProvider,
    TradableProxyPriceProvider,
)
from aios.proxy.signal import ProxySignalEngine
from main import main


def test_proxy_provider_merges_partial_results_by_priority() -> None:
    provider = TradableProxyPriceProvider(
        [
            FixtureProxyPriceProvider(
                _proxy_frame(
                    [
                        ("NVDA", "NVDA-USD-SWAP", -2.0, "okx"),
                    ]
                )
            ),
            FixtureProxyPriceProvider(
                _proxy_frame(
                    [
                        ("NVDA", "NVDABUSD", -9.0, "binance"),
                        ("MU", "MUBUSD", -4.5, "binance"),
                    ]
                )
            ),
        ]
    )

    result = provider.fetch(
        ProxyPriceRequest(
            symbols={"NVDA": "NVDA-USD-SWAP", "MU": "MUBUSD"},
            provider_priority=["okx", "binance"],
        )
    )

    assert set(result["ticker"]) == {"NVDA", "MU"}
    provider_by_ticker = dict(zip(result["ticker"], result["provider"]))
    assert provider_by_ticker["NVDA"] == "okx"
    assert provider_by_ticker["MU"] == "binance"
    assert result.duplicated(["date", "ticker"]).sum() == 0


def test_binance_proxy_provider_uses_usd_m_futures_endpoint_first(
    monkeypatch,
) -> None:
    requested_urls: list[str] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        @staticmethod
        def read() -> bytes:
            return json.dumps(
                {
                    "symbol": "AAPLUSDT",
                    "lastPrice": "281.21",
                    "priceChangePercent": "1.597",
                    "closeTime": 1782525600000,
                }
            ).encode("utf-8")

    def fake_urlopen(url, timeout):
        requested_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(
        "aios.proxy.providers.urllib.request.urlopen",
        fake_urlopen,
    )

    result = BinanceProxyPriceProvider(timeout_seconds=1).fetch(
        ProxyPriceRequest(
            symbols={"AAPL": "AAPLUSDT"},
            provider_priority=["binance"],
        )
    )

    assert requested_urls
    assert requested_urls[0].startswith(BINANCE_FUTURES_TICKER_URL)
    assert result["ticker"].iloc[0] == "AAPL"
    assert result["proxy_symbol"].iloc[0] == "AAPLUSDT"
    assert result["provider"].iloc[0] == "binance"
    assert result["source"].iloc[0] == "Binance public USD-M futures 24hr ticker"


def test_proxy_prices_are_stored_separately_and_do_not_enter_official_cache(
    tmp_path: Path,
) -> None:
    official_cache = _write_official_cache(tmp_path)
    proxy_fixture = tmp_path / "proxy_fixture.csv"
    proxy_output = tmp_path / "data" / "proxy" / "tradable_proxy_prices.csv"
    output_dir = tmp_path / "reports"
    config_path = tmp_path / "config.yaml"
    portfolio_path = tmp_path / "portfolio.yaml"
    _proxy_frame(
        [
            ("MU", "MUBUSD", -4.5, "fixture"),
            ("NVDA", "NVDABUSD", -3.5, "fixture"),
        ]
    ).to_csv(proxy_fixture, index=False)

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
  provider_priority:
    - fixture
  symbols:
    MU: MUBUSD
    NVDA: NVDABUSD
  fixture_path: {proxy_fixture}
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

    stored_proxy = pd.read_csv(proxy_output)
    official_after_run = pd.read_csv(official_cache)
    signal = json.loads((output_dir / "latest_signal.json").read_text())

    assert list(stored_proxy.columns) == PROXY_PRICE_COLUMNS
    assert set(stored_proxy["ticker"]) == {"MU", "NVDA"}
    assert set(official_after_run.columns) == set(PRICE_COLUMNS)
    assert "proxy_price" not in official_after_run.columns
    assert {"MU", "NVDA"}.isdisjoint(set(official_after_run["ticker"]))
    assert signal["proxy_intraday_signal"]["available"] is True
    assert signal["proxy_intraday_signal"]["warning"] == PROXY_WARNING


def test_manual_official_price_excludes_matching_proxy_ticker() -> None:
    signal = ProxySignalEngine(
        ai_tickers=["MSFT", "AAPL", "TSLA"],
        hbm_weights={"MU": 0.5, "NVDA": 0.5},
        manual_official_tickers=["MU"],
    ).build(
        _proxy_frame(
            [
                ("MU", "MUBUSD", -10.0, "fixture"),
                ("NVDA", "NVDABUSD", 2.0, "fixture"),
            ]
        )
    )

    assert "MU" not in signal.tickers_covered
    assert signal.proxy_hbm_1d_change == 2.0


def _proxy_frame(rows: list[tuple[str, str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-06-27",
                "ticker": ticker,
                "proxy_symbol": symbol,
                "proxy_price": 100.0 + index,
                "proxy_change_pct": change_pct,
                "source": "fixture",
                "provider": provider,
                "timestamp": f"2026-06-27T10:{index:02d}:00+00:00",
                "session": "intraday",
                "warning": PROXY_WARNING,
            }
            for index, (ticker, symbol, change_pct, provider) in enumerate(rows)
        ]
    )


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

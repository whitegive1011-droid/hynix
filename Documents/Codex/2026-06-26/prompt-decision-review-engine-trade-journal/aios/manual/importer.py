"""Import manual GitHub Issue prices into AIOS cache and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from aios.app.runner import AiosRunner
from aios.config.loader import load_config
from aios.config.models import AiosConfig
from aios.data.quality import build_cache_coverage_report
from aios.manual.issue_parser import (
    MANUAL_DAILY_PRICE_COLUMNS,
    ManualPriceIssueRows,
    build_manual_issue_warnings,
    parse_manual_price_issue,
)
from aios.proxy.models import PROXY_PRICE_COLUMNS, PROXY_WARNING
from aios.storage.csv_store import upsert_csv


@dataclass(frozen=True)
class ManualIssueImportSummary:
    imported_rows: int
    imported_tickers: list[str]
    official_rows: int
    proxy_rows: int
    latest_date: str
    warnings: list[str]
    manual_output_path: Path
    cache_output_path: Path
    proxy_output_path: Path
    output_dir: Path


class ManualIssueImporter:
    """Import one GitHub Issue submission and regenerate AIOS reports."""

    def __init__(
        self,
        config_path: Path,
        portfolio_path: Path,
        issue_body_file: Path,
        manual_output_path: Path,
        cache_output_path: Path,
        output_dir: Path,
        no_input: bool = True,
    ) -> None:
        self.config_path = config_path
        self.portfolio_path = portfolio_path
        self.issue_body_file = issue_body_file
        self.manual_output_path = manual_output_path
        self.cache_output_path = cache_output_path
        self.output_dir = output_dir
        self.no_input = no_input

    def run(self) -> int:
        summary = self.import_prices()
        self._print_summary(summary)
        AiosRunner(
            config_path=self.config_path,
            portfolio_path=self.portfolio_path,
            provider_override="csv",
            output_dir_override=self.output_dir,
            no_input=self.no_input,
            csv_path_override=self.cache_output_path,
            manual_input_path_override=self.manual_output_path,
        ).run()
        return 0

    def import_prices(self) -> ManualIssueImportSummary:
        if not self.issue_body_file.exists():
            raise FileNotFoundError(
                f"Issue body file not found: {self.issue_body_file}"
            )

        parsed = parse_manual_price_issue(
            self.issue_body_file.read_text(encoding="utf-8")
        )
        config = load_config(self.config_path)
        official_rows = _official_issue_rows(parsed.rows)
        proxy_rows = _proxy_issue_rows(parsed.rows)
        self._upsert_daily_manual_prices(official_rows)
        stored_cache = upsert_csv(
            path=self.cache_output_path,
            frame=parsed.to_cache_frame(official_rows),
            key_columns=["date", "ticker"],
        )
        self._upsert_proxy_prices(proxy_rows, config)

        report = build_cache_coverage_report(
            prices=stored_cache,
            required_tickers=config.data.required_tickers,
            provider_by_ticker={
                ticker: "GitHub Issue" for ticker in parsed.tickers
            },
            stale_price_days=config.data_quality.stale_price_days,
        )
        warnings = [
            *parsed.warnings,
            *(
                [
                    "Proxy rows were stored separately and were not treated as "
                    "official equity market data."
                ]
                if not proxy_rows.empty
                else []
            ),
            *(
                [
                    "Missing configured tickers after import: "
                    + ", ".join(report.missing_tickers)
                ]
                if report.missing_tickers
                else []
            ),
        ]
        return ManualIssueImportSummary(
            imported_rows=len(parsed.rows),
            imported_tickers=parsed.tickers,
            official_rows=len(official_rows),
            proxy_rows=len(proxy_rows),
            latest_date=parsed.latest_date,
            warnings=warnings,
            manual_output_path=self.manual_output_path,
            cache_output_path=self.cache_output_path,
            proxy_output_path=config.proxy.output_path,
            output_dir=self.output_dir,
        )

    def _upsert_daily_manual_prices(
        self,
        rows: pd.DataFrame,
    ) -> pd.DataFrame:
        rows = rows.copy()
        if rows.empty:
            return upsert_csv(
                path=self.manual_output_path,
                frame=pd.DataFrame(columns=MANUAL_DAILY_PRICE_COLUMNS),
                key_columns=["date", "ticker"],
            )
        rows["input_source"] = "GitHub Issue"
        rows["imported_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        )
        return upsert_csv(
            path=self.manual_output_path,
            frame=rows[MANUAL_DAILY_PRICE_COLUMNS],
            key_columns=["date", "ticker"],
        )

    def _upsert_proxy_prices(
        self,
        rows: pd.DataFrame,
        config: AiosConfig,
    ) -> pd.DataFrame:
        proxy_frame = _manual_proxy_rows_to_proxy_frame(rows, config)
        if proxy_frame.empty:
            return proxy_frame
        return upsert_csv(
            path=config.proxy.output_path,
            frame=proxy_frame,
            key_columns=["date", "ticker", "provider"],
        )

    @staticmethod
    def _print_summary(summary: ManualIssueImportSummary) -> None:
        print("AIOS Manual Issue Import")
        print("========================")
        print(f"Imported rows: {summary.imported_rows}")
        print(f"Official rows: {summary.official_rows}")
        print(f"Proxy rows: {summary.proxy_rows}")
        print(f"Latest manual input date: {summary.latest_date}")
        print(
            "Manual tickers used: "
            + (", ".join(summary.imported_tickers) or "None")
        )
        print(f"Manual file: {summary.manual_output_path}")
        print(f"Cache file: {summary.cache_output_path}")
        print(f"Proxy file: {summary.proxy_output_path}")
        print(f"Reports output: {summary.output_dir}")
        if summary.warnings:
            print("Warnings:")
            for warning in summary.warnings:
                print(f"- {warning}")
        else:
            print("Warnings: None")


def missing_required_basket_warning(rows: pd.DataFrame) -> list[str]:
    """Return warnings for tests and lightweight callers."""

    return build_manual_issue_warnings(rows)


def _proxy_issue_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    proxy_mask = (
        rows["source"].astype(str).str.contains("proxy", case=False, na=False)
        | rows["note"].astype(str).str.contains("proxy", case=False, na=False)
    )
    return rows[proxy_mask].copy()


def _official_issue_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    proxy_index = set(_proxy_issue_rows(rows).index)
    return rows[~rows.index.isin(proxy_index)].copy()


def _manual_proxy_rows_to_proxy_frame(
    rows: pd.DataFrame,
    config: AiosConfig,
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=PROXY_PRICE_COLUMNS)

    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    proxy_rows = []
    for row in rows.to_dict(orient="records"):
        ticker = str(row["ticker"])
        proxy_rows.append(
            {
                "date": str(row["date"]),
                "ticker": ticker,
                "proxy_symbol": _proxy_symbol_for_row(row, config),
                "proxy_price": float(row["close"]),
                "proxy_change_pct": row.get("change_pct"),
                "source": "GitHub Issue",
                "provider": str(row.get("source") or "manual_proxy"),
                "timestamp": imported_at,
                "session": "manual",
                "warning": PROXY_WARNING,
            }
        )
    return pd.DataFrame(proxy_rows, columns=PROXY_PRICE_COLUMNS)


def _proxy_symbol_for_row(row: dict[str, object], config: AiosConfig) -> str:
    ticker = str(row["ticker"])
    configured = config.proxy.symbols.get(ticker)
    if configured:
        return configured

    note = str(row.get("note") or "")
    for token in note.replace(",", " ").replace('"', " ").split():
        cleaned = token.strip()
        if cleaned.endswith("USDT") or cleaned.endswith("BUSD"):
            return cleaned
    return ticker

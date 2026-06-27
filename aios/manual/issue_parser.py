"""Parse manual price submissions from GitHub Issues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import StringIO
import math
import re

import pandas as pd

from aios.data.models import PRICE_COLUMNS


ISSUE_PRICE_COLUMNS = [
    "date",
    "ticker",
    "close",
    "change_pct",
    "market_cap",
    "source",
    "note",
]

REQUIRED_ISSUE_PRICE_COLUMNS = ["date", "ticker", "close"]

MANUAL_DAILY_PRICE_COLUMNS = [
    *ISSUE_PRICE_COLUMNS,
    "input_source",
    "imported_at",
]

REQUIRED_BASKET_TICKERS = [
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "AAPL",
    "TSLA",
    "000660.KS",
    "MU",
    "005930.KS",
]

OPTIONAL_MANUAL_TICKERS = [
    "NVDA",
    "QQQ",
    "SOXX",
    "7709.HK",
    "7747.HK",
]


class ManualPriceIssueParseError(ValueError):
    """Raised when a manual price issue body cannot be parsed safely."""


@dataclass(frozen=True)
class ManualPriceIssueRows:
    """Normalized manual price rows parsed from one GitHub Issue body."""

    rows: pd.DataFrame
    trading_date: str | None
    warnings: list[str]

    @property
    def tickers(self) -> list[str]:
        return sorted(self.rows["ticker"].astype(str).unique())

    @property
    def latest_date(self) -> str:
        return max(self.rows["date"].astype(str))

    def to_cache_frame(self, rows: pd.DataFrame | None = None) -> pd.DataFrame:
        return manual_issue_rows_to_cache_frame(self.rows if rows is None else rows)


def parse_manual_price_issue(body: str) -> ManualPriceIssueRows:
    """Parse and validate a GitHub Issue manual price submission."""

    if not body or not body.strip():
        raise ManualPriceIssueParseError("Issue body is empty.")

    trading_date = _extract_trading_date(body)
    csv_text = extract_price_csv_text(body)
    rows = _read_issue_csv(csv_text)
    rows = _normalize_issue_rows(rows)

    if trading_date is not None:
        mismatched = sorted(
            date_value
            for date_value in rows["date"].astype(str).unique()
            if date_value != trading_date
        )
        if mismatched:
            raise ManualPriceIssueParseError(
                "CSV dates do not match Trading date "
                f"{trading_date}: {', '.join(mismatched)}"
            )

    return ManualPriceIssueRows(
        rows=rows,
        trading_date=trading_date,
        warnings=build_manual_issue_warnings(rows),
    )


def extract_price_csv_text(body: str) -> str:
    """Extract the CSV textarea payload from a GitHub Issue body."""

    for block in re.findall(
        r"```(?:csv|text)?\s*\n?(.*?)```",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        if _looks_like_price_csv(block):
            return block.strip()

    lines = body.splitlines()
    for index, line in enumerate(lines):
        if _looks_like_price_csv(line):
            collected = [line]
            for next_line in lines[index + 1 :]:
                stripped = next_line.strip()
                if stripped.startswith("### "):
                    break
                if stripped.startswith("```"):
                    continue
                if not stripped and len(collected) > 1:
                    break
                if stripped:
                    collected.append(next_line)
            return "\n".join(collected).strip()

    raise ManualPriceIssueParseError(
        "Could not find price CSV. Include a header line: "
        + ",".join(ISSUE_PRICE_COLUMNS)
    )


def manual_issue_rows_to_cache_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Convert normalized issue rows into OHLCV cache rows."""

    if rows.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    prices = pd.DataFrame(
        {
            "date": rows["date"].astype(str),
            "ticker": rows["ticker"].astype(str),
            "open": rows["close"].astype(float),
            "high": rows["close"].astype(float),
            "low": rows["close"].astype(float),
            "close": rows["close"].astype(float),
            "adj_close": rows["close"].astype(float),
            "volume": 0,
        }
    )
    return prices[PRICE_COLUMNS].drop_duplicates(
        subset=["date", "ticker"],
        keep="last",
    )


def build_manual_issue_warnings(rows: pd.DataFrame) -> list[str]:
    """Build non-fatal warnings for incomplete manual mobile submissions."""

    available = set(rows["ticker"].astype(str).unique()) if not rows.empty else set()
    missing_required = [
        ticker for ticker in REQUIRED_BASKET_TICKERS if ticker not in available
    ]
    missing_optional = [
        ticker for ticker in OPTIONAL_MANUAL_TICKERS if ticker not in available
    ]

    warnings: list[str] = []
    if missing_required:
        warnings.append(
            "Missing required basket tickers: " + ", ".join(missing_required)
        )
    if missing_optional:
        warnings.append(
            "Optional recommended tickers not included: "
            + ", ".join(missing_optional)
        )
    return warnings


def _extract_trading_date(body: str) -> str | None:
    match = re.search(
        r"^###\s+Trading date\s*$([\s\S]*?)(?=^###\s|\Z)",
        body,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return None

    for line in match.group(1).splitlines():
        value = line.strip()
        if value and value != "_No response_":
            return _validate_date(value, "Trading date")
    return None


def _read_issue_csv(csv_text: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            StringIO(csv_text),
            dtype=str,
            keep_default_na=False,
            on_bad_lines="error",
        )
    except Exception as exc:
        raise ManualPriceIssueParseError(
            f"Malformed price CSV: {exc}"
        ) from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    missing_columns = [
        column for column in REQUIRED_ISSUE_PRICE_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        raise ManualPriceIssueParseError(
            "Manual price CSV missing required columns: "
            + ", ".join(missing_columns)
        )
    for column in ISSUE_PRICE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[ISSUE_PRICE_COLUMNS].copy()


def _normalize_issue_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise ManualPriceIssueParseError("Manual price CSV contains no rows.")

    normalized_rows = []
    for index, row in frame.iterrows():
        row_number = int(index) + 2
        ticker = _normalize_ticker(row["ticker"], row_number)
        close = _required_positive_float(row["close"], "close", row_number)
        normalized_rows.append(
            {
                "date": _validate_date(row["date"], f"row {row_number} date"),
                "ticker": ticker,
                "close": close,
                "change_pct": _optional_float(
                    row["change_pct"],
                    "change_pct",
                    row_number,
                ),
                "market_cap": _optional_float(
                    row["market_cap"],
                    "market_cap",
                    row_number,
                ),
                "source": "manual_upload",
                "note": _optional_string(row["note"]),
            }
        )

    normalized = pd.DataFrame(normalized_rows, columns=ISSUE_PRICE_COLUMNS)
    normalized = normalized.drop_duplicates(
        subset=["date", "ticker"],
        keep="last",
    )
    return normalized.sort_values(["date", "ticker"]).reset_index(drop=True)


def _looks_like_price_csv(text: str) -> bool:
    first_line = next(
        (
            line.strip().lower().replace(" ", "")
            for line in text.splitlines()
            if line.strip()
        ),
        "",
    )
    return first_line.startswith("date,ticker")


def _validate_date(value: object, label: str) -> str:
    text = _optional_string(value)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ManualPriceIssueParseError(
            f"Invalid {label}: {text or '<blank>'}. Expected YYYY-MM-DD."
        )
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ManualPriceIssueParseError(
            f"Invalid {label}: {text}. Expected a real calendar date."
        ) from exc


def _normalize_ticker(value: object, row_number: int) -> str:
    ticker = _optional_string(value).upper()
    if not ticker:
        raise ManualPriceIssueParseError(
            f"Invalid ticker on row {row_number}: ticker is required."
        )
    return ticker


def _required_positive_float(value: object, label: str, row_number: int) -> float:
    number = _parse_float(value, label, row_number)
    if number is None or number <= 0:
        raise ManualPriceIssueParseError(
            f"Invalid {label} on row {row_number}: value must be greater than 0."
        )
    return number


def _optional_float(value: object, label: str, row_number: int) -> float | None:
    text = _optional_string(value)
    if not text:
        return None
    return _parse_float(text, label, row_number)


def _parse_float(value: object, label: str, row_number: int) -> float | None:
    text = _optional_string(value).replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise ManualPriceIssueParseError(
            f"Invalid {label} on row {row_number}: {text} is not numeric."
        ) from exc
    if math.isnan(number) or math.isinf(number):
        raise ManualPriceIssueParseError(
            f"Invalid {label} on row {row_number}: value must be finite."
        )
    return number


def _optional_string(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()

"""Date and run-id helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def current_run_timestamp(timezone_name: str) -> str:
    try:
        tzinfo = ZoneInfo(timezone_name)
    except Exception:
        tzinfo = timezone.utc
    return datetime.now(tzinfo).isoformat(timespec="seconds")


def run_id_from_timestamp(timestamp: str) -> str:
    return timestamp.replace(":", "").replace("+", "_plus_")

"""CSV storage helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def upsert_csv(
    path: str | Path,
    frame: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    """Write a CSV, replacing existing rows that share key values."""

    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if frame.empty:
        if not csv_path.exists():
            frame.to_csv(csv_path, index=False)
        return frame

    if csv_path.exists():
        existing = pd.read_csv(csv_path)
        if existing.empty:
            combined = frame.copy()
        else:
            combined = pd.concat([existing, frame], ignore_index=True)
    else:
        combined = frame.copy()

    combined = combined.drop_duplicates(
        subset=key_columns,
        keep="last",
    )
    combined = combined.sort_values(key_columns).reset_index(drop=True)
    combined.to_csv(csv_path, index=False)
    return combined

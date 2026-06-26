from pathlib import Path

import pandas as pd

from aios.storage.csv_store import upsert_csv


def test_upsert_csv_replaces_existing_key(tmp_path: Path) -> None:
    path = tmp_path / "history.csv"
    original = pd.DataFrame(
        [
            {"date": "2026-06-26", "ticker": "7709.HK", "source": "csv", "close": 10}
        ]
    )
    updated = pd.DataFrame(
        [
            {"date": "2026-06-26", "ticker": "7709.HK", "source": "csv", "close": 11}
        ]
    )

    upsert_csv(path, original, ["date", "ticker", "source"])
    combined = upsert_csv(path, updated, ["date", "ticker", "source"])

    assert len(combined) == 1
    assert combined.iloc[0]["close"] == 11

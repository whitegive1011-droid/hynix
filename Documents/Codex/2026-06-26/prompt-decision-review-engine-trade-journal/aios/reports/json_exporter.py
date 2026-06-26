"""JSON export for the latest signal."""

from __future__ import annotations

import json
from pathlib import Path

from aios.reports.models import PresentationContext, context_to_dict


def write_latest_signal(
    context: PresentationContext,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(context_to_dict(context), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path

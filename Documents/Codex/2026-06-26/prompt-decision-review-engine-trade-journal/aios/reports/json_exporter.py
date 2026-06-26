"""JSON export for the latest signal."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from aios.reports.models import PresentationContext, context_to_dict


def write_latest_signal(
    context: PresentationContext,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _strict_json_safe(context_to_dict(context)),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return path


def _strict_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strict_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_strict_json_safe(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value

"""Rebuild the comparison study independently of older immutable demo payloads."""
import dataclasses
from collections.abc import Mapping
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.compare.research_demo import build_research_demo

OUTPUT = ROOT / "apps/desktop/src/generated/comparison-research-demo.json"


def _json_value(value: object) -> Any:
    """Convert the new comparison payload without depending on older exporters."""

    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping) and not isinstance(value, (str, bytes)):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    return value


def export_bytes() -> bytes:
    payload = _json_value(build_research_demo())
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


if __name__ == "__main__":
    OUTPUT.write_bytes(export_bytes())
    print(f"Wrote {OUTPUT}")

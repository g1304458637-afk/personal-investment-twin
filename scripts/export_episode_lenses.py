"""Export a compact Decision Lens demo without rewriting the showcase payload.

The normal (promoted) location reads its sibling ``showcase-demo.json``.  The
staging copy deliberately requires ``--input`` because the source fixture is
outside the staging area; this prevents an accidental write to the real repo.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "apps/desktop/src/generated/showcase-demo.json"
OUTPUT = ROOT / "apps/desktop/src/generated/episode-lenses-demo.json"


def _load_evaluator():
    """Use a direct file import in staging; promoted code can use package import."""
    module_path = ROOT / "src/lenses/history.py"
    spec = importlib.util.spec_from_file_location("episode_lenses_export_history", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("decision_lens_evaluator_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.evaluate_episode_lenses


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _episode(entry: dict[str, Any]) -> dict[str, Any]:
    episode = entry.get("episode")
    if not isinstance(episode, dict):
        raise ValueError("episode_lens_demo_entry_episode_missing")
    required = ("episode_id", "subject_id", "account_id", "instrument_id")
    if any(_text(episode.get(key)) is None for key in required):
        raise ValueError("episode_lens_demo_entry_identity_missing")
    return episode


def _matching_chart(charts: list[Any], entry: dict[str, Any]) -> dict[str, Any]:
    episode = _episode(entry)
    matched: list[dict[str, Any]] = []
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        market = chart.get("market")
        nested = chart.get("position_episode_demo")
        if not isinstance(market, dict) or not isinstance(nested, dict):
            continue
        if market.get("instrument_id") != episode["instrument_id"]:
            continue
        candidates = nested.get("entries")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if isinstance(candidate, dict) and isinstance(candidate.get("episode"), dict):
                current = candidate["episode"]
                if (current.get("episode_id"), current.get("subject_id"), current.get("account_id"), current.get("instrument_id")) == (
                    episode["episode_id"], episode["subject_id"], episode["account_id"], episode["instrument_id"]):
                    matched.append(chart)
    if len(matched) != 1:
        raise ValueError("episode_lens_demo_chart_join_not_unique")
    return matched[0]


def _market_frame(chart: dict[str, Any], instrument_id: str) -> pd.DataFrame:
    market = chart.get("market")
    if not isinstance(market, dict) or not isinstance(market.get("bars"), list):
        raise ValueError("episode_lens_demo_chart_bars_missing")
    basis = _text(market.get("price_basis")) or "demo_daily_close"
    source = _text(market.get("source_url")) or "demo_showcase"
    version = _text(market.get("source_version")) or "1"
    rows = [dict(date=item.get("date"), instrument=instrument_id, close=item.get("close"),
                 price_type=basis, data_source=source, data_version=version, is_synthetic=True)
            for item in market["bars"] if isinstance(item, dict)]
    return pd.DataFrame(rows)


def _canonical_demo_executions(entry: dict[str, Any]) -> pd.DataFrame:
    """The showcase is a demo fixture, so its declared calendar date is absent.

    This is the sole intentional fallback: derive a date from the recorded
    decision timestamp, label the report accordingly, and never use it in the
    production evaluator path.
    """
    rows = []
    for decision in entry.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        occurred = decision.get("occurred_at")
        try:
            market_date = pd.Timestamp(occurred).normalize().date().isoformat()
        except (TypeError, ValueError):
            market_date = None
        rows.append(dict(execution_id=decision.get("execution_id"), market_date=market_date,
                         side=decision.get("side"), quantity=decision.get("executed_quantity"),
                         price=decision.get("execution_price")))
    return pd.DataFrame(rows)


def build_export(source: dict[str, Any]) -> dict[str, Any]:
    demo = source.get("position_episode_demo")
    charts = source.get("charts")
    if not isinstance(demo, dict) or not isinstance(demo.get("entries"), list) or not isinstance(charts, list):
        raise ValueError("episode_lens_demo_source_missing")
    evaluate = _load_evaluator()
    reports = []
    for entry in demo["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("episode_lens_demo_entry_invalid")
        episode = _episode(entry)
        chart = _matching_chart(charts, entry)
        report = evaluate(entry, _market_frame(chart, episode["instrument_id"]), _canonical_demo_executions(entry))
        report["limitations"] = [*report["limitations"], "演示导出缺少规范交易所市场日期，因此仅在此演示文件中以操作时间日期代替；生产核对必须使用规范成交记录的市场日期。"]
        reports.append(report)
    return {"reports": reports}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=SHOWCASE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not args.input.exists():
        raise SystemExit("showcase_demo_input_missing; staging requires --input PATH")
    source = json.loads(args.input.read_text(encoding="utf-8"))
    payload = build_export(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

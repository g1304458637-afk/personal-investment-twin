"""Export the deterministic strategy-comparison demo for the desktop.

For every showcase episode the same T1 v1 rules are replayed on that
instrument's own synthetic OHLC history (from the shipped showcase chart
bars) and compared with the recorded executions.  The demo derives the
episode market date from the recorded decision timestamp — the same declared
fallback as the Lens demo export; production runtime must use canonical
exchange calendar dates.  Output: apps/desktop/src/generated/strategy-comparison-demo.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategy.compare import SCHEMA_VERSION, NO_VERDICT_NOTE, compare_episode, compare_portfolio  # noqa: E402
from src.strategy.strategies.t1 import build_t1_spec  # noqa: E402

SHOWCASE = ROOT / "apps/desktop/src/generated/showcase-demo.json"
STRATEGY_RESULT = ROOT / "data/sample/strategy_universe/t1_v1_result.json"
OUTPUT = ROOT / "apps/desktop/src/generated/strategy-comparison-demo.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _day(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def main() -> int:
    source = _load(SHOWCASE)
    strategy_result = _load(STRATEGY_RESULT)
    spec = build_t1_spec()
    demo = source["position_episode_demo"]
    charts = source["charts"]

    reports = []
    user_realized_total = 0.0
    user_episode_count = 0
    for entry in demo["entries"]:
        episode = entry["episode"]
        instrument = episode["instrument_id"]
        matched = [chart for chart in charts
                   if isinstance(chart, dict) and isinstance(chart.get("market"), dict)
                   and chart["market"].get("instrument_id") == instrument
                   and isinstance(chart.get("position_episode_demo"), dict)]
        matched = [chart for chart in matched
                   if any(candidate.get("episode", {}).get("episode_id") == episode["episode_id"]
                          for candidate in chart["position_episode_demo"].get("entries", []))]
        if len(matched) != 1:
            raise SystemExit(f"comparison_chart_join_not_unique: {episode['episode_id']}")
        bars = [{"date": bar["date"], "open": bar["open"], "high": bar["high"],
                 "low": bar["low"], "close": bar["close"]}
                for bar in matched[0]["market"]["bars"] if isinstance(bar, dict)]
        executions = [{
            "execution_id": decision.get("execution_id"),
            "day": _day(decision["occurred_at"]).isoformat(),
            "side": decision.get("side"),
            "quantity": decision.get("executed_quantity"),
            "price": decision.get("execution_price"),
            "fee": decision.get("fees"),
        } for decision in entry["decisions"] if isinstance(decision, dict)]
        closed_at = episode.get("closed_at")
        report = compare_episode(
            spec, bars, instrument=instrument, is_synthetic=True,
            executions=executions, episode_id=episode["episode_id"],
            window_start=_day(episode["opened_at"]),
            window_end=_day(closed_at) if closed_at else None,
        )
        outcome = entry["outcome_story"]["episode_outcome"]["actual_result"]
        report["recorded_episode_result"] = {
            "pnl": outcome.get("pnl"),
            "result_kind": outcome.get("result_kind"),
            "result_sign": outcome.get("result_sign"),
            "source_kind": outcome.get("source", {}).get("source_kind"),
        }
        report["limitations"] = [*report["limitations"],
                                 "演示导出缺少规范交易所市场日期，以记录时间日期代替；生产运行时必须使用规范成交的交易所日历日期。"]
        reports.append(report)
        if outcome.get("result_kind") == "realized" and isinstance(outcome.get("pnl"), (int, float)):
            user_realized_total += float(outcome["pnl"])
            user_episode_count += 1

    portfolio = compare_portfolio(
        {
            "scope": "SYN_STUDY_SHOWCASE",
            "realized_episode_count": user_episode_count,
            "realized_pnl_total": user_realized_total,
            "note": "示例账户各 Episode 已实现结果合计（确定性导出）。",
        },
        strategy_result,
        note="示例账户与策略账户并列展示；两者资金与标的池不同，不构成同口径比较。",
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_from": "showcase-demo.json + t1_v1_result.json",
        "reports": reports,
        "portfolio": portfolio,
        "limitations": [
            "示例数据为合成行情与合成成交，仅用于教学演示，不代表真实市场业绩。",
            NO_VERDICT_NOTE,
        ],
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False,
                                 allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "reports": len(reports),
                      "user_realized_total": user_realized_total}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

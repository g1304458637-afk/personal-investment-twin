"""Run the T1 v1 strategy simulation over the synthetic universe fixtures.

Deterministic end to end.  Writes the full journal JSON next to the fixtures
and prints a compact summary.  The output never touches user account data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))

from src.strategy.data import load_simulation_data  # noqa: E402
from src.strategy.engine import run_simulation  # noqa: E402
from src.strategy.report import result_to_dict  # noqa: E402
from src.strategy.strategies.dual_ma import build_dual_ma_spec  # noqa: E402
from src.strategy.strategies.rsi_mr import build_rsi_mr_spec  # noqa: E402
from src.strategy.strategies.turtle import build_turtle_spec  # noqa: E402
from src.strategy.strategies.t1 import build_t1_spec  # noqa: E402


def _desktop_payload(payload: dict, data) -> dict:
    """Trimmed artifact for the desktop demo: no per-day event journal.

    The full journal (selection reasons, signals, daily events, holdings)
    stays in the data-directory result file; the desktop artifact keeps the
    spec, summary, daily ledger, and the complete order/fill path.
    """
    bars = [
        {"instrument": instrument, "date": day.isoformat(),
         "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close}
        for instrument in sorted(data.series)
        for day, bar in zip(data.series[instrument].dates, data.series[instrument].bars)
    ]
    return {
        "schema_version": payload["schema_version"],
        "strategy": payload["strategy"],
        "data_fingerprint": payload["data_fingerprint"],
        "summary": payload["summary"],
        "bars": bars,
        "equity": [
            {"date": day["date"], "cash": day["cash"], "equity": day["equity"],
             "invested_fraction": day["invested_fraction"],
             "drawdown_from_peak": day["drawdown_from_peak"]}
            for day in payload["days"]
        ],
        "orders": payload["orders"],
        "fills": payload["fills"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/sample/strategy_universe")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--desktop-output", type=Path,
                        default=ROOT / "apps/desktop/src/generated/strategy-simulation-demo.json")
    args = parser.parse_args()
    output = args.output or (args.data_dir / "t1_v1_result.json")

    data = load_simulation_data(args.data_dir)
    # One full run per registered strategy: the canonical artifact (T1) plus
    # lazily-loaded desktop files for the other strategies.
    strategies = [build_t1_spec(), build_dual_ma_spec(), build_rsi_mr_spec(), build_turtle_spec()]
    payloads: dict[str, dict] = {}
    for spec in strategies:
        result = run_simulation(spec, data)
        second = result_to_dict(run_simulation(spec, data))
        if second != result_to_dict(result):
            raise SystemExit("simulation_is_not_deterministic")
        payload = result_to_dict(result)
        payloads[spec.strategy_id] = payload
        if spec.strategy_id != "toujing_t1_breakout_trend":
            slug = {"toujing_dual_ma": "dual-ma", "toujing_rsi_mean_reversion": "rsi-mean-reversion",
                    "toujing_turtle_s2_long": "turtle"}.get(spec.strategy_id, spec.strategy_id)
            (args.data_dir / f"{slug}_result.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
            desktop_path = args.desktop_output.parent / f"strategy-simulation-{slug}.json"
            desktop_path.write_text(json.dumps(_desktop_payload(payload, data), ensure_ascii=False,
                                               indent=1, allow_nan=False) + "\n", encoding="utf-8")
    result = run_simulation(strategies[0], data)
    payload = payloads[strategies[0].strategy_id]
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False,
                                 allow_nan=False) + "\n", encoding="utf-8")
    desktop = _desktop_payload(payload, data)
    args.desktop_output.parent.mkdir(parents=True, exist_ok=True)
    args.desktop_output.write_text(json.dumps(desktop, ensure_ascii=False, indent=1,
                                              sort_keys=False, allow_nan=False) + "\n",
                                   encoding="utf-8")
    summary = payload["summary"]
    print(json.dumps({
        "output": str(output), "desktop_output": str(args.desktop_output),
        "strategies": {key: value["summary"]["final_equity"] for key, value in payloads.items()},
        "data_fingerprint": payload["data_fingerprint"],
        "strategy": f"{result.spec.strategy_id}@{result.spec.version}",
        "final_equity": summary["final_equity"],
        "total_return": summary["total_return"],
        "max_drawdown": summary["max_drawdown"],
        "orders": summary["order_count"], "fills": summary["fill_count"],
        "rejected": summary["rejected_order_count"],
        "cancelled": summary["cancelled_order_count"],
        "total_fees": summary["total_fees"],
        "round_trips": summary["round_trip_count"], "win_rate": summary["win_rate"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Golden corpus for the lifecycle state-fold refactor.

Builds position-episode lifecycles from every available execution fixture with
the CURRENT code and writes canonical JSON to a directory. After a refactor,
re-run with --compare to byte-diff against the stored goldens.

Usage:
  python scripts/golden_lifecycle.py write /tmp/lifecycle-golden
  python scripts/golden_lifecycle.py compare /tmp/lifecycle-golden
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.csv_importer import load_normalized_csv
from src.episodes.position_episode import build_position_episode_lifecycle

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Every execution fixture with columns the loader accepts, plus the price
# fixtures that pair with them.
CASES = {
    "behavior": (
        "data/sample/synthetic_behavior_executions.csv",
        "data/sample/synthetic_behavior_prices.csv",
    ),
    "large": None,  # generated deterministically below
}


def _large_case(tmp_dir: Path) -> tuple[Path, Path]:
    """~500 fills across 3 instruments: buys, full exits, partial exits, re-entries."""
    import math

    exec_rows: list[str] = []
    price_rows: list[str] = []
    symbols = ["SYN_ALPHA", "SYN_BETA", "SYN_GAMMA"]
    dates = pd.bdate_range("2024-01-01", periods=520)
    quantities = {"SYN_ALPHA": 0.0, "SYN_BETA": 0.0, "SYN_GAMMA": 0.0}
    seq = 0
    for day_index, day in enumerate(dates):
        for symbol in symbols:
            close = 10.0 + 3.0 * math.sin(day_index / 17.0) + len(symbol) * 0.1
            price_rows.append(f"{day.date()},{symbol},{close:.4f},synthetic,large_case,v1,true")
        symbol = symbols[day_index % 3]
        close = 10.0 + 3.0 * math.sin(day_index / 17.0) + len(symbol) * 0.1
        action = day_index % 7
        held = quantities[symbol]
        if action in (0, 1, 2) or held == 0.0:
            size = 100 + (day_index % 5) * 20
            seq += 1
            exec_rows.append(f"{day} 10:{day_index % 60:02d}:00,{symbol},BUY,{size},{close:.4f},1.0,CNY,X-{seq}")
            quantities[symbol] = held + size
        elif action in (3, 4) and held > 100:
            # partial exit
            size = held // 2 if held >= 200 else 50
            seq += 1
            exec_rows.append(f"{day} 13:{day_index % 60:02d}:00,{symbol},SELL,{size},{close:.4f},1.0,CNY,X-{seq}")
            quantities[symbol] = held - size
        elif action in (5, 6):
            seq += 1
            exec_rows.append(f"{day} 14:{day_index % 60:02d}:00,{symbol},SELL,{held:.0f},{close:.4f},1.0,CNY,X-{seq}")
            quantities[symbol] = 0.0
    exec_path = tmp_dir / "large_executions.csv"
    price_path = tmp_dir / "large_prices.csv"
    exec_path.write_text("execution_time,symbol,side,quantity,price,fee,currency,execution_id\n" + "\n".join(exec_rows) + "\n")
    price_path.write_text("date,instrument,close,price_type,data_source,data_version,is_synthetic\n" + "\n".join(price_rows) + "\n")
    return exec_path, price_path


def _prices_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def build(case: str, tmp_dir: Path) -> dict:
    paths = CASES[case]
    if paths is None:
        paths = _large_case(tmp_dir)
    exec_path, price_path = paths
    executions = load_normalized_csv(PROJECT_ROOT / exec_path)
    market = _prices_frame(PROJECT_ROOT / price_path)
    lifecycle = build_position_episode_lifecycle(
        executions,
        market,
        subject_id="golden:synthetic-behavior",
        account_id="golden-acc",
        as_of=max(pd.Timestamp(pd.read_csv(PROJECT_ROOT / price_path)["date"].max()).normalize(),
                  pd.Timestamp(executions["event_time"].max()).normalize()) + pd.Timedelta(days=1),
        init_cash=100_000.0,
        data_tier="synthetic",
        calculation_code_version="golden-v1",
    )
    payload = {
        "episodes": [item.as_dict() if hasattr(item, "as_dict") else repr(item) for item in lifecycle.episodes],
        "states": [item.__dict__ if hasattr(item, "__dict__") else str(item) for item in lifecycle.states],
        "snapshots": [repr(item) for item in lifecycle.snapshots],
        "decisions": [repr(item) for item in lifecycle.decisions],
    }
    return json.loads(json.dumps(payload, default=str, sort_keys=True))


def main() -> int:
    mode, directory = sys.argv[1], Path(sys.argv[2])
    directory.mkdir(parents=True, exist_ok=True)
    failures = 0
    for case in CASES:
        started = pd.Timestamp.now()
        payload = build(case, directory)
        dump = directory / f"{case}.json"
        if mode == "write":
            dump.write_text(json.dumps(payload, sort_keys=True))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        print(f"  build time: {(pd.Timestamp.now() - started).total_seconds():.2f}s")
        golden = directory / f"{case}.sha"
        if mode == "write":
            golden.write_text(digest)
            print(f"{case}: {digest}")
        else:
            expected = golden.read_text().strip()
            status = "MATCH" if expected == digest else "MISMATCH"
            if expected != digest:
                failures += 1
            print(f"{case}: {digest} {status}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

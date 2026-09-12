"""Export the built-in strategy library (rule tables + params only) for the
desktop reference section.  Tiny file: no journals, no bars."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.strategy.strategies.dual_ma import build_dual_ma_spec  # noqa: E402
from src.strategy.strategies.rsi_mr import build_rsi_mr_spec  # noqa: E402
from src.strategy.strategies.t1 import build_t1_spec  # noqa: E402
from src.strategy.strategies.turtle import build_turtle_spec  # noqa: E402

OUTPUT = ROOT / "apps/desktop/src/generated/strategy-library.json"


def main() -> int:
    entries = []
    for spec in (build_t1_spec(), build_dual_ma_spec(), build_rsi_mr_spec(), build_turtle_spec()):
        entries.append({
            "strategy_id": spec.strategy_id,
            "version": spec.version,
            "title": spec.title,
            "description": spec.description,
            "params": spec.params,
            "rule_table": [dict(rule) for rule in spec.rule_table],
        })
    payload = {"schema_version": "strategy_library.v1", "strategies": entries}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "strategies": len(entries)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

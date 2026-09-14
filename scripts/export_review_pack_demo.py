"""Export the deterministic review_pack.v1 demo for the desktop.

The script mints a fully synthetic account (no real broker, no real user),
commits it through the canonical import path (generic CSV preview + repository
commits, synthetic_demo market facts), tags a few episodes through the
existing ReviewStore read-model, then exports ``build_review_pack`` output to
apps/desktop/src/generated/review-pack-demo.json.

Demo shape (all deterministic, rerunnable byte-for-byte):
- 13 closed episodes (win/loss mixed) exiting across many months;
- one 3-consecutive-loss streak followed by a denser 10-trading-day window
  with re-buys of the losing instruments (tilt observation);
- several open positions that the closed-only sections must ignore;
- 5 user-authored tags distributed over the closed episodes, exercising both
  the sufficient and the insufficient win-rate branches.

The demo data is synthetic and carries no monetary claims; the script appends
an explicit synthetic-data limitation to every section of the exported pack.
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.review_store import ReviewStore  # noqa: E402
from src.ingestion.generic_csv import GenericCsvImportConfig, preview_generic_csv  # noqa: E402
from src.market_data.models import HistoricalPriceFact  # noqa: E402
from src.persistence import LocalRepository  # noqa: E402
from src.review_pack import build_review_pack  # noqa: E402

OUTPUT = ROOT / "apps" / "desktop" / "src" / "generated" / "review-pack-demo.json"
SUBJECT = "demo_subject"
ACCOUNT = "review_demo"
INITIAL_CASH = 200_000.0
BUY_TIME, SELL_TIME = "09:31:00", "14:50:00"

SYNTHETIC_DEMO_NOTE = (
    "演示数据为合成行情与合成成交（synthetic_demo），仅用于前端演示，"
    "不代表任何真实市场、真实账户或真实业绩。"
)

EXEC_HEADER = ["symbol", "market", "security_type", "currency", "event_time", "side",
               "quantity", "price", "fee", "source_execution_id", "source_order_id"]

PRICE_SERIES = {  # symbol -> (base, amplitude, period, daily drift)
    "RVA": (20.0, 2.0, 40.0, 0.010),
    "RVB": (50.0, 3.0, 60.0, -0.020),
    "RVC": (10.0, 0.8, 21.0, 0.008),
    "RVD": (30.0, 1.2, 55.0, 0.012),
    "RVE": (8.0, 0.5, 14.0, -0.003),
}


def demo_days() -> list[str]:
    return [day.date().isoformat() for day in pd.bdate_range("2025-01-02", "2025-11-28")]


def demo_closes() -> dict[str, list[tuple[str, float]]]:
    days = demo_days()
    closes: dict[str, list[tuple[str, float]]] = {}
    for symbol, (base, amplitude, period, drift) in PRICE_SERIES.items():
        rows = []
        for index, day in enumerate(days):
            close = base + amplitude * math.sin(index / period * 2.0 * math.pi) + drift * index
            rows.append((day, round(max(close, 0.5), 2)))
        closes[symbol] = rows
    return closes


def _exec(symbol: str, day: str, side: str, quantity: float, price: float, tag: str) -> list:
    time = BUY_TIME if side == "BUY" else SELL_TIME
    return [symbol, "XSHG", "equity", "CNY", f"{day} {time}", side, quantity, price, 1.0,
            f"{tag}-E", f"{tag}-O"]


def demo_executions() -> list[list]:
    days = demo_days()

    def day(index: int) -> str:
        return days[index]

    plan = [  # (symbol, buy_idx, sell_idx, qty, buy_px, sell_px, tag); sell_idx None = open
        ("RVA", 2, 14, 500, 20.0, 21.5, "E1"),      # win
        ("RVB", 8, 30, 200, 50.0, 47.0, "E2"),      # loss
        ("RVC", 15, 40, 1000, 10.0, 11.2, "E3"),    # partial exit at 25, final at 40 -> win
        ("RVD", 20, 48, 300, 30.0, 32.0, "E4"),     # win
        ("RVE", 35, 42, 2000, 8.0, 7.6, "E5"),      # loss
        ("RVA", 55, 70, 400, 20.5, 21.8, "E6"),     # win
        ("RVB", 90, 100, 150, 49.0, 46.5, "E7"),    # loss (streak 1)
        ("RVC", 95, 104, 800, 10.5, 9.8, "E8"),     # loss (streak 2)
        ("RVE", 98, 108, 1500, 8.2, 7.5, "E9"),     # loss (streak 3 -> tilt trigger)
        ("RVA", 110, 114, 600, 21.0, 21.6, "W1"),   # tilt-window trade, later closed
        ("RVB", 112, 116, 300, 48.0, 48.8, "W2"),   # tilt-window re-buy of a loss instrument
        ("RVC", 115, None, 900, 9.9, None, "W3"),   # stays open
        ("RVE", 117, None, 1200, 7.4, None, "W4"),  # stays open
        ("RVD", 125, 150, 350, 31.0, 33.0, "E10"),  # win
        ("RVA", 160, 190, 600, 22.0, 23.5, "E11"),  # win
        ("RVE", 195, None, 1000, 7.0, None, "E12"), # stays open
    ]
    rows: list[list] = []
    for symbol, buy_idx, sell_idx, quantity, buy_px, sell_px, tag in plan:
        rows.append(_exec(symbol, day(buy_idx), "BUY", quantity, buy_px, f"{tag}B"))
        if sell_idx is None:
            continue
        if tag == "E3":  # add_position then two exits: half at day 25, half at the end
            rows.append(_exec(symbol, day(25), "SELL", quantity / 2, 10.8, f"{tag}S1"))
        rows.append(_exec(symbol, day(sell_idx), "SELL", quantity / 2 if tag == "E3" else quantity,
                          sell_px, f"{tag}S"))
    return rows


def commit_demo_account(repo: LocalRepository) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXEC_HEADER)
    writer.writerows(demo_executions())
    preview = preview_generic_csv(buffer.getvalue().encode("utf-8"),
                                  config=GenericCsvImportConfig(SUBJECT, ACCOUNT, "Asia/Shanghai"))
    bad = [(row.status, row.issues) for row in preview.rows if row.status != "new_execution"]
    if bad:
        raise SystemExit(f"demo fixture rejected by canonical import: {bad}")
    items = [row.candidate for row in preview.rows if row.candidate]
    repo.commit_trade_import(subject_id=SUBJECT, account_id=ACCOUNT, display_name="复盘演示账户",
        initial_cash=INITIAL_CASH, batch_id=preview.batch.batch_id, file_sha256=preview.batch.file_sha256,
        filename="review_pack_demo_executions_v1.csv", imported_at="2026-01-01T00:00:00Z",
        summary=preview.summary.as_dict(), executions=items)
    facts = []
    closes = demo_closes()
    for item in items:
        symbol = item.instrument.local_symbol
        for day, close in closes[symbol]:
            facts.append(HistoricalPriceFact(
                observation_id=f"obs-demo-{symbol}-{day}", instrument=item.instrument,
                date=date.fromisoformat(day), close=close, price_type="synthetic", currency="CNY",
                source_id="review_pack_demo", source_tier="synthetic_demo", source_version="v1",
                imported_at="2026-01-01T00:01:00Z", source_file_sha256="demo-sha",
                source_row_identity=f"{symbol}-{day}", source_label="review_pack_demo"))
    repo.commit_market_import(subject_id=SUBJECT, account_id=ACCOUNT,
        batch_id="batch-review-pack-demo", file_sha256="demo-sha", filename="review_pack_demo_market_v1.csv",
        imported_at="2026-01-01T00:01:00Z", summary={"new_observations": len(facts)}, facts=facts)


def apply_demo_tags(repo: LocalRepository, pack: dict) -> None:
    """Tag demo episodes identified by (symbol, realized pnl); both unique."""
    symbol_by_instrument = {}
    for item in repo.executions(SUBJECT, ACCOUNT):
        symbol_by_instrument[item.instrument.instrument_id] = item.instrument.local_symbol
    episode_id_by_key = {}
    for row in pack["exit_quality"]["episodes"]:
        symbol = symbol_by_instrument.get(row["instrument"], row["instrument"])
        episode_id_by_key[(symbol, round(row["realized_pnl"], 6))] = row["episode_id"]

    store = ReviewStore(repo.connection)
    tags_by_symbol_pnl = {
        ("RVA", 748.0): ["按计划执行", "提前止盈"],
        ("RVB", -602.0): ["按计划执行", "止损太晚"],
        ("RVC", 997.0): ["提前止盈"],
        ("RVD", 598.0): ["按计划执行"],
        ("RVE", -802.0): ["越跌越买"],
        ("RVA", 518.0): ["按计划执行", "提前止盈"],
        ("RVB", -377.0): ["止损太晚"],
        ("RVC", -562.0): ["止损太晚"],
        ("RVE", -1052.0): ["越跌越买"],
        ("RVD", 698.0): ["按计划执行"],
        ("RVA", 898.0): ["按计划执行"],
        ("RVB", 238.0): ["亏损后回买"],
    }
    for (symbol, pnl), tags in tags_by_symbol_pnl.items():
        episode_id = episode_id_by_key.get((symbol, pnl))
        if episode_id is None:
            raise SystemExit(f"demo episode not found for tag: {symbol} {pnl}")
        store.set_tags(subject_id=SUBJECT, account_id=ACCOUNT, episode_id=episode_id, tags=tags)


def add_demo_limitations(pack: dict) -> None:
    for section in ("exit_quality", "calendar", "behavior_flags", "playbook"):
        pack[section]["limitations"].append(SYNTHETIC_DEMO_NOTE)
    for row in pack["exit_quality"]["episodes"]:
        row["limitations"].append(SYNTHETIC_DEMO_NOTE)
    for row in pack["behavior_flags"]["tilt"]:
        row["limitations"].append(SYNTHETIC_DEMO_NOTE)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="review_pack_demo_") as tmp:
        repo = LocalRepository(Path(tmp) / "demo.sqlite3")
        try:
            commit_demo_account(repo)
            pack = build_review_pack(repo, SUBJECT, ACCOUNT)
            apply_demo_tags(repo, pack)
            pack = build_review_pack(repo, SUBJECT, ACCOUNT)
        finally:
            repo.close()
    add_demo_limitations(pack)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1, allow_nan=False) + "\n",
                      encoding="utf-8")
    summary = {
        "output": str(OUTPUT.relative_to(ROOT)),
        "as_of": pack["as_of"],
        "coverage": pack["coverage"],
        "closed_episodes": len(pack["exit_quality"]["episodes"]),
        "calendar_months": len(pack["calendar"]["months"]),
        "calendar_days": len(pack["calendar"]["days"]),
        "tilt_observations": len(pack["behavior_flags"]["tilt"]),
        "playbook_tags": len(pack["playbook"]["tags"]),
        "untagged_episode_count": pack["playbook"]["untagged_episode_count"],
        "tagged_episodes": len(pack["episode_tags"]),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

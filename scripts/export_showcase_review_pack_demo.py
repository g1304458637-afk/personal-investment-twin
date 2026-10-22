"""Export ReviewPack for the same fictional account as showcase-demo.json.

Canonical repository facts are constructed from ``showcase.showcase_inputs``.
The public display episode IDs are mapped from qualified replay IDs only
after showcase_runtime verifies identical execution refs on both sides.
The older, independent 13-episode review-pack-demo fixture remains untouched.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.canonical_execution import canonical_execution, execution_time, fee_fact  # noqa: E402
from src.demo import showcase  # noqa: E402
from src.demo.showcase_runtime import _episode_mapping, _qualified_inputs  # noqa: E402
from src.market_data.models import HistoricalPriceFact  # noqa: E402
from src.persistence import LocalRepository  # noqa: E402
from src.review_pack import build_review_pack  # noqa: E402

OUTPUT = ROOT / "apps/desktop/src/generated/showcase-review-pack-demo.json"
SYNTHETIC_NOTE = (
    "此复盘包与“我的年度投资 · 示例”共用合成成交和收盘行情；"
    "不代表真实账户、真实市场或真实业绩。"
)


def _commit_showcase(repo: LocalRepository) -> None:
    frame, prices, instruments = _qualified_inputs(showcase.SUBJECT_ID)
    source_sha = showcase.source_fingerprint()
    executions = []
    for row in frame.itertuples(index=False):
        symbol = next(symbol for symbol, item in instruments.items()
                      if item.instrument_id == row.symbol)
        executions.append(canonical_execution(
            subject_id=showcase.SUBJECT_ID, account_id=showcase.ACCOUNT_ID,
            instrument=instruments[symbol],
            event_time=execution_time(row.event_time, precision="minute",
                                      source_timezone="Asia/Shanghai"),
            side=row.side, executed_quantity=row.executed_quantity,
            executed_price=row.executed_price, fee=fee_fact(row.fee, currency="CNY"),
            source=showcase.VERSION, source_record_ref=row.execution_id,
            execution_sequence=int(row.execution_sequence),
            sequence_source="showcase_source_order", execution_id=row.execution_id,
            source_execution_id=row.execution_id, source_order_id=row.order_id,
        ))
    repo.commit_trade_import(
        subject_id=showcase.SUBJECT_ID, account_id=showcase.ACCOUNT_ID,
        display_name="我的年度投资 · 示例", initial_cash=showcase.INITIAL_CASH,
        batch_id="showcase-review-pack-executions-v1", file_sha256=source_sha,
        filename="showcase.showcase_inputs:executions", imported_at="2026-01-01T00:00:00Z",
        summary={"new_executions": len(executions)}, executions=executions,
    )
    observations = []
    for row in prices.itertuples(index=False):
        if row.instrument not in {item.instrument_id for item in instruments.values()}:
            continue  # Declared benchmark-only series, never a held security.
        instrument = next(item for item in instruments.values()
                          if item.instrument_id == row.instrument)
        day = row.date.date() if hasattr(row.date, "date") else date.fromisoformat(str(row.date))
        observations.append(HistoricalPriceFact(
            observation_id=f"showcase:{row.instrument}:{day.isoformat()}",
            instrument=instrument, date=day, close=float(row.close),
            price_type="synthetic", currency="CNY", source_id=showcase.VERSION,
            source_tier="synthetic_demo", source_version="1",
            imported_at="2026-01-01T00:01:00Z", source_file_sha256=source_sha,
            source_row_identity=f"{row.instrument}:{day.isoformat()}",
            source_label="showcase.showcase_inputs",
        ))
    repo.commit_market_import(
        subject_id=showcase.SUBJECT_ID, account_id=showcase.ACCOUNT_ID,
        batch_id="showcase-review-pack-prices-v1", file_sha256=source_sha,
        filename="showcase.showcase_inputs:prices", imported_at="2026-01-01T00:01:00Z",
        summary={"new_observations": len(observations)}, facts=observations,
    )


def build_export() -> dict:
    with tempfile.TemporaryDirectory(prefix="showcase_review_pack_") as directory:
        repo = LocalRepository(Path(directory) / "account.sqlite3")
        try:
            _commit_showcase(repo)
            pack = build_review_pack(repo, showcase.SUBJECT_ID, showcase.ACCOUNT_ID)
        finally:
            repo.close()
    identity, _, _, _ = _episode_mapping(showcase.SUBJECT_ID)
    mapped = []
    for row in pack["exit_quality"]["episodes"]:
        canonical_id = row["episode_id"]
        match = identity.get(canonical_id)
        if match is None or match["canonical_episode_id"] != canonical_id:
            raise ValueError(f"review_pack_episode_identity_unverified: {canonical_id}")
        if row["instrument"] != match["canonical_instrument_id"]:
            raise ValueError(f"review_pack_instrument_identity_unverified: {canonical_id}")
        row["episode_id"] = match["display_episode_id"]
        row["instrument"] = match["display_instrument_id"]
        row["limitations"].append(SYNTHETIC_NOTE)
        mapped.append({
            "display_episode_id": match["display_episode_id"],
            "canonical_episode_id": canonical_id,
            "display_instrument_id": match["display_instrument_id"],
            "canonical_instrument_id": match["canonical_instrument_id"],
        })
    if len(mapped) != len({item["display_episode_id"] for item in mapped}):
        raise ValueError("review_pack_episode_mapping_not_one_to_one")
    for section in ("exit_quality", "calendar", "behavior_flags", "playbook"):
        pack[section]["limitations"].append(SYNTHETIC_NOTE)
    pack["data_tier"] = "synthetic"
    pack["source_version"] = showcase.VERSION
    pack["source_fingerprint"] = showcase.source_fingerprint()
    pack["episode_identity_mapping"] = sorted(mapped, key=lambda item: item["display_episode_id"])
    return pack


def export_bytes() -> bytes:
    return (json.dumps(build_export(), ensure_ascii=False, indent=1,
                       sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(export_bytes())
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

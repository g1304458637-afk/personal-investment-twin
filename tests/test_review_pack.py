"""review_pack.v1 builder tests over a canonical LocalRepository.

The fixtures go through the canonical import path (generic CSV preview +
repository commits), so every number asserted here is produced end to end by
the same deterministic pipeline the product runtime uses.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import date

import pandas as pd
import pytest

from src.agents.review_store import ReviewStore
from src.ingestion.generic_csv import GenericCsvImportConfig, preview_generic_csv
from src.market_data.models import HistoricalPriceFact
from src.persistence import LocalRepository
from src.review_pack import SCHEMA_VERSION, build_review_pack

SUBJECT = "review-pack-subject"
EXEC_HEADER = ["symbol", "market", "security_type", "currency", "event_time", "side",
               "quantity", "price", "fee", "source_execution_id", "source_order_id"]


def _exec_row(symbol, day, side, quantity, price, fee, tag, time_of_day="09:30:00"):
    return [symbol, "XSHG", "equity", "CNY", f"{day} {time_of_day}", side, quantity, price, fee,
            f"{tag}-E", f"{tag}-O"]


def _commit_trades(repo, subject, account, rows, initial_cash=1_000_000.0):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXEC_HEADER)
    writer.writerows(rows)
    preview = preview_generic_csv(buffer.getvalue().encode("utf-8"),
                                  config=GenericCsvImportConfig(subject, account, "Asia/Shanghai"))
    bad = [(row.status, row.issues) for row in preview.rows if row.status != "new_execution"]
    assert not bad, bad
    items = [row.candidate for row in preview.rows if row.candidate]
    repo.commit_trade_import(subject_id=subject, account_id=account, display_name=account,
        initial_cash=initial_cash, batch_id=preview.batch.batch_id, file_sha256=preview.batch.file_sha256,
        filename="trades.csv", imported_at="2026-01-01T00:00:00Z",
        summary=preview.summary.as_dict(), executions=items)
    return items


def _commit_prices(repo, subject, account, items, closes_by_symbol):
    """Commit synthetic daily closes directly as canonical price facts."""
    facts = []
    for item in items:
        symbol = item.instrument.local_symbol
        for day, close in closes_by_symbol.get(symbol, []):
            facts.append(HistoricalPriceFact(
                observation_id=f"obs-{subject}-{account}-{symbol}-{day}",
                instrument=item.instrument, date=date.fromisoformat(day), close=float(close),
                price_type="synthetic", currency="CNY", source_id="review_pack_test",
                source_tier="synthetic_demo", source_version="v1",
                imported_at="2026-01-01T00:01:00Z", source_file_sha256="test-sha",
                source_row_identity=f"{symbol}-{day}", source_label="review_pack_test"))
    repo.commit_market_import(subject_id=subject, account_id=account,
        batch_id=f"batch-{subject}-{account}", file_sha256="test-sha", filename="prices.csv",
        imported_at="2026-01-01T00:01:00Z", summary={"new_observations": len(facts)}, facts=facts)


def _symbol_closes(symbol, days, base):
    return [(day, round(base * (1.0 + 0.01 * math.sin(index / 5.0) + 0.001 * index), 2))
            for index, day in enumerate(days)]


def test_exit_quality_exact_mfe_mae_and_derived_fields(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    items = _commit_trades(repo, SUBJECT, "ACC-EX", [
        _exec_row("600000", "2025-01-02", "BUY", 100, 10.0, 1.0, "T1"),
        _exec_row("600000", "2025-01-08", "SELL", 100, 12.0, 1.0, "T2"),
    ])
    _commit_prices(repo, SUBJECT, "ACC-EX", items, {"600000": [
        ("2025-01-02", 10.5), ("2025-01-03", 11.5), ("2025-01-06", 9.5),
        ("2025-01-07", 12.8), ("2025-01-08", 12.0), ("2025-01-09", 11.0), ("2025-01-10", 11.5)]})
    pack = build_review_pack(repo, SUBJECT, "ACC-EX")
    repo.close()

    assert pack["schema_version"] == SCHEMA_VERSION == "review_pack.v1"
    assert pack["as_of"] == "2025-01-10"
    assert pack["coverage"] == {"execution_count": 2, "episode_count": 1,
                                "first_date": "2025-01-02", "last_date": "2025-01-08"}
    rows = pack["exit_quality"]["episodes"]
    assert len(rows) == 1
    row = rows[0]
    # Manual path (documented in src/review_pack/exit_quality.py):
    # 01-02: 100*(10.5-10)-1 = 49; 01-03: 149; 01-06: -51; 01-07: 279; close: 198.
    assert row["realized_pnl"] == pytest.approx(198.0)
    assert row["mfe_amount"] == pytest.approx(279.0)
    assert row["mae_amount"] == pytest.approx(-51.0)
    assert row["facts"] == {"peak_date": "2025-01-07", "trough_date": "2025-01-06", "hold_days": 6}
    assert row["status"] == "closed"
    notional_max = 100 * 12.8  # peak end-of-day position market value
    assert row["mfe_pct"] == pytest.approx(279.0 / notional_max)
    assert row["mae_pct"] == pytest.approx(-51.0 / notional_max)
    assert row["exit_efficiency"] == pytest.approx(198.0 / 279.0)
    assert row["giveback_ratio"] == pytest.approx((279.0 - 198.0) / 279.0)
    assert any("日线收盘价" in item for item in row["limitations"])
    assert any("前向填充" in item for item in row["limitations"])
    month = next(item for item in pack["calendar"]["months"] if item["month"] == "2025-01")
    assert month == {"month": "2025-01", "realized_pnl": pytest.approx(198.0),
                     "closed_count": 1, "win_count": 1}
    assert pack["calendar"]["days"] == [{"date": "2025-01-08", "realized_pnl": pytest.approx(198.0),
                                         "closed_count": 1}]


def test_missing_price_days_are_skipped_never_interpolated(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    items = _commit_trades(repo, SUBJECT, "ACC-GAP", [
        _exec_row("600000", "2025-01-02", "BUY", 100, 10.0, 1.0, "T1"),
        _exec_row("600000", "2025-01-08", "SELL", 100, 12.0, 1.0, "T2"),
    ])
    # No observation on 2025-01-07 anywhere: the day is skipped, never filled,
    # and can therefore never appear as peak or trough.
    _commit_prices(repo, SUBJECT, "ACC-GAP", items, {"600000": [
        ("2025-01-02", 10.5), ("2025-01-03", 11.5), ("2025-01-06", 9.5), ("2025-01-08", 12.0)]})
    pack = build_review_pack(repo, SUBJECT, "ACC-GAP")
    repo.close()
    row = pack["exit_quality"]["episodes"][0]
    assert row["mfe_amount"] == pytest.approx(198.0)  # close-day realized replaces the lost peak
    assert row["facts"]["peak_date"] == "2025-01-08"
    assert row["facts"]["trough_date"] == "2025-01-06"
    assert any("跳过" in item and "前向填充" in item for item in row["limitations"])


def test_incomplete_multi_symbol_panel_degrades_without_guessing(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    items = _commit_trades(repo, SUBJECT, "ACC-PANELGAP", [
        _exec_row("AAA", "2025-01-02", "BUY", 100, 10.0, 1.0, "T1"),
        _exec_row("AAA", "2025-01-08", "SELL", 100, 12.0, 1.0, "T2"),
        _exec_row("BBB", "2025-01-03", "BUY", 100, 20.0, 1.0, "T3"),
        _exec_row("BBB", "2025-01-06", "SELL", 100, 21.0, 1.0, "T4"),
    ])
    _commit_prices(repo, SUBJECT, "ACC-PANELGAP", items, {
        "AAA": [("2025-01-02", 10.5), ("2025-01-03", 10.6), ("2025-01-06", 10.7), ("2025-01-08", 12.0)],
        # BBB misses 2025-01-06: the joint panel is incomplete -> fail closed.
        "BBB": [("2025-01-03", 20.5)],
    })
    pack = build_review_pack(repo, SUBJECT, "ACC-PANELGAP")
    repo.close()
    assert pack["coverage"]["execution_count"] == 4
    assert pack["coverage"]["episode_count"] == 0
    assert pack["exit_quality"]["episodes"] == []
    assert any("生命周期不可用" in item for item in pack["exit_quality"]["limitations"])
    json.dumps(pack, allow_nan=False)


def test_no_market_data_degrades_without_guessing(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    _commit_trades(repo, SUBJECT, "ACC-NOPRICE", [
        _exec_row("600000", "2025-01-02", "BUY", 100, 10.0, 1.0, "T1"),
        _exec_row("600000", "2025-01-08", "SELL", 100, 12.0, 1.0, "T2"),
    ])
    pack = build_review_pack(repo, SUBJECT, "ACC-NOPRICE")
    repo.close()
    assert pack["as_of"] == "2025-01-08"
    assert pack["coverage"] == {"execution_count": 2, "episode_count": 0,
                                "first_date": "2025-01-02", "last_date": "2025-01-08"}
    assert pack["exit_quality"]["episodes"] == []
    assert any("市场数据" in item for item in pack["exit_quality"]["limitations"])
    assert pack["playbook"]["tags"] == []
    assert pack["episode_tags"] == []


def test_empty_account_keeps_schema_with_zero_coverage(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    repo.upsert_account(SUBJECT, "ACC-EMPTY", display_name="empty", initial_cash=1000.0,
                        now="2026-01-01T00:00:00Z")
    repo.connection.commit()
    pack = build_review_pack(repo, SUBJECT, "ACC-EMPTY")
    repo.close()
    assert pack["as_of"] is None
    assert pack["coverage"] == {"execution_count": 0, "episode_count": 0,
                                "first_date": None, "last_date": None}
    assert pack["calendar"]["months"] == []
    json.dumps(pack, allow_nan=False)


def test_unknown_account_fails_closed(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    with pytest.raises(ValueError, match="account not found"):
        build_review_pack(repo, SUBJECT, "GHOST")
    repo.close()


def test_loss_episode_caps_giveback_at_one_and_skips_efficiency(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    items = _commit_trades(repo, SUBJECT, "ACC-LOSS", [
        _exec_row("600000", "2025-01-02", "BUY", 100, 10.0, 1.0, "T1"),
        _exec_row("600000", "2025-01-08", "SELL", 100, 5.0, 1.0, "T2"),
    ])
    _commit_prices(repo, SUBJECT, "ACC-LOSS", items, {"600000": [
        ("2025-01-02", 10.5), ("2025-01-03", 11.5), ("2025-01-06", 9.5),
        ("2025-01-07", 10.2), ("2025-01-08", 5.0)]})
    pack = build_review_pack(repo, SUBJECT, "ACC-LOSS")
    repo.close()
    row = pack["exit_quality"]["episodes"][0]
    assert row["realized_pnl"] == pytest.approx((5.0 - 10.0) * 100 - 2.0)
    assert row["mfe_amount"] == pytest.approx(149.0)  # 100*(11.5-10)-1
    assert row["exit_efficiency"] is None  # realized <= 0, never scored
    assert row["giveback_ratio"] == 1.0  # capped: loss round trip gave back the whole peak
    month = pack["calendar"]["months"][0]
    assert month["win_count"] == 0


def _tilt_fixture(tmp_path):
    """>=20 executions, 3 consecutive losing closes, a denser 10-day window."""
    days = [day.date().isoformat() for day in pd.bdate_range("2024-11-01", "2025-03-31")]

    def day(index: int) -> str:
        return days[index]

    rows = []
    tag = 0
    # Five filler episodes on T4, all closing before the losing streak.
    for buy_day, sell_day, buy_price, sell_price in [
        (day(36), day(40), 30.0, 31.0), (day(44), day(48), 30.0, 29.0),
        (day(52), day(56), 30.0, 31.5), (day(57), day(58), 30.0, 30.4),
        (day(59), day(59), 30.0, 30.8),
    ]:
        tag += 1
        rows.append(_exec_row("T4", buy_day, "BUY", 300, buy_price, 1.0, f"F{tag}B", "09:31:00"))
        rows.append(_exec_row("T4", sell_day, "SELL", 300, sell_price, 1.0, f"F{tag}S", "14:50:00"))
    # Three consecutive losing closes -> trigger.
    for index, (symbol, buy_day, sell_day, buy_price, sell_price) in enumerate([
        ("T1", day(60), day(61), 10.0, 9.0), ("T2", day(62), day(63), 20.0, 19.0),
        ("T3", day(64), day(65), 5.0, 4.5),
    ]):
        rows.append(_exec_row(symbol, buy_day, "BUY", 1000, buy_price, 1.0, f"L{index}B"))
        rows.append(_exec_row(symbol, sell_day, "SELL", 1000, sell_price, 1.0, f"L{index}S"))
    # The observed window: denser trading incl. re-buys of the losing instruments.
    rows.append(_exec_row("T1", day(67), "BUY", 1200, 9.5, 1.0, "W1B"))
    rows.append(_exec_row("T1", day(69), "SELL", 1200, 9.6, 1.0, "W1S"))
    rows.append(_exec_row("T2", day(71), "BUY", 500, 19.0, 1.0, "W2B"))
    rows.append(_exec_row("T3", day(73), "BUY", 2000, 4.6, 1.0, "W3B"))
    rows.append(_exec_row("T4", day(75), "BUY", 800, 30.0, 1.0, "W4B"))

    repo = LocalRepository(tmp_path / "db.sqlite3")
    items = _commit_trades(repo, SUBJECT, "ACC-TILT", rows)
    closes = {symbol: _symbol_closes(symbol, days, base)
              for symbol, base in [("T1", 10.0), ("T2", 20.0), ("T3", 5.0), ("T4", 30.0)]}
    _commit_prices(repo, SUBJECT, "ACC-TILT", items, closes)
    return repo, days


def test_tilt_trigger_calendar_and_playbook(tmp_path):
    repo, days = _tilt_fixture(tmp_path)
    store = ReviewStore(repo.connection)
    pack = build_review_pack(repo, SUBJECT, "ACC-TILT")

    rows = pack["exit_quality"]["episodes"]
    # Opening order: F1..F5, E1..E3, W1; then three episodes stay open.
    assert [row["realized_pnl"] for row in rows] == pytest.approx(
        [298.0, -302.0, 448.0, 118.0, 238.0, -1002.0, -1002.0, -502.0, 118.0])
    assert pack["coverage"]["execution_count"] == 21
    assert pack["coverage"]["episode_count"] == 12  # 9 closed + 3 open

    # Tilt: exactly one trigger on the third consecutive losing close.
    tilt = pack["behavior_flags"]["tilt"]
    assert len(tilt) == 1
    item = tilt[0]
    assert item["trigger"] == "three_consecutive_losses"
    assert item["trigger_date"] == days[65]
    window = item["window"]
    assert window["days"] == 10
    assert window["trade_count"] == 5
    assert window["baseline_trade_count"] == pytest.approx(21 / len(days))
    # Window buys avg 13525 vs prior-30-trading-day buys avg 10000.
    assert window["avg_size_change_pct"] == pytest.approx(0.3525)
    assert window["same_instrument_rebuy_count"] == 3
    assert any("不推断心理动机" in note for note in item["limitations"])

    # Calendar: realized PnL attributed to exit days, aggregated by month.
    months = {row["month"]: row for row in pack["calendar"]["months"]}
    assert set(months) == {"2024-12", "2025-01", "2025-02"}  # empty months absent
    assert months["2024-12"]["realized_pnl"] == pytest.approx(298.0)
    assert months["2025-01"]["closed_count"] == 7
    assert months["2025-01"]["win_count"] == 3
    assert months["2025-01"]["realized_pnl"] == pytest.approx(
        -302.0 + 448.0 + 118.0 + 238.0 - 1002.0 - 1002.0 - 502.0)
    assert sum(row["closed_count"] for row in pack["calendar"]["days"]) == 9
    day_row = next(row for row in pack["calendar"]["days"] if row["date"] == days[65])
    assert day_row == {"date": days[65], "realized_pnl": pytest.approx(-502.0), "closed_count": 1}

    # Playbook: win_rate only with >=5 tagged episodes, else insufficient.
    for index in range(5):
        store.set_tags(subject_id=SUBJECT, account_id="ACC-TILT",
                       episode_id=rows[index]["episode_id"], tags=["按计划执行"])
    store.set_tags(subject_id=SUBJECT, account_id="ACC-TILT",
                   episode_id=rows[5]["episode_id"], tags=["止损太晚"])
    store.set_tags(subject_id=SUBJECT, account_id="ACC-TILT",
                   episode_id=rows[6]["episode_id"], tags=["止损太晚", "亏损后回买"])
    store.set_tags(subject_id=SUBJECT, account_id="ACC-TILT",
                   episode_id=rows[8]["episode_id"], tags=["亏损后回买"])
    pack = build_review_pack(repo, SUBJECT, "ACC-TILT")
    tags = {row["tag"]: row for row in pack["playbook"]["tags"]}
    assert set(tags) == {"按计划执行", "止损太晚", "亏损后回买"}
    assert tags["按计划执行"] == {"tag": "按计划执行", "episode_count": 5, "win_count": 4,
                              "total_pnl": pytest.approx(298.0 - 302.0 + 448.0 + 118.0 + 238.0),
                              "win_rate": pytest.approx(0.8), "confidence": "sufficient"}
    assert tags["止损太晚"]["episode_count"] == 2
    assert tags["止损太晚"]["win_rate"] is None
    assert tags["止损太晚"]["confidence"] == "insufficient"
    assert tags["止损太晚"]["total_pnl"] == pytest.approx(-2004.0)
    assert tags["亏损后回买"]["confidence"] == "insufficient"
    assert pack["playbook"]["untagged_episode_count"] == 1
    assert len(pack["episode_tags"]) == 8
    tagged = {row["episode_id"]: row["tags"] for row in pack["episode_tags"]}
    assert tagged[rows[6]["episode_id"]] == ["止损太晚", "亏损后回买"]
    assert any("insufficient" in note or "不足" in note
               for note in pack["playbook"]["limitations"])
    json.dumps(pack, allow_nan=False)  # no NaN/Infinity may leak into the payload
    repo.close()


def test_tilt_sample_insufficient_below_twenty_executions(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    items = _commit_trades(repo, SUBJECT, "ACC-SMALL", [
        _exec_row("600000", "2025-01-02", "BUY", 100, 10.0, 1.0, "T1"),
        _exec_row("600000", "2025-01-08", "SELL", 100, 12.0, 1.0, "T2"),
    ])
    _commit_prices(repo, SUBJECT, "ACC-SMALL", items, {"600000": [
        ("2025-01-02", 10.5), ("2025-01-08", 12.0)]})
    pack = build_review_pack(repo, SUBJECT, "ACC-SMALL")
    repo.close()
    assert pack["behavior_flags"]["tilt"] == []
    assert any("样本不足" in item for item in pack["behavior_flags"]["limitations"])


def test_pack_schema_shape_is_exact(tmp_path):
    repo = LocalRepository(tmp_path / "db.sqlite3")
    items = _commit_trades(repo, SUBJECT, "ACC-EX", [
        _exec_row("600000", "2025-01-02", "BUY", 100, 10.0, 1.0, "T1"),
        _exec_row("600000", "2025-01-08", "SELL", 100, 12.0, 1.0, "T2"),
    ])
    _commit_prices(repo, SUBJECT, "ACC-EX", items, {"600000": [
        ("2025-01-02", 10.5), ("2025-01-08", 12.0)]})
    pack = build_review_pack(repo, SUBJECT, "ACC-EX")
    repo.close()
    assert set(pack) == {"schema_version", "subject_id", "account_id", "as_of", "coverage",
                         "exit_quality", "calendar", "behavior_flags", "playbook", "episode_tags"}
    assert set(pack["coverage"]) == {"execution_count", "episode_count", "first_date", "last_date"}
    assert set(pack["exit_quality"]) == {"episodes", "limitations"}
    assert set(pack["calendar"]) == {"months", "days", "limitations"}
    assert set(pack["behavior_flags"]) == {"tilt", "limitations"}
    assert set(pack["playbook"]) == {"tags", "untagged_episode_count", "limitations"}
    for row in pack["exit_quality"]["episodes"]:
        assert set(row) == {"episode_id", "instrument", "mfe_amount", "mae_amount", "mfe_pct",
                            "mae_pct", "realized_pnl", "status", "exit_efficiency",
                            "giveback_ratio", "hold_baseline_pnl", "hold_baseline_delta",
                            "facts", "limitations"}
        assert set(row["facts"]) == {"peak_date", "trough_date", "hold_days"}
    for row in pack["calendar"]["months"]:
        assert set(row) == {"month", "realized_pnl", "closed_count", "win_count"}
    for row in pack["calendar"]["days"]:
        assert set(row) == {"date", "realized_pnl", "closed_count"}
    for row in pack["playbook"]["tags"]:
        assert set(row) == {"tag", "episode_count", "win_count", "total_pnl", "win_rate",
                            "confidence"}
    for row in pack["episode_tags"]:
        assert set(row) == {"episode_id", "tags"}

"""Build the deterministic synthetic strategy-universe fixtures.

The output is a self-contained synthetic market used only by the strategy
history simulation (``src/strategy``).  It never mixes with real market data
contracts: every instrument id is ``SYN_POOL_*`` and the dataset ships its own
README.  Generation is deterministic (no RNG): piecewise-linear waypoint
interpolation in a split-adjusted price space plus ordinal-hash wiggles.

Outputs (under ``data/sample/strategy_universe/``):
  universe.csv          instrument,display_name,list_date,delist_date
  prices.csv            date,instrument,open,high,low,close   (unadjusted)
  corporate_actions.csv instrument,ex_date,action,ratio
  README.md
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/sample/strategy_universe"

START = "2022-08-01"
END = "2025-07-31"
SPLIT_DATE_A11 = "2024-05-15"
LIST_DATE_A08 = "2023-06-01"
DELIST_LAST_BAR_A09 = "2024-07-29"
DELIST_DATE_A09 = "2024-08-26"
SUSPENSION_A10 = ("2024-08-01", "2024-10-31")
# A09 engineered rally: a short-lived listing that enters while the demo account
# holds 3 of 4 slots (verified against the deterministic run), then halts and is
# delisted while held, so the demo run deterministically covers the forced
# liquidation path.  Compounding +6% closes from a flat base guarantee an A2
# breakout and never trigger the A3 exit while the rally lasts.
A09_RALLY_DAYS: Final[tuple[str, ...]] = (
    "2024-07-16", "2024-07-17", "2024-07-18", "2024-07-19", "2024-07-22",
    "2024-07-23", "2024-07-24", "2024-07-25", "2024-07-26", "2024-07-29",
)
A09_RALLY: Final[dict[str, float]] = {
    day: 1.06 ** (index + 1) for index, day in enumerate(A09_RALLY_DAYS)
}

# (instrument, display_name, waypoints [(u, adjusted_price)], volatility,
#  list_date, delist_date, split_ratio, missing_dates, close_overrides, open_overrides)
PROFILES: Final[tuple[tuple[str, str, tuple[tuple[float, float], ...], float, str, str | None, float | None, tuple[str, ...], dict[str, float], dict[str, float]], ...]] = (
    ("SYN_POOL_A01", "合成趋势一号", ((0.0, 10.0), (0.5, 20.0), (1.0, 30.0)), 0.012, START, None, None, (), {}, {}),
    ("SYN_POOL_A02", "合成震荡二号", ((0.0, 12.0), (0.25, 10.0), (0.5, 14.0), (0.75, 10.5), (1.0, 13.0)), 0.015, START, None, None, (), {}, {}),
    ("SYN_POOL_A03", "合成阴跌三号", ((0.0, 30.0), (1.0, 8.0)), 0.014, START, None, None, (), {}, {}),
    ("SYN_POOL_A04", "合成冲落四号", ((0.0, 10.0), (0.35, 26.0), (0.45, 24.0), (0.55, 9.0), (1.0, 8.5)), 0.018, START, None, None, (), {}, {}),
    ("SYN_POOL_A05", "合成慢牛五号", ((0.0, 12.0), (0.3, 15.0), (0.55, 14.0), (0.8, 19.0), (1.0, 22.0)), 0.013, START, None, None, (), {}, {}),
    ("SYN_POOL_A06", "合成暴涨六号", ((0.0, 15.0), (0.45, 16.0), (0.55, 38.0), (0.65, 14.0), (1.0, 12.0)), 0.020, START, None, None, (), {}, {}),
    ("SYN_POOL_A07", "合成横盘七号", ((0.0, 10.0), (1.0, 10.4)), 0.006, START, None, None, (), {}, {}),
    ("SYN_POOL_A08", "合成次新八号", ((0.0, 8.0), (0.6, 12.0), (1.0, 16.0)), 0.020, LIST_DATE_A08, None, None, (), {}, {}),
    ("SYN_POOL_A09", "合成退市九号", ((0.0, 10.0), (1.0, 11.0)), 0.012, START, DELIST_DATE_A09, None, (), A09_RALLY, {}),
    ("SYN_POOL_A10", "合成停牌十号", ((0.0, 14.0), (1.0, 18.0)), 0.012, START, None, None, (), {}, {}),
    ("SYN_POOL_A11", "合成拆股十一号", ((0.0, 10.0), (0.55, 12.5), (1.0, 15.0)), 0.010, START, None, 2.0, (), {}, {}),
    ("SYN_POOL_A12", "合成缺口十二号", ((0.0, 11.0), (1.0, 14.0)), 0.010, START, None, None, (), {}, {}),
    ("SYN_POOL_A13", "合成深调十三号", ((0.0, 25.0), (0.3, 12.0), (0.6, 13.0), (1.0, 20.0)), 0.016, START, None, None, (), {}, {}),
    ("SYN_POOL_A14", "合成沉寂十四号", ((0.0, 10.0), (1.0, 9.0)), 0.004, START, None, None, (), {}, {}),
    ("SYN_POOL_A15", "合成转折十五号", ((0.0, 10.0), (0.4, 18.0), (0.7, 17.5), (1.0, 12.0)), 0.014, START, None, None, (), {}, {}),
    ("SYN_POOL_A16", "合成宽幅十六号", ((0.0, 20.0), (0.2, 26.0), (0.35, 18.0), (0.5, 27.0), (0.65, 17.0), (0.8, 26.0), (1.0, 16.0)), 0.022, START, None, None, (), {}, {}),
)

# Scattered single-day gaps for A12 (declared missing observations, not suspension).
GAP_DATES_A12: Final[tuple[str, ...]] = (
    "2022-09-15", "2022-11-23", "2023-02-09", "2023-05-18", "2023-08-30",
    "2023-12-06", "2024-03-13", "2024-07-02", "2024-11-19", "2025-04-22",
)

README = """# 合成策略股票池（strategy_universe）

本目录数据 100% 合成，由 `scripts/build_strategy_universe_fixtures.py` 确定性生成，与任何真实证券无关，
只能用于策略历史模拟（`src/strategy`）的教学演示与测试，不得用于宣称真实业绩。

- `universe.csv`：点时成员资格。`list_date` 前与 `delist_date` 起（含当日）不可选。
- `prices.csv`：未复权日度价格（工作日枚举，非真实交易所日历）。缺行 = 当日不可交易（停牌或缺失）。
  合成十一号在 2024-05-15 按 1:2 拆股，因此此前价格约为之后的两倍——这是引擎必须处理的未复权现实。
- `corporate_actions.csv`：公司行动（V1 仅支持 split）。

重新生成：`.venv/bin/python scripts/build_strategy_universe_fixtures.py`（输出应与提交内容逐字节一致）。
"""


def _wiggle(ordinal: int, index: int, salt: int) -> float:
    """Deterministic pseudo-noise in [-0.5, 0.5); ordinal-hash, no RNG."""
    raw = (index * 2654435761 + ordinal * 40503 + salt * 97) % 2003
    return raw / 2003 - 0.5


def _waypoint_price(waypoints: tuple[tuple[float, float], ...], u: float) -> float:
    for index in range(1, len(waypoints)):
        u0, p0 = waypoints[index - 1]
        u1, p1 = waypoints[index]
        if u <= u1:
            span = u1 - u0
            share = 0.0 if span <= 0 else (u - u0) / span
            return p0 + (p1 - p0) * share
    return waypoints[-1][1]


def _round_cny(value: float) -> float:
    return max(0.01, round(value * 100.0 + 1e-9) / 100.0)


def _build_rows() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    all_days = pd.bdate_range(START, END)
    universe_rows: list[dict[str, object]] = []
    price_rows: list[dict[str, object]] = []
    action_rows: list[dict[str, object]] = []
    for ordinal, (instrument, display, waypoints, vol, list_date, delist_date, split_ratio,
                  missing, close_overrides, open_overrides) in enumerate(PROFILES):
        universe_rows.append({
            "instrument": instrument, "display_name": display, "list_date": list_date,
            "delist_date": "" if delist_date is None else delist_date,
        })
        if split_ratio is not None:
            action_rows.append({"instrument": instrument, "ex_date": SPLIT_DATE_A11,
                                "action": "split", "ratio": split_ratio})
        listed_from = pd.Timestamp(list_date)
        last_bar = pd.Timestamp(DELIST_LAST_BAR_A09) if instrument == "SYN_POOL_A09" else None
        gaps = {pd.Timestamp(day) for day in missing}
        if instrument == "SYN_POOL_A12":
            gaps |= {pd.Timestamp(day) for day in GAP_DATES_A12}
        suspended = set()
        if instrument == "SYN_POOL_A10":
            suspended = {day for day in all_days
                         if pd.Timestamp(SUSPENSION_A10[0]) <= day <= pd.Timestamp(SUSPENSION_A10[1])}
        prior_adj_close: float | None = None
        for index, day in enumerate(all_days):
            if day < listed_from or day in gaps or day in suspended:
                continue
            if last_bar is not None and day > last_bar:
                continue
            u = index / (len(all_days) - 1)
            close_adj = _waypoint_price(waypoints, u) * (1.0 + 2.0 * vol * _wiggle(ordinal, index, 1))
            close_adj *= close_overrides.get(day.date().isoformat(), 1.0)
            if prior_adj_close is None:
                open_adj = close_adj
            else:
                open_adj = prior_adj_close * (1.0 + 2.0 * vol * 0.6 * _wiggle(ordinal, index, 2))
            open_adj *= open_overrides.get(day.date().isoformat(), 1.0)
            high_adj = max(open_adj, close_adj) * (1.0 + vol * abs(_wiggle(ordinal, index, 3)))
            low_adj = min(open_adj, close_adj) * (1.0 - vol * abs(_wiggle(ordinal, index, 4)))
            prior_adj_close = close_adj
            # Raw (unadjusted) prices: multiply by the product of future split ratios.
            factor = split_ratio if (split_ratio is not None and day < pd.Timestamp(SPLIT_DATE_A11)) else 1.0
            open_raw = _round_cny(open_adj * factor)
            close_raw = _round_cny(close_adj * factor)
            high_raw = max(_round_cny(high_adj * factor), open_raw, close_raw)
            low_raw = min(_round_cny(low_adj * factor), open_raw, close_raw)
            price_rows.append({
                "date": day.date().isoformat(), "instrument": instrument,
                "open": open_raw, "high": high_raw, "low": low_raw, "close": close_raw,
            })
    return universe_rows, price_rows, action_rows


def _csv_bytes(rows: list[dict[str, object]], columns: tuple[str, ...]) -> bytes:
    frame = pd.DataFrame(rows, columns=list(columns))
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def main() -> int:
    universe_rows, price_rows, action_rows = _build_rows()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = {
        "universe.csv": _csv_bytes(universe_rows, ("instrument", "display_name", "list_date", "delist_date")),
        "prices.csv": _csv_bytes(price_rows, ("date", "instrument", "open", "high", "low", "close")),
        "corporate_actions.csv": _csv_bytes(action_rows, ("instrument", "ex_date", "action", "ratio")),
        "README.md": README.encode("utf-8"),
    }
    for name, payload in files.items():
        (OUTPUT / name).write_bytes(payload)
    digest = hashlib.sha256(b"".join(files[name] for name in sorted(files))).hexdigest()
    print(json.dumps({"output": str(OUTPUT), "instruments": len(universe_rows),
                      "price_rows": len(price_rows), "actions": len(action_rows),
                      "sha256": digest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

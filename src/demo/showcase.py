"""One fictional account shared by every product demonstration.

This module defines INPUTS, never financial outputs. The synthetic weekday
schedule is not an exchange calendar. No prices or trades represent a real
security, person or professional's track record. Legacy regression fixtures
are deliberately left intact.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

VERSION = "toujing_showcase_v1"
SUBJECT_ID = ACCOUNT_ID = "SYN_STUDY_SHOWCASE"
REFERENCE_SUBJECT = "SYN_STUDY_SHOWCASE_REFERENCE"
SUBJECTS = (SUBJECT_ID, REFERENCE_SUBJECT)
START, MIDDLE, END = "2025-01-02", "2025-07-02", "2025-12-31"
AS_OF = pd.Timestamp(f"{END} 23:59:00")
INITIAL_CASH = 100_000.0
SYMBOLS = ("SYN_GROWTH", "SYN_VALUE", "SYN_FUND")
NAMES = {
    "SYN_GROWTH": {"zh": "辰光科技 · 模拟", "en": "Chenguang Tech · Simulated"},
    "SYN_VALUE": {"zh": "远川制造 · 模拟", "en": "Yuanchuan Industrial · Simulated"},
    "SYN_FUND": {"zh": "均衡组合基金 · 模拟", "en": "Balanced Fund · Simulated"},
    "SYN_INDUSTRIAL": {"zh": "其他制造成分 · 模拟", "en": "Other industrial holdings · Simulated"},
    "cash": {"zh": "现金", "en": "Cash"},
}

# Date, security, side, quantity, assumed execution price. Explicit source
# facts, not a strategy optimized against the subsequently generated path.
MAIN_TRADES = (
    ("2025-01-02", "SYN_VALUE", "BUY", 600, 20.0),
    ("2025-01-02", "SYN_FUND", "BUY", 2500, 10.0),
    ("2025-01-13", "SYN_GROWTH", "BUY", 400, 10.0),
    ("2025-02-07", "SYN_GROWTH", "BUY", 300, 11.2),
    ("2025-03-03", "SYN_FUND", "BUY", 500, 9.7),
    ("2025-03-07", "SYN_GROWTH", "BUY", 400, 12.2),
    ("2025-03-14", "SYN_VALUE", "BUY", 200, 21.0),
    ("2025-04-10", "SYN_GROWTH", "SELL", 400, 10.8),
    ("2025-05-08", "SYN_GROWTH", "SELL", 300, 10.4),
    ("2025-05-16", "SYN_VALUE", "SELL", 300, 24.0),
    ("2025-06-06", "SYN_GROWTH", "SELL", 400, 10.5),
    ("2025-06-13", "SYN_VALUE", "SELL", 500, 26.0),
    ("2025-07-11", "SYN_GROWTH", "BUY", 600, 10.8),
    ("2025-08-01", "SYN_VALUE", "BUY", 500, 25.0),
    ("2025-08-08", "SYN_GROWTH", "BUY", 400, 10.2),
    ("2025-09-12", "SYN_FUND", "SELL", 500, 11.2),
    ("2025-09-19", "SYN_GROWTH", "SELL", 300, 13.4),
    ("2025-10-10", "SYN_VALUE", "SELL", 200, 27.0),
    ("2025-11-07", "SYN_FUND", "BUY", 400, 11.8),
    ("2025-11-14", "SYN_GROWTH", "BUY", 200, 12.6),
)
REFERENCE_TRADES = (
    ("2025-01-02", "SYN_VALUE", "BUY", 1200, 20.0),
    ("2025-01-02", "SYN_FUND", "BUY", 4000, 10.0),
    ("2025-01-13", "SYN_GROWTH", "BUY", 400, 10.0),
    ("2025-03-07", "SYN_GROWTH", "SELL", 200, 12.2),
    ("2025-06-06", "SYN_GROWTH", "SELL", 200, 10.5),
    ("2025-06-13", "SYN_VALUE", "SELL", 300, 26.0),
    ("2025-07-11", "SYN_GROWTH", "BUY", 500, 10.8),
    ("2025-09-19", "SYN_GROWTH", "SELL", 200, 13.4),
    ("2025-10-10", "SYN_VALUE", "SELL", 200, 27.0),
)
# The paired first growth investments explicitly share entry and exit times.
# This is a declared fictional fill time, not a change to replay cutoffs or
# inferred intraday market availability. Other rows retain their source order.
EXECUTION_TIME_OVERRIDES = {
    (REFERENCE_SUBJECT, "2025-06-06", "SYN_GROWTH", "SELL"): pd.Timestamp("2025-06-06 10:10:00"),
}


def showcase_inputs(subject: str = SUBJECT_ID) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return fresh deterministic account executions and common daily OHLCV."""
    if subject not in SUBJECTS:
        raise ValueError("unregistered_showcase_subject")
    dates = pd.bdate_range(START, END)
    anchors = {
        "SYN_GROWTH": {START: 9.8, "2025-03-21": 12.8, "2025-04-04": 9.8,
                       "2025-07-02": 10.6, "2025-10-01": 14.0, END: 14.4},
        "SYN_VALUE": {START: 20.0, "2025-02-21": 19.1, "2025-07-02": 25.2, END: 28.0},
        "SYN_FUND": {START: 10.0, "2025-07-02": 10.6, END: 12.0},
        "SYN_MARKET": {START: 100.0, "2025-03-21": 108.0, "2025-04-04": 95.0,
                       "2025-07-02": 104.0, "2025-10-01": 114.0, END: 116.0},
        "SHOWCASE_INDUSTRY": {START: 100.0, "2025-03-21": 113.0, "2025-04-04": 92.0,
                              "2025-07-02": 102.0, "2025-10-01": 115.0, END: 118.0},
    }
    for date, symbol, _, _, price in (*MAIN_TRADES, *REFERENCE_TRADES):
        old = anchors[symbol].get(date)
        if old is not None and old != price:
            raise ValueError("conflicting_showcase_price_anchor")
        anchors[symbol][date] = price
    rows = []
    for asset, (symbol, knots) in enumerate(anchors.items()):
        ordered = sorted(knots.items())
        x = np.array([dates.get_loc(pd.Timestamp(date)) for date, _ in ordered])
        values = np.interp(np.arange(len(dates)), x, [v for _, v in ordered])
        # Bounded deterministic daily texture; declared simulated source prices,
        # not filled market observations or financial return calculations.
        for i, date in enumerate(dates):
            close = round(float(values[i]) * (1 + 0.005 * np.sin(i * 1.73 + asset)), 4)
            close = knots.get(date.date().isoformat(), close)
            opening = round(close * (1 + 0.007 * np.sin(i * 0.93 + asset + 1)), 4)
            high = round(max(opening, close) * 1.012, 4)
            low = round(min(opening, close) * 0.988, 4)
            volume = int(600_000 + ((i * 7919 + asset * 104729) % 800_000))
            rows.append(dict(date=date, instrument=symbol, open=opening, high=high,
                             low=low, close=float(close), volume=volume, amount=None,
                             price_type="synthetic", data_source=VERSION,
                             data_version="1", is_synthetic=True))
    schedule = MAIN_TRADES if subject == SUBJECT_ID else REFERENCE_TRADES
    executions = pd.DataFrame([
        dict(event_time=EXECUTION_TIME_OVERRIDES.get(
                 (subject, date, symbol, side),
                 pd.Timestamp(date) + pd.Timedelta(hours=10, minutes=sequence)),
             symbol=symbol, side=side, executed_quantity=float(quantity),
             executed_price=float(price), fee=5.0, execution_sequence=sequence + 1,
             execution_id=f"{subject}:execution:{sequence + 1:02d}",
             order_id=f"{subject}:order:{sequence + 1:02d}",
             subject_id=subject, account_id=subject)
        for sequence, (date, symbol, side, quantity, price) in enumerate(schedule)
    ])
    return executions, pd.DataFrame(rows)


def source_fingerprint(subject: str = SUBJECT_ID) -> str:
    executions, prices = showcase_inputs(subject)
    payload = {"version": VERSION, "executions": executions.to_json(date_format="iso", orient="split"),
               "prices": prices.to_json(date_format="iso", orient="split")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

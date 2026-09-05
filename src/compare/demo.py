"""Dedicated, explicitly synthetic same-listing pair; never a real fallback."""

import pandas as pd

from src.compare.same_stock import build_episode_compare_facts, compare_same_stock
from src.core.canonical_execution import instrument_ref

INSTRUMENT = instrument_ref(local_symbol="SYN_COMPARE", market="SYNTHETIC",
                            security_type="equity", currency="CNY",
                            display_name="同股操作示例 / Synthetic comparison")
AS_OF = pd.Timestamp("2025-01-17 16:00:00")


def pair_inputs():
    dates = pd.bdate_range("2025-01-02", "2025-01-17")
    closes = [10, 10.8, 12, 13, 11.5, 9, 8.5, 9.5, 11, 10, 11.5, 11]
    prices = pd.DataFrame({"date": dates, "instrument": INSTRUMENT.instrument_id,
                           "close": closes, "price_type": "synthetic",
                           "data_source": "same_stock_pair_fixture", "data_version": "1",
                           "is_synthetic": True})
    schedules = {
        "A": [(0, "BUY", 100, 10), (2, "BUY", 100, 12), (3, "BUY", 100, 13),
              (7, "SELL", 100, 9.5), (11, "SELL", 200, 11)],
        "B": [(0, "BUY", 100, 10), (3, "SELL", 40, 13), (8, "BUY", 40, 11),
              (10, "SELL", 40, 11.5), (11, "SELL", 60, 11)],
    }
    frames = {}
    for who, schedule in schedules.items():
        frames[who] = pd.DataFrame([
            {"subject_id": f"SYN_COMPARE_{who}", "account_id": f"SYN_COMPARE_ACCOUNT_{who}",
             "event_time": dates[day] + pd.Timedelta(hours=10),
             "symbol": INSTRUMENT.instrument_id, "side": side,
             "executed_quantity": qty, "executed_price": price, "fee": 1.0,
             "execution_id": f"SYN_COMPARE_{who}_EXEC_{i}",
             "order_id": f"SYN_COMPARE_{who}_ORDER_{i}", "execution_sequence": i + 1}
            for i, (day, side, qty, price) in enumerate(schedule)
        ])
    return frames, prices


def build_pair():
    frames, prices = pair_inputs()
    facts = [build_episode_compare_facts(
        frames[who], prices, subject_id=f"SYN_COMPARE_{who}",
        account_id=f"SYN_COMPARE_ACCOUNT_{who}", instrument=INSTRUMENT,
        as_of=AS_OF, init_cash=100_000, data_tier="synthetic",
    ) for who in ("A", "B")]
    return compare_same_stock(*facts)

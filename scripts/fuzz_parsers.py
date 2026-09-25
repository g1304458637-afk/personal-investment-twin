"""Ad-hoc fuzz harness: hostile CSVs must produce typed errors, never crashes.

Run: python scripts/fuzz_parsers.py
Exit code 0 = every parser answered with an expected error type (or succeeded);
exit 1 prints the offending (parser, input, exception) triples.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.csv_importer import load_normalized_csv
from src.ingestion.broker_csv import BROKER_EASTMONEY, BROKER_THS, convert_to_generic_csv, detect_broker_format
from src.ingestion.generic_csv import GenericCsvImportConfig, preview_generic_csv
from src.market_data.generic_csv import GenericHistoricalPriceCsvAdapter, GenericPriceCsvConfig

TRADE_CONFIG = GenericCsvImportConfig(
    subject_id="SUBJECT-1", account_id="ACC-1", source_timezone="Asia/Shanghai",
)
PRICE_CONFIG = GenericPriceCsvConfig(source_id="fuzz", source_version="v1", imported_at="2026-09-17T00:00:00")
PRICE_ADAPTER = GenericHistoricalPriceCsvAdapter()

EXPECTED = (ValueError,)  # parsers contract: ValueError (often with issue codes)

TRADE_HEADERS = "symbol,market,security_type,event_time,side,quantity,price,fee\n"
PRICE_HEADERS = "date,symbol,close,price_type\n"

HOSTILE_TRADE_ROWS = [
    "",
    ",,,,,,,\n",
    ",,,,,,,",
    "A\n",
    "A,X\n",
    "A,X,equity\n",
    "A,X,equity,2025-13-45 99:99:99,BUY,1,10,0\n",
    "A,X,equity,2025-01-02,BUY,0,0,0\n",
    "A,X,equity,2025-01-02,BUY,-5,10,0\n",
    "A,X,equity,2025-01-02,BUY,1e400,10,0\n",
    "A,X,equity,2025-01-02,BUY,NaN,10,0\n",
    "A,X,equity,2025-01-02,BUY,inf,10,0\n",
    "A,X,equity,2025-01-02,BUY,１,１０,０\n",
    "A,X,equity,2025-01-02 09:30:00+25:00,BUY,1,10,0\n",
    "A,X,equity,9999-12-31 23:59:59,BUY,1,10,0\n",
    "A,X,equity,2025-01-02,BUY,1,10,0\n" * 200,
    'A,X,equity,2025-01-02,BUY,1,10,0,"' + "x" * 100000 + '"\n',
    "A,X,equity,2025-01-02,BUY,1,10,0,extra,cells,here\n",
    "\x00A,X,equity,2025-01-02,BUY,1,10,0\n",
    "A,X,equity,2025-01-02,BUY,1,10,0\n\x00\n",
    "﻿" + TRADE_HEADERS + "A,X,equity,2025-01-02,BUY,1,10,0\n",
    "symbol,market,security_type,event_time,side,quantity,price,fee\nA,X\n",
    "symbol,symbol,event_time,side,quantity,price,fee\nA,X,2025-01-02,BUY,1,10,0\n",
]

HOSTILE_PRICE_ROWS = [
    "",
    ",,,\n",
    "A\n",
    "X,,,close\n",
    "2025-01-02,A,not-a-number,close\n",
    "2025-01-02,A,-5,close\n",
    "2025-01-02,A,1e400,close\n",
    "2025-01-02,A,NaN,close\n",
    "2025-13-45,A,10,close\n",
    "2025-01-02,A,10,weird_type\n",
    "2025-01-02,A,10,close\n" * 200,
    "﻿" + PRICE_HEADERS + "2025-01-02,A,10,close\n",
    "date,symbol,close,price_type\n2025-01-02,A\n",
]

HOSTILE_LOADCSV = [
    "execution_time,symbol,side,quantity,price,fee\n",
    "execution_time,symbol,side,quantity,price,fee\n2025-01-02,A,BUY,1,10,0,EXTRA\n",
    "execution_time,symbol,side,quantity,price,fee\ngarbage,A,BUY,1,10,0\n",
    "execution_time,symbol,side,quantity,price,fee\n,2025-01-02,A,BUY,1,10,0\n",
]

HOSTILE_BROKER = [
    b"",
    b"\xff\xfe\x00bad",
    b"\x81\x7f",
    "成交日期,成交时间,证券代码,买卖方向,成交价格,成交数量\n".encode("gbk"),
    "日期,时间,代码,操作,成交价,数量\n合计,合计,合计,买入,abc,def\n".encode("gbk"),
    ("日期,时间,代码,操作,成交价,数量\n" + "2024-12-31,09:31:05,600519,证券买入,1500.00,100\n" * 500).encode("gbk"),
]


def check(name: str, fn, arg) -> str:
    try:
        fn(arg)
        return "ok"
    except EXPECTED:
        return "typed-error"
    except Exception as exc:  # unexpected crash
        print(f"UNEXPECTED in {name}: {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        return "CRASH"


def run_suite() -> tuple[int, int]:
    crashes = 0
    total = 0

    for index, row in enumerate(HOSTILE_TRADE_ROWS):
        total += 1
        if check(f"trade[{index}]", lambda c: preview_generic_csv(c, config=TRADE_CONFIG), TRADE_HEADERS + row) == "CRASH":
            crashes += 1
        total += 1
        if check(f"trade-bare[{index}]", lambda c: preview_generic_csv(c, config=TRADE_CONFIG), row) == "CRASH":
            crashes += 1

    for index, row in enumerate(HOSTILE_PRICE_ROWS):
        total += 1
        if check(f"price[{index}]", lambda c: PRICE_ADAPTER.preview(PRICE_HEADERS + row, PRICE_CONFIG), None) == "CRASH":
            crashes += 1

    for index, text in enumerate(HOSTILE_LOADCSV):
        total += 1
        if check(f"loadcsv[{index}]", lambda c: load_normalized_csv_path(c), text) == "CRASH":
            crashes += 1

    for index, blob in enumerate(HOSTILE_BROKER):
        total += 1
        def broker(b):
            broker_name = detect_broker_format(b)
            if broker_name is not None:
                convert_to_generic_csv(b, broker_name)
        if check(f"broker[{index}]", broker, blob) == "CRASH":
            crashes += 1

    # Byte-level mutation fuzz on the two known-good fixtures.
    good_trade = (TRADE_HEADERS + "A,X,equity,2025-01-02 09:30:00,BUY,100,10.0,1.0\n").encode()
    for seed in range(300):
        mutated = mutate(good_trade, seed)
        total += 1
        if check(f"trade-mut[{seed}]", lambda c: preview_generic_csv(c, config=TRADE_CONFIG), mutated) == "CRASH":
            crashes += 1
    good_price = (PRICE_HEADERS + "2025-01-02,A,10.0,close\n").encode()
    for seed in range(300):
        mutated = mutate(good_price, seed)
        total += 1
        if check(f"price-mut[{seed}]", lambda c: PRICE_ADAPTER.preview(mutated, PRICE_CONFIG), None) == "CRASH":
            crashes += 1

    print(f"{total} hostile inputs, {crashes} unexpected crashes")
    return total, crashes


def main() -> int:
    _, crashes = run_suite()
    return 1 if crashes else 0


def load_normalized_csv_path(text: str):
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        handle.write(text)
        name = handle.name
    try:
        return load_normalized_csv(name)
    finally:
        Path(name).unlink(missing_ok=True)


def mutate(data: bytes, seed: int) -> bytes:
    import random
    rng = random.Random(seed)
    out = bytearray(data)
    for _ in range(rng.randint(1, 6)):
        op = rng.randint(0, 2)
        if not out:
            break
        pos = rng.randrange(len(out))
        if op == 0:
            out[pos] = rng.randrange(256)
        elif op == 1:
            del out[pos]
        else:
            out.insert(pos, rng.choice(b',"\n\r\x00\xff $$'))
    return bytes(out)


if __name__ == "__main__":
    sys.exit(main())

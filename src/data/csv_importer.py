from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


COLUMN_MAP = {
    "execution_time": "event_time",
    "quantity": "executed_quantity",
    "price": "executed_price",
}


def _stable_execution_id(row: pd.Series) -> str:
    """Generate a stable internal ID when the source file has no execution ID."""
    raw = (
        f"{row['event_time']}|{row['symbol']}|{row['side']}|"
        f"{row['executed_quantity']}|{row['executed_price']}|{row['fee']}"
    )
    return "INT-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_normalized_csv(path: str | Path) -> pd.DataFrame:
    """Load the current synthetic CSV into the normalized execution contract."""
    df = pd.read_csv(path)

    df = df.rename(columns=COLUMN_MAP)

    required = {
        "event_time",
        "symbol",
        "side",
        "executed_quantity",
        "executed_price",
        "fee",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["event_time"] = pd.to_datetime(df["event_time"])
    df["side"] = df["side"].astype(str).str.upper().str.strip()
    df["symbol"] = df["symbol"].astype(str).str.strip()

    df["executed_quantity"] = pd.to_numeric(df["executed_quantity"])
    df["executed_price"] = pd.to_numeric(df["executed_price"])
    df["fee"] = pd.to_numeric(df["fee"])

    if not set(df["side"]).issubset({"BUY", "SELL"}):
        raise ValueError("side must be BUY or SELL")

    if (df["executed_quantity"] <= 0).any():
        raise ValueError("executed_quantity must be positive")

    if (df["executed_price"] <= 0).any():
        raise ValueError("executed_price must be positive")

    if (df["fee"] < 0).any():
        raise ValueError("fee must be non-negative")

    if "order_id" not in df.columns:
        df["order_id"] = [f"INT-ORDER-{i:06d}" for i in range(1, len(df) + 1)]

    if "execution_id" not in df.columns:
        df["execution_id"] = df.apply(_stable_execution_id, axis=1)

    return df[
        [
            "event_time",
            "symbol",
            "side",
            "executed_quantity",
            "executed_price",
            "fee",
            "order_id",
            "execution_id",
        ]
    ].copy()

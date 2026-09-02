"""Product-level InvestmentEpisode mapped from a vectorbt Position record."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import pandas as pd


VECTORBT_POSITION_FIELDS: Final[tuple[str, ...]] = (
    "Position Id",
    "Column",
    "Size",
    "Entry Timestamp",
    "Avg Entry Price",
    "Entry Fees",
    "Exit Timestamp",
    "Avg Exit Price",
    "Exit Fees",
    "PnL",
    "Return",
    "Direction",
    "Status",
)


@dataclass(frozen=True, slots=True)
class InvestmentEpisode:
    """Stable product representation of one vectorbt Position.

    ``pnl`` and ``return_value`` always come directly from vectorbt.  For a
    Closed position they are closed-position metrics; for an Open position
    they are vectorbt mark-to-market metrics at ``valuation_time`` and
    ``valuation_price``.
    """

    episode_id: str
    symbol: str
    size: float
    entry_time: pd.Timestamp
    avg_entry_price: float
    entry_fees: float
    exit_time: pd.Timestamp | None
    avg_exit_price: float | None
    exit_fees: float | None
    valuation_time: pd.Timestamp | None
    valuation_price: float | None
    pnl: float
    return_value: float
    direction: str
    status: str
    position_id: int


def _required_timestamp(value: object, field: str) -> pd.Timestamp:
    if pd.isna(value):
        raise ValueError(f"{field} cannot be null")
    return pd.Timestamp(value)


def _required_float(value: object, field: str) -> float:
    if pd.isna(value):
        raise ValueError(f"{field} cannot be null")
    return float(value)


def from_vectorbt_position_record(
    record: Mapping[str, object] | pd.Series,
) -> InvestmentEpisode:
    """Map one ``positions.records_readable`` row without financial recomputation.

    The episode ID is an internal product identifier derived from vectorbt's
    position ID and symbol.  It is not a broker order or execution identifier.
    """

    missing = [field for field in VECTORBT_POSITION_FIELDS if field not in record]
    if missing:
        raise ValueError(f"Missing vectorbt Position fields: {missing}")

    for field in ("Position Id", "Column", "Direction", "Status"):
        if pd.isna(record[field]):
            raise ValueError(f"{field} cannot be null")

    position_id = int(record["Position Id"])
    symbol = str(record["Column"])
    direction = str(record["Direction"])
    status = str(record["Status"])
    if not symbol:
        raise ValueError("Column cannot be empty")
    if not direction:
        raise ValueError("Direction cannot be empty")
    if status not in {"Open", "Closed"}:
        raise ValueError("Status must be Open or Closed")

    if status == "Closed":
        exit_time = _required_timestamp(record["Exit Timestamp"], "Exit Timestamp")
        avg_exit_price = _required_float(record["Avg Exit Price"], "Avg Exit Price")
        exit_fees = _required_float(record["Exit Fees"], "Exit Fees")
        valuation_time = None
        valuation_price = None
    else:
        exit_time = None
        avg_exit_price = None
        exit_fees = None
        valuation_time = _required_timestamp(record["Exit Timestamp"], "Exit Timestamp")
        valuation_price = _required_float(record["Avg Exit Price"], "Avg Exit Price")

    return InvestmentEpisode(
        episode_id=f"investment-episode:{symbol}:{position_id}",
        symbol=symbol,
        size=_required_float(record["Size"], "Size"),
        entry_time=_required_timestamp(record["Entry Timestamp"], "Entry Timestamp"),
        avg_entry_price=_required_float(record["Avg Entry Price"], "Avg Entry Price"),
        entry_fees=_required_float(record["Entry Fees"], "Entry Fees"),
        exit_time=exit_time,
        avg_exit_price=avg_exit_price,
        exit_fees=exit_fees,
        valuation_time=valuation_time,
        valuation_price=valuation_price,
        pnl=_required_float(record["PnL"], "PnL"),
        return_value=_required_float(record["Return"], "Return"),
        direction=direction,
        status=status,
        position_id=position_id,
    )

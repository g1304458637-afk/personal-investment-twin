"""Load and validate the synthetic strategy-universe dataset.

The strategy simulation consumes its own closed dataset (universe membership,
unadjusted daily OHLC, corporate actions).  It never reads the real market
data contract or user-imported prices; every instrument must be a synthetic
pool member so simulated results cannot be attributed to real securities.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

REQUIRED_PRICE_COLUMNS = ("date", "instrument", "open", "high", "low", "close")
REQUIRED_UNIVERSE_COLUMNS = ("instrument", "display_name", "list_date", "delist_date")
REQUIRED_ACTION_COLUMNS = ("instrument", "ex_date", "action", "ratio")
SUPPORTED_ACTIONS = {"split"}


class StrategyDataError(ValueError):
    """The strategy dataset is missing, inconsistent, or not synthetic-only."""


@dataclass(frozen=True, slots=True)
class UniverseMember:
    instrument: str
    display_name: str
    list_date: date
    delist_date: date | None


@dataclass(frozen=True, slots=True)
class CorporateAction:
    instrument: str
    ex_date: date
    action: str
    ratio: float


@dataclass(frozen=True, slots=True)
class Bar:
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class InstrumentSeries:
    """Immutable per-instrument daily series with split adjustment factors.

    ``raw`` prices are the unadjusted traded prices used for fills, stops and
    valuation.  ``adjusted_close`` divides raw closes by the cumulative future
    split factor so signals stay continuous across splits.  Windows count
    valid observations, not calendar days (the Decision Lens convention).
    """

    instrument: str
    dates: tuple[date, ...]
    bars: tuple[Bar, ...]
    adjusted_close: tuple[float, ...]
    split_factors: tuple[float, ...]

    def index_on_or_before(self, day: date) -> int | None:
        """Latest observation index with date <= day, or None."""
        low, high, found = 0, len(self.dates) - 1, None
        while low <= high:
            mid = (low + high) // 2
            if self.dates[mid] <= day:
                found = mid
                low = mid + 1
            else:
                high = mid - 1
        return found

    def bar_on(self, day: date) -> Bar | None:
        index = self.index_on_or_before(day)
        if index is None or self.dates[index] != day:
            return None
        return self.bars[index]

    def raw_close_on_or_before(self, day: date) -> float | None:
        index = self.index_on_or_before(day)
        return None if index is None else self.bars[index].close


@dataclass(frozen=True, slots=True)
class SimulationData:
    dates: tuple[date, ...]
    series: dict[str, InstrumentSeries]
    members: dict[str, UniverseMember]
    actions: tuple[CorporateAction, ...]
    fingerprint: str

    def listed_on(self, day: date) -> tuple[str, ...]:
        return tuple(
            instrument for instrument, member in self.members.items()
            if member.list_date <= day and (member.delist_date is None or day < member.delist_date)
        )


def _parse_day(value: object, field_name: str) -> date:
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        raise StrategyDataError(f"{field_name} is not a valid date: {value!r}")
    return parsed.date()


def _finite(value: object, field_name: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise StrategyDataError(f"{field_name} is not numeric: {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise StrategyDataError(f"{field_name} must be finite and positive: {value!r}")
    return number


def _load_csv(path: Path, required_columns: tuple[str, ...]) -> pd.DataFrame:
    if not path.exists():
        raise StrategyDataError(f"missing strategy dataset file: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise StrategyDataError(f"{path.name} lacks required columns: {', '.join(missing)}")
    return frame


def load_simulation_data(directory: Path) -> SimulationData:
    """Load the three fixture CSVs; fail closed on any structural problem."""
    directory = Path(directory)
    # Content fingerprint covers full file bytes so any price edit changes it.
    fingerprint_source = b"".join(
        (directory / name).read_bytes()
        for name in ("universe.csv", "prices.csv", "corporate_actions.csv")
        if (directory / name).exists()
    )
    universe_frame = _load_csv(directory / "universe.csv", REQUIRED_UNIVERSE_COLUMNS)
    prices_frame = _load_csv(directory / "prices.csv", REQUIRED_PRICE_COLUMNS)
    actions_path = directory / "corporate_actions.csv"
    if actions_path.exists():
        actions_frame = _load_csv(actions_path, REQUIRED_ACTION_COLUMNS)
    else:
        actions_frame = pd.DataFrame(columns=list(REQUIRED_ACTION_COLUMNS))

    members: dict[str, UniverseMember] = {}
    for _, row in universe_frame.iterrows():
        instrument = str(row["instrument"]).strip()
        if not instrument:
            raise StrategyDataError("universe row without instrument id")
        if not instrument.startswith("SYN_POOL_"):
            # Hard boundary: the strategy dataset may never contain real securities.
            raise StrategyDataError(f"non-synthetic instrument in strategy dataset: {instrument}")
        if instrument in members:
            raise StrategyDataError(f"duplicate universe member: {instrument}")
        delist_text = str(row["delist_date"]).strip()
        members[instrument] = UniverseMember(
            instrument=instrument,
            display_name=str(row["display_name"]).strip(),
            list_date=_parse_day(row["list_date"], f"{instrument}.list_date"),
            delist_date=_parse_day(delist_text, f"{instrument}.delist_date") if delist_text else None,
        )
    if not members:
        raise StrategyDataError("strategy universe is empty")

    actions: list[CorporateAction] = []
    for _, row in actions_frame.iterrows():
        instrument = str(row["instrument"]).strip()
        action = str(row["action"]).strip()
        ratio = _finite(row["ratio"], f"{instrument}.ratio")
        if instrument not in members:
            raise StrategyDataError(f"corporate action for unknown instrument: {instrument}")
        if action not in SUPPORTED_ACTIONS:
            raise StrategyDataError(f"unsupported corporate action: {action}")
        if ratio <= 0:
            raise StrategyDataError(f"split ratio must be positive: {instrument}")
        actions.append(CorporateAction(instrument=instrument,
                                       ex_date=_parse_day(row["ex_date"], f"{instrument}.ex_date"),
                                       action=action, ratio=ratio))
    actions.sort(key=lambda item: (item.instrument, item.ex_date, item.action))
    seen_actions: set[tuple[str, date, str]] = set()
    for item in actions:
        key = (item.instrument, item.ex_date, item.action)
        if key in seen_actions:
            raise StrategyDataError(f"duplicate corporate action: {key}")
        seen_actions.add(key)

    prices_frame["date"] = prices_frame["date"].map(lambda value: _parse_day(value, "prices.date"))
    grouped: dict[str, list[tuple[date, Bar]]] = {instrument: [] for instrument in members}
    for row in prices_frame.itertuples(index=False):
        instrument = str(row.instrument).strip()
        if instrument not in grouped:
            raise StrategyDataError(f"price rows for instrument outside universe: {instrument}")
        bar = Bar(
            open=_finite(row.open, f"{instrument}.open"),
            high=_finite(row.high, f"{instrument}.high"),
            low=_finite(row.low, f"{instrument}.low"),
            close=_finite(row.close, f"{instrument}.close"),
        )
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.high < bar.low:
            raise StrategyDataError(f"inconsistent OHLC on {row.date} for {instrument}")
        grouped[instrument].append((row.date, bar))

    all_dates: set[date] = set()
    # Delist dates are event days even when no instrument prints a bar then:
    # the forced liquidation must run inside the simulation calendar.
    all_dates.update(member.delist_date for member in members.values()
                     if member.delist_date is not None)
    series: dict[str, InstrumentSeries] = {}
    for instrument, rows in grouped.items():
        rows.sort(key=lambda item: item[0])
        dates = tuple(day for day, _ in rows)
        if len(set(dates)) != len(dates):
            raise StrategyDataError(f"duplicate price dates for {instrument}")
        member = members[instrument]
        if dates and dates[0] < member.list_date:
            raise StrategyDataError(f"{instrument} has bars before its list_date")
        if member.delist_date is not None and dates and dates[-1] >= member.delist_date:
            raise StrategyDataError(f"{instrument} has bars on or after its delist_date")
        instrument_actions = sorted(
            (item for item in actions if item.instrument == instrument and item.action == "split"),
            key=lambda item: item.ex_date)
        split_factors: list[float] = []
        adjusted: list[float] = []
        for day, bar in rows:
            factor = 1.0
            for item in instrument_actions:
                if item.ex_date > day:
                    factor *= item.ratio
            split_factors.append(factor)
            adjusted.append(bar.close / factor)
        all_dates.update(dates)
        series[instrument] = InstrumentSeries(
            instrument=instrument, dates=dates, bars=tuple(bar for _, bar in rows),
            adjusted_close=tuple(adjusted), split_factors=tuple(split_factors))
    if not all_dates:
        raise StrategyDataError("strategy dataset contains no price rows")

    fingerprint_payload = {
        "content_sha256": hashlib.sha256(fingerprint_source).hexdigest(),
        "universe": sorted((member.instrument, member.list_date.isoformat(),
                            member.delist_date.isoformat() if member.delist_date else None)
                           for member in members.values()),
        "actions": [(item.instrument, item.ex_date.isoformat(), item.action, item.ratio) for item in actions],
        "row_count": int(len(prices_frame)),
    }
    digest = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode()).hexdigest()
    return SimulationData(dates=tuple(sorted(all_dates)), series=series, members=members,
                          actions=tuple(actions), fingerprint=digest)

"""Export one fixed-source historical chart with a separate simulated ledger.

This exporter deliberately reuses the existing position Episode, replay, Outcome,
and presentation builders.  It only adapts Plotly's raw OHLC plus adjusted-close
source columns onto one adjusted price basis before supplying those facts to the
existing contracts.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference" / "standard_chart"
SOURCE_CSV = REFERENCE_DIR / "finance-charts-apple.csv"
SOURCE_METADATA = REFERENCE_DIR / "source.json"
EXECUTIONS_CSV = REFERENCE_DIR / "simulated-executions.csv"
OUTPUT_PATH = PROJECT_ROOT / "apps" / "desktop" / "src" / "generated" / "standard-chart-demo.json"

INITIAL_CASH = 100_000.0
CALCULATION_CODE_VERSION = "standard-chart-demo-v1"
SOURCE_INSTRUMENT_ID = "AAPL"
REPLAY_INSTRUMENT_ID = "SYN_AAPL_HISTORY"
SUBJECT_ID = "demo-user:standard-chart"
ACCOUNT_ID = "demo-account:standard-chart"
# Independently hand-calculated from the six fixed simulated fills and $6 fees.
EXPECTED_NET_PNL = -81.68892

sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_desktop_demo_evidence import (  # noqa: E402
    _json_value,
    _position_episode_entry,
    _position_episode_story,
)
from src.episodes.position_episode import build_position_episode_lifecycle  # noqa: E402


def _read_metadata() -> dict[str, str]:
    metadata = json.loads(SOURCE_METADATA.read_text(encoding="utf-8"))
    required = {
        "source_url",
        "source_sha256",
        "source_version",
        "source_commit",
        "license",
        "license_url",
    }
    missing = required.difference(metadata)
    if missing:
        raise RuntimeError(f"Source metadata is missing {sorted(missing)}")
    return {key: str(metadata[key]) for key in required}


def _verified_source_frame(metadata: dict[str, str]) -> pd.DataFrame:
    raw_bytes = SOURCE_CSV.read_bytes()
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha != metadata["source_sha256"]:
        raise RuntimeError(
            "Pinned Plotly source SHA-256 does not match source.json: "
            f"expected {metadata['source_sha256']}, got {actual_sha}"
        )
    source = pd.read_csv(BytesIO(raw_bytes))
    required = {
        "Date",
        "AAPL.Open",
        "AAPL.High",
        "AAPL.Low",
        "AAPL.Close",
        "AAPL.Volume",
        "AAPL.Adjusted",
    }
    missing = required.difference(source.columns)
    if missing:
        raise RuntimeError(f"Pinned Plotly source is missing {sorted(missing)}")
    source["Date"] = pd.to_datetime(source["Date"], errors="raise")
    if source["Date"].duplicated().any():
        raise RuntimeError("Pinned Plotly source must have unique session dates")
    price_columns = ("AAPL.Open", "AAPL.High", "AAPL.Low", "AAPL.Close", "AAPL.Adjusted")
    for column in price_columns:
        source[column] = pd.to_numeric(source[column], errors="raise")
        if not source[column].map(lambda value: math.isfinite(float(value)) and value > 0).all():
            raise RuntimeError(f"Pinned Plotly source has invalid {column} values")
    source["AAPL.Volume"] = pd.to_numeric(source["AAPL.Volume"], errors="raise")
    if not source["AAPL.Volume"].map(
        lambda value: math.isfinite(float(value)) and value >= 0 and float(value).is_integer()
    ).all():
        raise RuntimeError("Pinned Plotly source has invalid AAPL.Volume values")
    source = source.loc[source["Date"].dt.year == 2016].copy()
    if (
        source.empty
        or not source["Date"].is_monotonic_increasing
        or not source["Date"].is_unique
    ):
        raise RuntimeError("2016 source sessions must be present and chronological")
    return source


def _adjusted_market_frame(source: pd.DataFrame, metadata: dict[str, str]) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    raw_close = pd.to_numeric(source["AAPL.Close"], errors="raise")
    adjusted_close = pd.to_numeric(source["AAPL.Adjusted"], errors="raise")
    if (raw_close <= 0).any() or (adjusted_close <= 0).any():
        raise RuntimeError("Pinned Plotly source has a non-positive close")
    factor = adjusted_close / raw_close
    market = pd.DataFrame(
        {
            "date": source["Date"],
            "instrument": REPLAY_INSTRUMENT_ID,
            "close": adjusted_close,
            "price_type": "adjusted_close",
            "data_source": metadata["source_url"],
            "data_version": metadata["source_version"],
            "is_synthetic": False,
        }
    )
    bars: list[dict[str, object]] = []
    for index, row in source.iterrows():
        current_factor = float(factor.loc[index])
        bars.append(
            {
                "date": pd.Timestamp(row["Date"]).strftime("%Y-%m-%d"),
                "open": float(row["AAPL.Open"]) * current_factor,
                "high": float(row["AAPL.High"]) * current_factor,
                "low": float(row["AAPL.Low"]) * current_factor,
                "close": float(row["AAPL.Adjusted"]),
                "volume": int(row["AAPL.Volume"]),
                "amount": None,
            }
        )
    return market, bars


def _simulated_executions(market: pd.DataFrame) -> pd.DataFrame:
    executions = pd.read_csv(EXECUTIONS_CSV)
    executions["event_time"] = pd.to_datetime(executions["event_time"], errors="raise")
    executions["market_date"] = pd.to_datetime(executions["market_date"], errors="raise")
    if tuple(executions["side"]) != ("BUY", "BUY", "BUY", "SELL", "SELL", "SELL"):
        raise RuntimeError("Standard chart ledger must contain the fixed six executions")
    if not executions["symbol"].eq(REPLAY_INSTRUMENT_ID).all():
        raise RuntimeError("Standard chart ledger must use the explicit replay instrument")
    if not executions["subject_id"].eq(SUBJECT_ID).all() or not executions["account_id"].eq(ACCOUNT_ID).all():
        raise RuntimeError("Standard chart ledger subject/account does not match the demo")
    if not executions["event_time"].is_monotonic_increasing:
        raise RuntimeError("Standard chart ledger must preserve chronological order")
    close_by_day = market.set_index("date")["close"]
    for row in executions.itertuples(index=False):
        source_close = float(close_by_day.loc[pd.Timestamp(row.market_date)])
        if float(row.executed_price) != source_close:
            raise RuntimeError(
                f"{row.execution_id} must use its source adjusted close, "
                f"not {row.executed_price}"
            )
    return executions


def build_export() -> dict[str, object]:
    """Return the deterministic standard-chart payload without writing it."""

    metadata = _read_metadata()
    source = _verified_source_frame(metadata)
    market, bars = _adjusted_market_frame(source, metadata)
    executions = _simulated_executions(market)
    as_of = pd.Timestamp(market["date"].max()).normalize() + pd.Timedelta(hours=23, minutes=59)
    lifecycle = build_position_episode_lifecycle(
        executions,
        market,
        subject_id=SUBJECT_ID,
        account_id=ACCOUNT_ID,
        as_of=as_of,
        init_cash=INITIAL_CASH,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    if len(lifecycle.episodes) != 1 or lifecycle.episodes[0].status != "closed":
        raise RuntimeError("Standard chart ledger must produce one closed Episode")
    episode = lifecycle.episodes[0]
    story = _position_episode_story(
        lifecycle,
        executions,
        market,
        episode_id=episode.episode_id,
        subject_id=SUBJECT_ID,
        account_id=ACCOUNT_ID,
        analysis_as_of=as_of,
    )
    actual_pnl = story["episode_outcome"].actual_result.pnl
    if not math.isclose(actual_pnl, EXPECTED_NET_PNL, rel_tol=0.0, abs_tol=1e-8):
        raise RuntimeError(
            "Standard chart replay PnL differs from the fixed ledger expectation: "
            f"expected {EXPECTED_NET_PNL}, got {actual_pnl}"
        )
    entry = _position_episode_entry(
        lifecycle,
        episode_id=episode.episode_id,
        executions=executions,
        market_prices=market,
        outcome_story=story,
    )
    entry["instrument"] = {
        "instrument_id": REPLAY_INSTRUMENT_ID,
        "display_name": "Apple · AAPL",
        "currency": "USD",
        "is_synthetic": True,
        "data_tier": "synthetic",
    }
    return {
        "schema_version": "1",
        "data_tier": "synthetic",
        "market": {
            "instrument_id": SOURCE_INSTRUMENT_ID,
            "replay_instrument_id": REPLAY_INSTRUMENT_ID,
            "display_name": "Apple · AAPL",
            "currency": "USD",
            "price_basis": "source_adjusted",
            "source_url": metadata["source_url"],
            "source_sha256": metadata["source_sha256"],
            "source_version": metadata["source_version"],
            "provenance": (
                "Historical bars are real Plotly-source AAPL observations on the "
                "source adjusted basis.  The displayed OHLC values use the daily "
                "Adjusted/Close factor; the separate replay ledger is simulated."
            ),
            "bars": bars,
        },
        "position_episode_demo": {
            "data_tier": "synthetic",
            "default_episode_id": episode.episode_id,
            "entries": (entry,),
        },
    }


def export_bytes() -> bytes:
    return (
        json.dumps(_json_value(build_export()), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(export_bytes())
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

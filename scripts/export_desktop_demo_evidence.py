"""Export deterministic synthetic EvidenceRecords for the Desktop demo.

The script intentionally delegates every financial result to the existing
vectorbt-backed evidence builders and their Evidence Contract adapters.  It
only prepares the already-checked sample inputs and serializes the results.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "apps" / "desktop" / "src" / "generated" / "backend-demo-evidence.json"
INITIAL_CASH = 100_000.0
CALCULATION_CODE_VERSION = "desktop-demo-evidence-v1"

sys.path.insert(0, str(PROJECT_ROOT))

from src.attribution.exit_timing_evidence import build_exit_timing_evidence  # noqa: E402
from src.attribution.friction_evidence import build_friction_evidence  # noqa: E402
from src.attribution.selection_evidence import build_selection_evidence  # noqa: E402
from src.attribution.sizing_evidence import build_sizing_evidence  # noqa: E402
from src.behavior.disposition_effect import build_disposition_effect_evidence  # noqa: E402
from src.behavior.loss_averaging import build_loss_averaging_evidence  # noqa: E402
from src.behavior.portfolio_concentration import (  # noqa: E402
    build_portfolio_concentration_evidence,
)
from src.behavior.turnover_intensity import build_turnover_intensity_evidence  # noqa: E402
from src.core.portfolio_replay import replay_multi_asset_executions  # noqa: E402
from src.data.csv_importer import load_normalized_csv  # noqa: E402
from src.data.local_market_data_provider import LocalMarketDataProvider  # noqa: E402
from src.evidence.adapters import adapt_evidence  # noqa: E402
from src.episodes.investment_episode import (  # noqa: E402
    from_vectorbt_position_record,
)
from src.history.metric_series import (  # noqa: E402
    build_portfolio_hhi_history,
    build_turnover_history,
)


def _json_value(value: object) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    return value


def _adapt(value: object, subject_id: str):
    return adapt_evidence(
        value,
        subject_id=subject_id,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
    )


def _build_selected_episode(executions: pd.DataFrame):
    symbol = str(executions["symbol"].iat[0])
    valuation_prices = executions.pivot(
        index="event_time",
        columns="symbol",
        values="executed_price",
    )
    portfolio = replay_multi_asset_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )
    records = portfolio.positions.records_readable
    if len(records) != 1:
        raise RuntimeError("Synthetic selected demo must produce exactly one Position")
    episode = from_vectorbt_position_record(records.iloc[0])
    if episode.symbol != symbol:
        raise RuntimeError("Selected Episode symbol does not match executions")
    return episode, valuation_prices


def _build_exit_episode(root: Path):
    rows = pd.read_csv(root / "data" / "sample" / "synthetic_exit_timing_prices.csv")
    rows["date"] = pd.to_datetime(rows["date"])
    symbol = "SYN_EXIT_UP"
    daily_prices = rows.loc[rows["instrument"] == symbol].set_index("date")["close"]
    entry_time = pd.Timestamp("2025-06-01 09:30:00")
    exit_time = pd.Timestamp("2025-06-02 10:05:00")
    valuation_prices = pd.concat(
        [
            pd.Series([float(daily_prices.iloc[0])], index=[entry_time], name=symbol),
            daily_prices.rename(symbol),
            pd.Series([float(daily_prices.iloc[0])], index=[exit_time], name=symbol),
        ]
    ).sort_index().to_frame()
    executions = pd.DataFrame(
        {
            "event_time": [entry_time, exit_time],
            "symbol": [symbol, symbol],
            "side": ["BUY", "SELL"],
            "executed_quantity": [100.0, 100.0],
            "executed_price": [100.0, 99.5],
            "fee": [0.0, 0.0],
            "order_id": ["EXIT-DEMO-1", "EXIT-DEMO-2"],
            "execution_id": ["EXIT-DEMO-1", "EXIT-DEMO-2"],
        }
    )
    portfolio = replay_multi_asset_executions(
        executions,
        valuation_prices,
        init_cash=INITIAL_CASH,
    )
    records = portfolio.positions.records_readable
    if len(records) != 1:
        raise RuntimeError("Synthetic exit demo must produce exactly one Position")
    return from_vectorbt_position_record(records.iloc[0])


def _exit_provider(root: Path, exit_prices: pd.DataFrame) -> LocalMarketDataProvider:
    with tempfile.TemporaryDirectory(prefix="desktop-demo-reference-") as temporary_name:
        temporary_root = Path(temporary_name)
        for name in ("industry_membership.csv", "benchmark_mapping.csv"):
            shutil.copyfile(root / "data" / "reference" / name, temporary_root / name)
        reference_prices = pd.read_csv(root / "data" / "reference" / "prices.csv")
        pd.concat([reference_prices, exit_prices], ignore_index=True).to_csv(
            temporary_root / "prices.csv",
            index=False,
        )
        return LocalMarketDataProvider(temporary_root)


def build_export() -> dict[str, object]:
    sample_executions = load_normalized_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_executions.csv"
    )
    selected_episode, selected_prices = _build_selected_episode(sample_executions)
    reference_provider = LocalMarketDataProvider(PROJECT_ROOT / "data" / "reference")

    selection = build_selection_evidence(selected_episode, reference_provider)
    friction = build_friction_evidence(
        sample_executions,
        selected_prices,
        init_cash=INITIAL_CASH,
    )

    behavior_executions = load_normalized_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_executions.csv"
    )
    behavior_prices = pd.read_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_behavior_prices.csv"
    )
    behavior_price_panel = (
        behavior_prices.assign(date=pd.to_datetime(behavior_prices["date"]))
        .pivot(index="date", columns="instrument", values="close")
        .sort_index(kind="stable")
    )
    sizing_results = build_sizing_evidence(
        behavior_executions,
        behavior_price_panel,
        init_cash=INITIAL_CASH,
    )
    sizing = next(
        (item for item in sizing_results if item.evidence_status == "complete"),
        None,
    )
    if sizing is None:
        raise RuntimeError("Synthetic behavior fixture produced no complete sizing interval")

    turnover = build_turnover_intensity_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )
    concentration = build_portfolio_concentration_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )
    disposition = build_disposition_effect_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )
    loss_averaging = build_loss_averaging_evidence(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
    )

    exit_episode = _build_exit_episode(PROJECT_ROOT)
    exit_price_rows = pd.read_csv(
        PROJECT_ROOT / "data" / "sample" / "synthetic_exit_timing_prices.csv"
    )
    exit = build_exit_timing_evidence(
        exit_episode,
        _exit_provider(PROJECT_ROOT, exit_price_rows),
    )

    behavior_subject = "demo-user:synthetic-behavior"
    records = [
        _adapt(selection, selected_episode.episode_id),
        _adapt(sizing, behavior_subject),
        _adapt(exit, exit_episode.episode_id),
        _adapt(friction, selected_episode.episode_id),
        _adapt(turnover, behavior_subject),
        _adapt(concentration, behavior_subject),
        _adapt(disposition, behavior_subject),
        _adapt(loss_averaging, behavior_subject),
    ]
    turnover_record = next(
        record for record in records if record.metric_id == "mean_daily_turnover"
    )
    hhi_history = build_portfolio_hhi_history(
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
        subject_id=behavior_subject,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    turnover_history = build_turnover_history(
        turnover,
        parent_record=turnover_record,
    )
    return {
        "schema_version": "1",
        "export_version": "desktop-demo-evidence-v1",
        "data_tier": "synthetic",
        "selected_episode": selected_episode,
        "evidence_records": records,
        "historical_series": {
            "portfolio_hhi": hhi_history,
            "turnover": turnover_history,
        },
    }


def main() -> int:
    payload = _json_value(build_export())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Evidence records: {len(payload['evidence_records'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

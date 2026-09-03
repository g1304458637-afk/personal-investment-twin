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
from src.benchmark.peer import build_synthetic_peer_benchmark  # noqa: E402
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
from src.evidence.explainability import (  # noqa: E402
    CALCULATION_TRACE_SCHEMA_VERSION,
    build_explainability_view,
    build_pretrade_hhi_trace,
)
from src.evidence.registry import (  # noqa: E402
    CONCEPT_REGISTRY_REVISION,
    list_concepts,
)
from src.episodes.investment_episode import (  # noqa: E402
    from_vectorbt_position_record,
)
from src.episodes.position_episode import (  # noqa: E402
    PositionEpisodeLifecycle,
    build_position_episode_lifecycle,
)
from src.history.metric_series import (  # noqa: E402
    build_portfolio_hhi_history,
    build_turnover_history,
)
from src.pretrade.impact import (  # noqa: E402
    ProposedTrade,
    simulate_synthetic_trade_impact,
)
from src.twin.state import (  # noqa: E402
    build_historical_twin_snapshots,
    build_twin_metric_comparison,
    build_twin_snapshot,
    latest_twin_snapshot_at,
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


def _position_episode_entry(
    lifecycle: PositionEpisodeLifecycle,
    *,
    episode_id: str,
    market_prices: pd.DataFrame,
) -> dict[str, object]:
    episode = next(item for item in lifecycle.episodes if item.episode_id == episode_id)
    decisions = tuple(
        item for item in lifecycle.decisions if item.episode_id == episode.episode_id
    )
    state_ids = {
        reference
        for decision in decisions
        for reference in (decision.state_before_ref, decision.state_after_ref)
    }
    snapshot = next(
        (
            item
            for item in lifecycle.snapshots
            if item.episode_id == episode.episode_id
        ),
        None,
    )
    if snapshot is not None:
        state_ids.add(snapshot.position_state_ref)
    states = {
        item.state_id: item for item in lifecycle.states if item.state_id in state_ids
    }
    evidence_ids = {
        *episode.evidence_refs,
        *(reference for item in decisions for reference in item.evidence_refs),
    }
    evidence_references = tuple(
        item
        for item in lifecycle.evidence_references
        if item.evidence_id in evidence_ids
    )

    dates = pd.to_datetime(market_prices["date"], errors="raise")
    timeline_end = episode.closed_at or lifecycle.as_of
    price_rows = market_prices.loc[
        (market_prices["instrument"] == episode.instrument_id)
        & (dates.dt.normalize() >= episode.opened_at.normalize())
        & (dates.dt.normalize() <= timeline_end.normalize())
    ].sort_values("date", kind="stable")
    price_points = tuple(
        {
            "observed_at": pd.Timestamp(row["date"]),
            "price": float(row["close"]),
        }
        for _, row in price_rows.iterrows()
    )
    return {
        "episode": episode,
        "snapshot": snapshot,
        "decisions": decisions,
        "states_by_ref": states,
        "evidence_references": evidence_references,
        "price_points": price_points,
    }


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
    incomplete_exit = build_exit_timing_evidence(
        exit_episode,
        _exit_provider(
            PROJECT_ROOT,
            exit_price_rows.loc[
                exit_price_rows["instrument"] == exit_episode.symbol
            ].iloc[:9].copy(),
        ),
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
    selection_record = next(
        record for record in records if record.metric_id == "selection_episode_asset_return"
    )
    friction_record = next(
        record
        for record in records
        if record.metric_id == "recorded_trading_friction_comparison"
    )
    selected_market_prices = pd.read_csv(PROJECT_ROOT / "data" / "reference" / "prices.csv")
    selected_lifecycle = build_position_episode_lifecycle(
        sample_executions,
        selected_market_prices,
        subject_id="demo-user:synthetic-selected-episode",
        account_id="demo-account:selected",
        as_of=pd.Timestamp("2025-05-20 23:59:00"),
        init_cash=INITIAL_CASH,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
        episode_evidence={
            str(sample_executions.iloc[0]["execution_id"]): (
                selection_record,
                friction_record,
            )
        },
    )
    selected_position_episode = selected_lifecycle.episodes[0]

    behavior_lifecycle = build_position_episode_lifecycle(
        behavior_executions,
        behavior_prices,
        subject_id=behavior_subject,
        account_id="demo-account:behavior",
        as_of=pd.Timestamp("2025-01-08 23:59:00"),
        init_cash=INITIAL_CASH,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    open_position_episode = next(
        item
        for item in behavior_lifecycle.episodes
        if item.instrument_id == "SYN_WIN_SOLD"
    )
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
    histories = (hhi_history, turnover_history)
    snapshot_at = latest_twin_snapshot_at(records, histories)
    current_twin = build_twin_snapshot(
        records,
        histories,
        subject_id=behavior_subject,
        snapshot_at=snapshot_at,
        data_tier="synthetic",
    )
    historical_twins = build_historical_twin_snapshots(
        records,
        histories,
        subject_id=behavior_subject,
        snapshot_at=snapshot_at,
        data_tier="synthetic",
    )
    peer_benchmark = build_synthetic_peer_benchmark(
        subject_id=behavior_subject,
        subject_executions=behavior_executions,
        market_prices=behavior_prices,
        init_cash=INITIAL_CASH,
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    pretrade_demo = simulate_synthetic_trade_impact(
        ProposedTrade(
            subject_id=behavior_subject,
            proposed_time=pd.Timestamp("2025-01-08 23:59:00"),
            symbol="SYN_PAPER_WIN",
            side="BUY",
            quantity=200.0,
            execution_price=13.0,
            fees=5.0,
        ),
        behavior_executions,
        behavior_prices,
        init_cash=INITIAL_CASH,
        hhi_history=hhi_history,
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    if pretrade_demo.simulation_status != "complete":
        raise RuntimeError(
            f"Synthetic pre-trade demo failed: {pretrade_demo.simulation_reason}"
        )
    evidence_by_metric = {record.metric_id: record for record in records}
    explainability_sources = (
        (evidence_by_metric["portfolio_concentration_hhi"], concentration),
        (evidence_by_metric["mean_daily_turnover"], turnover),
        (evidence_by_metric["loss_averaging_event_rate"], loss_averaging),
        (evidence_by_metric["sizing_equal_weight_comparison"], sizing),
        (evidence_by_metric["exit_timing_post_exit_asset_return"], exit),
        (_adapt(incomplete_exit, exit_episode.episode_id), incomplete_exit),
    )
    explainability_views = tuple(
        build_explainability_view(record, source)
        for record, source in explainability_sources
    )
    pretrade_trace = build_pretrade_hhi_trace(
        pretrade_demo,
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    peer_metric_keys = {
        "portfolio_concentration_hhi": "portfolio_hhi",
        "mean_daily_turnover": "turnover",
        "closed_episode_count": "closed_episode_count",
    }
    return {
        "schema_version": "1",
        "export_version": "desktop-demo-evidence-v1",
        "data_tier": "synthetic",
        "explainability": {
            "schema_version": CALCULATION_TRACE_SCHEMA_VERSION,
            "concept_registry_revision": CONCEPT_REGISTRY_REVISION,
            "concepts": list_concepts(),
            "evidence_views": explainability_views,
            "pretrade_trace": pretrade_trace,
        },
        "selected_episode": selected_episode,
        "evidence_records": records,
        "historical_series": {
            "portfolio_hhi": hhi_history,
            "turnover": turnover_history,
        },
        "twin": {
            "data_tier": "synthetic",
            "current_snapshot": current_twin,
            "historical_snapshots": historical_twins,
            "comparison": {
                "portfolio_hhi": build_twin_metric_comparison(hhi_history),
                "turnover": build_twin_metric_comparison(turnover_history),
            },
        },
        "peer_benchmark": {
            "cohort": peer_benchmark.cohort,
            "cohort_n": peer_benchmark.cohort_n,
            "metrics": {
                peer_metric_keys[result.metric_id]: result
                for result in peer_benchmark.metrics
            },
        },
        "pretrade_demo": pretrade_demo,
        "position_episode_demo": {
            "data_tier": "synthetic",
            "default_episode_id": selected_position_episode.episode_id,
            "entries": (
                _position_episode_entry(
                    selected_lifecycle,
                    episode_id=selected_position_episode.episode_id,
                    market_prices=selected_market_prices,
                ),
                _position_episode_entry(
                    behavior_lifecycle,
                    episode_id=open_position_episode.episode_id,
                    market_prices=behavior_prices,
                ),
            ),
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

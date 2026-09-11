"""Build the single product showcase using existing financial engines.

Only source facts are authored in src.demo.showcase. This exporter composes
existing Evidence, lifecycle, history, comparison and pre-trade builders. It
does not relabel any legacy fixture or migrate historical Evidence.
"""
from __future__ import annotations

import dataclasses
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.export_desktop_demo_evidence import _json_value, _position_episode_entry, _position_episode_story
from src.attribution.exit_timing_evidence import build_exit_timing_evidence
from src.attribution.friction_evidence import build_friction_evidence
from src.attribution.selection_evidence import build_selection_evidence
from src.attribution.sizing_evidence import build_sizing_evidence
from src.behavior.disposition_effect import build_disposition_effect_evidence
from src.behavior.loss_averaging import build_loss_averaging_evidence
from src.behavior.portfolio_concentration import build_portfolio_concentration_evidence
from src.behavior.replay_state import prepare_behavior_replay
from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.cohort.engine import build_peer_benchmark_results
from src.cohort.models import PeerMetricValue
from src.data.local_market_data_provider import LocalMarketDataProvider
from src.demo.showcase import ACCOUNT_ID, AS_OF, END, INITIAL_CASH, NAMES, START, SUBJECT_ID, VERSION, showcase_inputs, source_fingerprint
from src.demo.showcase_comparison import build_showcase_comparison
from src.demo.showcase_runtime import build_showcase_pair, showcase_cohort_definition, simulate_showcase_trade
from src.episodes.investment_episode import from_vectorbt_position_record
from src.episodes.position_episode import build_position_episode_lifecycle
from src.evidence.adapters import adapt_evidence
from src.evidence.explainability import CALCULATION_TRACE_SCHEMA_VERSION, build_explainability_view, build_pretrade_hhi_trace
from src.evidence.registry import CONCEPT_REGISTRY_REVISION, list_concepts
from src.history.metric_series import build_portfolio_hhi_history_with_records, build_turnover_history
from src.pretrade.impact import ProposedTrade
from src.self_baseline.core import build_self_baseline_summary
from src.twin.state import build_historical_twin_snapshots, build_twin_metric_comparison, build_twin_snapshot_from_facts, latest_twin_snapshot_at

OUTPUT_PATH = ROOT / "apps/desktop/src/generated/showcase-demo.json"


def _adapt(source):
    return adapt_evidence(source, subject_id=SUBJECT_ID, data_tier="synthetic", calculation_code_version=VERSION)


def _provider(prices: pd.DataFrame) -> LocalMarketDataProvider:
    # The legacy selection method's fixed CSI300 slot receives an explicitly
    # synthetic benchmark, NOT actual CSI300 history. Its source name and tier
    # survive the Evidence adapter; all other showcase comparisons use exactly
    # the same SYN_MARKET observations.
    benchmark = prices.loc[prices.instrument == "SYN_MARKET"].assign(instrument="CSI300")
    with tempfile.TemporaryDirectory(prefix="toujing-showcase-reference-") as directory:
        root = Path(directory)
        pd.concat([prices, benchmark], ignore_index=True).to_csv(root / "prices.csv", index=False)
        pd.DataFrame([
            dict(symbol=symbol, industry_id="SHOWCASE_INDUSTRY", industry_name="Simulated industry",
                 valid_from=START, valid_to=None, classification="synthetic_showcase",
                 data_source=VERSION, data_version="1", is_synthetic=True)
            for symbol in NAMES if symbol not in {"cash", "SYN_INDUSTRIAL"}
        ]).to_csv(root / "industry_membership.csv", index=False)
        pd.DataFrame([
            dict(benchmark_id="CSI300", benchmark_name="Simulated broad-market benchmark (not actual CSI300)", benchmark_type="market"),
            dict(benchmark_id="SHOWCASE_INDUSTRY", benchmark_name="Simulated sector benchmark", benchmark_type="industry"),
        ]).to_csv(root / "benchmark_mapping.csv", index=False)
        return LocalMarketDataProvider(root)


def build_export() -> dict[str, object]:
    executions, prices = showcase_inputs()
    replay = prepare_behavior_replay(executions, prices, init_cash=INITIAL_CASH)
    lifecycle_args = dict(subject_id=SUBJECT_ID, account_id=ACCOUNT_ID, as_of=AS_OF,
                          init_cash=INITIAL_CASH, data_tier="synthetic", calculation_code_version=VERSION)
    lifecycle = build_position_episode_lifecycle(executions, prices, **lifecycle_args)
    primary = next(e for e in lifecycle.episodes if e.instrument_id == "SYN_GROWTH" and e.status == "closed")
    raw = replay.portfolio.positions.records_readable
    primary_record = raw.loc[raw["Position Id"] == primary.vectorbt_position_record_id].iloc[0]
    selected = dataclasses.replace(from_vectorbt_position_record(primary_record), episode_id=primary.episode_id)
    provider = _provider(prices)
    selection = build_selection_evidence(selected, provider)
    friction = build_friction_evidence(executions, replay.valuation_prices, init_cash=INITIAL_CASH)
    sizing = next(item for item in build_sizing_evidence(executions, replay.valuation_prices, init_cash=INITIAL_CASH)
                  if item.evidence_status == "complete")
    exit_source = build_exit_timing_evidence(selected, provider)
    turnover = build_turnover_intensity_evidence(executions, prices, init_cash=INITIAL_CASH)
    hhi = build_portfolio_concentration_evidence(executions, prices, init_cash=INITIAL_CASH)
    disposition = build_disposition_effect_evidence(executions, prices, init_cash=INITIAL_CASH)
    loss = build_loss_averaging_evidence(executions, prices, init_cash=INITIAL_CASH)
    sources = (selection, sizing, exit_source, friction, turnover, hhi, disposition, loss)
    records = tuple(_adapt(item) for item in sources)
    by_metric = {record.metric_id: record for record in records}
    exit_record = by_metric["exit_timing_post_exit_asset_return"]
    lifecycle = build_position_episode_lifecycle(executions, prices, **lifecycle_args,
        episode_evidence={primary.opening_execution_id: (records[0], exit_record)},
        decision_evidence={primary.closing_execution_id: (exit_record,)})

    entries = []
    charts = []
    for episode in lifecycle.episodes:
        # Exit Evidence from the primary closed Episode is only attached there.
        story = _position_episode_story(lifecycle, executions, prices, episode_id=episode.episode_id,
            subject_id=SUBJECT_ID, account_id=ACCOUNT_ID, analysis_as_of=AS_OF,
            exit_evidence=exit_record if episode.episode_id == primary.episode_id else None)
        entry = _position_episode_entry(lifecycle, episode_id=episode.episode_id,
                                       executions=executions, market_prices=prices, outcome_story=story)
        entry["instrument"] = dict(instrument_id=episode.instrument_id,
            display_name=NAMES[episode.instrument_id]["en"], currency="CNY", data_tier="synthetic", is_synthetic=True)
        entries.append(entry)
        bars = prices.loc[prices.instrument == episode.instrument_id]
        charts.append(dict(schema_version="1", data_tier="synthetic",
            market=dict(instrument_id=episode.instrument_id, replay_instrument_id=episode.instrument_id,
                display_name=NAMES[episode.instrument_id]["en"], currency="CNY", price_basis="synthetic_unadjusted",
                source_url="synthetic://toujing/showcase/v1",
                source_version=VERSION, source_sha256=source_fingerprint(),
                provenance="Authored synthetic OHLCV and executions; not real securities or an exchange calendar.",
                bars=[dict(date=row.date.date().isoformat(), open=row.open, high=row.high, low=row.low,
                           close=row.close, volume=row.volume, amount=None) for row in bars.itertuples()]),
            position_episode_demo=dict(data_tier="synthetic", default_episode_id=episode.episode_id, entries=(entry,))))

    history, history_records = build_portfolio_hhi_history_with_records(executions, prices,
        init_cash=INITIAL_CASH, subject_id=SUBJECT_ID, data_tier="synthetic", calculation_code_version=VERSION)
    turnover_history = build_turnover_history(turnover, parent_record=by_metric["mean_daily_turnover"])
    histories = (history, turnover_history)
    twin = build_twin_snapshot_from_facts(executions, prices, records, histories, **lifecycle_args)
    catalog = {r.evidence_id: r for r in (*records, *history_records)}
    self_baseline = build_self_baseline_summary(twin, histories, tuple(catalog.values()))
    historical_twins = build_historical_twin_snapshots(records, histories, subject_id=SUBJECT_ID,
        snapshot_at=latest_twin_snapshot_at(records, histories, subject_id=SUBJECT_ID),
        data_tier="synthetic", calculation_code_version=VERSION)
    pretrade = simulate_showcase_trade(ProposedTrade(SUBJECT_ID, AS_OF, "SYN_GROWTH", "BUY", 300, 14.4, 5))
    if pretrade.simulation_status != "complete":
        raise ValueError(f"showcase_pretrade_unavailable: {pretrade.simulation_reason}")
    # No sampled population is part of this coherent account example. The
    # legacy peer route receives an honest insufficient result, not old peers.
    definition = showcase_cohort_definition()
    metric_sources = (
        ("portfolio_concentration_hhi", by_metric["portfolio_concentration_hhi"].value, by_metric["portfolio_concentration_hhi"].evidence_id),
        ("mean_daily_turnover", by_metric["mean_daily_turnover"].value, by_metric["mean_daily_turnover"].evidence_id),
        ("closed_episode_count", float(sum(e.status == "closed" for e in lifecycle.episodes)), f"{VERSION}:lifecycle"),
    )
    peer_results = build_peer_benchmark_results(definition, (), (), tuple(
        PeerMetricValue(SUBJECT_ID, key, value, "complete", ref, pd.Timestamp(END)) for key, value, ref in metric_sources
    ), subject_id=SUBJECT_ID)
    keys = {"portfolio_concentration_hhi": "portfolio_hhi", "mean_daily_turnover": "turnover", "closed_episode_count": "closed_episode_count"}
    explain_sources = (hhi, turnover, loss, sizing, exit_source)
    comparison, pair_mapping = build_showcase_pair()
    return dict(schema_version="1", export_version=VERSION, data_tier="synthetic",
        showcase=dict(subject_id=SUBJECT_ID, account_id=ACCOUNT_ID,
            display_name={"zh": "我的年度投资 · 示例", "en": "My investment year · Example"},
            data_tier="synthetic", as_of=AS_OF, source_version=VERSION, input_sha256=source_fingerprint(),
            calendar="declared_synthetic_weekdays_not_exchange_calendar", initial_cash=INITIAL_CASH,
            execution_count=len(executions), names=NAMES,
            limitations=("All identities, executions, prices and fund disclosures are simulated.",
                         "One reference portfolio is not a professional track record or a peer population.",
                         "Corporate actions, broker authorization and predictive results are not demonstrated.")),
        selected_episode=selected, evidence_records=records,
        historical_series=dict(portfolio_hhi=history, turnover=turnover_history),
        twin=dict(data_tier="synthetic", current_snapshot=twin, historical_snapshots=historical_twins,
            comparison=dict(portfolio_hhi=build_twin_metric_comparison(history), turnover=build_twin_metric_comparison(turnover_history))),
        self_baseline=self_baseline,
        investments=dict(subject_id=SUBJECT_ID, as_of=AS_OF, data_tier="synthetic",
            portfolio_state_status=twin.portfolio_state.status, portfolio_state_reason=twin.portfolio_state.reason,
            summary=dict(open_episode_count=twin.data_quality_summary.open_episode_count,
                         closed_episode_count=twin.data_quality_summary.closed_episode_count,
                         current_position_count=len(twin.portfolio_state.positions)),
            open_episode_ids=tuple(e.episode_id for e in twin.episode_refs.open),
            closed_episode_ids=tuple(e.episode_id for e in twin.episode_refs.closed)),
        position_episode_demo=dict(data_tier="synthetic", default_episode_id=primary.episode_id, entries=entries),
        charts=charts, comparison_research=build_showcase_comparison(),
        same_stock_compare_demo=comparison, same_stock_identity_mapping=pair_mapping,
        pretrade_demo=pretrade, peer_benchmark=dict(cohort=definition, cohort_n=0,
            metrics={keys[r.metric_id]: r for r in peer_results}),
        explainability=dict(schema_version=CALCULATION_TRACE_SCHEMA_VERSION, concept_registry_revision=CONCEPT_REGISTRY_REVISION,
            concepts=list_concepts(), evidence_views=tuple(build_explainability_view(_adapt(source), source) for source in explain_sources),
            pretrade_trace=build_pretrade_hhi_trace(pretrade, calculation_code_version=VERSION)))


def export_bytes() -> bytes:
    return (json.dumps(_json_value(build_export()), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(export_bytes())
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

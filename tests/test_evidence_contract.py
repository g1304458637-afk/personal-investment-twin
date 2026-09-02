import copy
import json
from dataclasses import FrozenInstanceError, replace

import pandas as pd
import pytest

from src.attribution.decision_evidence_statistics import (
    DecisionObservation,
    build_decision_evidence_statistics,
)
from src.attribution.exit_timing_evidence import ExitTimingEvidence
from src.attribution.friction_evidence import FrictionEvidence
from src.attribution.selection_evidence import (
    BenchmarkProvenance,
    IndustryProvenance,
    PriceProvenance,
    SelectionEvidence,
)
from src.attribution.sizing_evidence import SizingDecisionEvidence
from src.behavior.disposition_effect import (
    LIMITATION as DISPOSITION_LIMITATION,
    METHOD_ID as DISPOSITION_METHOD_ID,
    METHOD_SOURCE as DISPOSITION_SOURCE,
    SAMPLE_BASIS as DISPOSITION_SAMPLE_BASIS,
    DispositionEffectEvidence,
)
from src.behavior.loss_averaging import (
    LIMITATION as LOSS_LIMITATION,
    METHOD_ID as LOSS_METHOD_ID,
    METHOD_SOURCE as LOSS_SOURCE,
    SAMPLE_BASIS as LOSS_SAMPLE_BASIS,
    LossAveragingEvent,
    LossAveragingEvidence,
)
from src.behavior.portfolio_concentration import (
    LIMITATION as CONCENTRATION_LIMITATION,
    METHOD_ID as CONCENTRATION_METHOD_ID,
    METHOD_SOURCE as CONCENTRATION_SOURCE,
    SAMPLE_BASIS as CONCENTRATION_SAMPLE_BASIS,
    PortfolioConcentrationEvidence,
)
from src.behavior.turnover_intensity import (
    LIMITATION as TURNOVER_LIMITATION,
    METHOD_ID as TURNOVER_METHOD_ID,
    METHOD_SOURCE as TURNOVER_SOURCE,
    SAMPLE_BASIS as TURNOVER_SAMPLE_BASIS,
    DailyTurnoverObservation,
    TurnoverIntensityEvidence,
)
from src.evidence.adapters import (
    adapt_benchmark_provenance,
    adapt_decision_evidence_statistics,
    adapt_disposition_effect_evidence,
    adapt_evidence,
    adapt_exit_timing_evidence,
    adapt_friction_evidence,
    adapt_industry_provenance,
    adapt_loss_averaging_evidence,
    adapt_portfolio_concentration_evidence,
    adapt_price_provenance,
    adapt_selection_evidence,
    adapt_sizing_evidence,
    adapt_turnover_intensity_evidence,
)
from src.evidence.contracts import canonical_json_bytes, create_evidence_record
from src.evidence.registry import (
    METHOD_VERSION_V1,
    SELECTION_METHOD_ID,
    get_method_definition,
    list_method_definitions,
)


SUBJECT_ID = "investor:test"
CODE_VERSION = "d0f0ad9"
START = pd.Timestamp("2025-01-02 09:30")
END = pd.Timestamp("2025-01-08 15:00")


@pytest.fixture
def price_provenance() -> PriceProvenance:
    return PriceProvenance(
        instrument="600000.SH",
        data_source="local_fixture",
        data_version="v1",
        as_of=END,
        price_type="synthetic",
        is_synthetic=True,
    )


@pytest.fixture
def benchmark_provenance() -> BenchmarkProvenance:
    return BenchmarkProvenance(
        benchmark_id="CSI300",
        benchmark_name="CSI 300",
        benchmark_type="market",
        data_source="local_fixture",
        data_version="v1",
        as_of=END,
        price_type="synthetic",
        is_synthetic=True,
    )


@pytest.fixture
def industry_provenance() -> IndustryProvenance:
    return IndustryProvenance(
        industry_id="SYN_BANKS",
        industry_name="Synthetic Banks",
        as_of=START,
        classification="synthetic_v1",
        data_source="local_fixture",
        data_version="v1",
        is_synthetic=True,
    )


@pytest.fixture
def selection(
    price_provenance,
    benchmark_provenance,
    industry_provenance,
) -> SelectionEvidence:
    return SelectionEvidence(
        episode_id="ep_600000.SH_0",
        symbol="600000.SH",
        start_time=START,
        end_time=END,
        asset_return=0.30,
        market_benchmark_id="CSI300",
        market_benchmark_name="CSI 300",
        market_benchmark_return=0.08,
        market_comparison="outperformed",
        industry_id="SYN_BANKS",
        industry_name="Synthetic Banks",
        industry_as_of_date=START,
        industry_benchmark_id="SYN_BANKS",
        industry_benchmark_name="Synthetic Banks Index",
        industry_benchmark_return=0.25,
        industry_comparison="outperformed",
        evidence_status="complete",
        evidence_reason=None,
        asset_provenance=price_provenance,
        industry_provenance=industry_provenance,
        benchmark_provenance=(benchmark_provenance,),
    )


@pytest.fixture
def sizing() -> SizingDecisionEvidence:
    return SizingDecisionEvidence(
        decision_time=START,
        interval_end_time=END,
        active_assets=("A", "B"),
        actual_weights={"A": 0.6, "B": 0.4},
        baseline_weights={"A": 0.5, "B": 0.5},
        risky_exposure=1.0,
        actual_start_value=100_000.0,
        baseline_start_value=100_000.0,
        actual_end_value=110_000.0,
        baseline_end_value=108_000.0,
        comparison="outperformed_baseline",
        evidence_status="complete",
        evidence_reason=None,
    )


@pytest.fixture
def exit_evidence(price_provenance) -> ExitTimingEvidence:
    return ExitTimingEvidence(
        episode_id="ep_600000.SH_0",
        symbol="600000.SH",
        actual_exit_time=START,
        actual_exit_price=13.0,
        policy_id="hold_20_sessions_v1",
        policy_sessions=20,
        counterfactual_exit_time=END,
        exit_session_market_price=13.0,
        counterfactual_exit_price=14.0,
        post_exit_asset_return=0.0769230769,
        comparison="actual_exit_underperformed_hold_baseline",
        evidence_status="complete",
        evidence_reason=None,
        provenance=price_provenance,
        counterfactual_notice="Fixed retrospective 20-session policy.",
    )


@pytest.fixture
def friction() -> FrictionEvidence:
    return FrictionEvidence(
        start_time=START,
        end_time=END,
        execution_count=4,
        recorded_fee_total=30.9,
        actual_end_value=103_369.1,
        zero_recorded_fee_end_value=103_400.0,
        comparison="lower_than_zero_fee_baseline",
        evidence_status="complete",
        evidence_reason=None,
        included_costs=("recorded_fee",),
        excluded_costs=(
            "unrecorded_tax",
            "slippage",
            "bid_ask_spread",
            "market_impact",
            "opportunity_cost",
        ),
    )


@pytest.fixture
def behavior_evidence(price_provenance):
    provenance = (price_provenance,)
    turnover = TurnoverIntensityEvidence(
        method_id=TURNOVER_METHOD_ID,
        method_source=TURNOVER_SOURCE,
        sample_basis=TURNOVER_SAMPLE_BASIS,
        observation_count=2,
        daily_turnover=(
            DailyTurnoverObservation(START.normalize(), 1_000.0, 100_000.0, 0.01),
            DailyTurnoverObservation(END.normalize(), 500.0, 101_000.0, 0.004950495),
        ),
        mean_daily_turnover=0.0074752475,
        total_traded_value=1_500.0,
        observation_days=2,
        denominator="portfolio_value",
        evidence_status="complete",
        evidence_reason=None,
        provenance=provenance,
        synthetic_provenance_present=True,
        limitation=TURNOVER_LIMITATION,
    )
    concentration = PortfolioConcentrationEvidence(
        method_id=CONCENTRATION_METHOD_ID,
        method_source=CONCENTRATION_SOURCE,
        sample_basis=CONCENTRATION_SAMPLE_BASIS,
        observation_count=1,
        as_of_time=END,
        active_asset_count=2,
        top1_weight=0.6,
        top3_weight=1.0,
        hhi=0.52,
        evidence_status="complete",
        evidence_reason=None,
        provenance=provenance,
        synthetic_provenance_present=True,
        limitation=CONCENTRATION_LIMITATION,
    )
    disposition = DispositionEffectEvidence(
        method_id=DISPOSITION_METHOD_ID,
        method_source=DISPOSITION_SOURCE,
        sample_basis=DISPOSITION_SAMPLE_BASIS,
        observation_count=7,
        realized_gains=1,
        paper_gains=2,
        realized_losses=1,
        paper_losses=3,
        neutral_observations=0,
        pgr=1 / 3,
        plr=1 / 4,
        disposition_effect=1 / 12,
        eligible_sale_events=2,
        evidence_status="complete",
        evidence_reason=None,
        provenance=provenance,
        synthetic_provenance_present=True,
        limitation=DISPOSITION_LIMITATION,
    )
    loss = LossAveragingEvidence(
        method_id=LOSS_METHOD_ID,
        method_source=LOSS_SOURCE,
        sample_basis=LOSS_SAMPLE_BASIS,
        observation_count=1,
        events=(
            LossAveragingEvent(
                event_time=END,
                symbol="600000.SH",
                pre_trade_position=100.0,
                pre_trade_avg_cost=10.0,
                execution_price=9.0,
                added_quantity=50.0,
                eligible_event=True,
                event_detected=True,
            ),
        ),
        eligible_add_events=1,
        loss_averaging_events=1,
        event_rate=1.0,
        evidence_status="complete",
        evidence_reason=None,
        provenance=provenance,
        synthetic_provenance_present=True,
        limitation=LOSS_LIMITATION,
    )
    return turnover, concentration, disposition, loss


@pytest.fixture
def statistics():
    return build_decision_evidence_statistics(
        [
            DecisionObservation("sizing", START, "sizing:1", "positive"),
            DecisionObservation("sizing", END, "sizing:2", "negative"),
            DecisionObservation("sizing", END, "sizing:3", "matched"),
        ]
    )


def _record(**overrides):
    values = {
        "subject_id": SUBJECT_ID,
        "metric_id": "metric",
        "evidence_kind": "test_evidence",
        "method_id": "method_v1",
        "method_version": "1",
        "observation_start": START,
        "observation_end": END,
        "as_of": END,
        "value": 0.25,
        "numerator": 1,
        "denominator": 4,
        "observation_count": 4,
        "ci_lower": None,
        "ci_upper": None,
        "evidence_status": "complete",
        "evidence_reason": None,
        "provenance": (),
        "data_tier": "demo",
        "calculation_code_version": CODE_VERSION,
        "limitations": (),
        "attributes": {"display": "stable"},
        "identity_attributes": {"b": 2, "a": 1},
    }
    values.update(overrides)
    return create_evidence_record(**values)


def test_evidence_record_is_deeply_immutable():
    record = _record(attributes={"nested": {"items": [1, 2]}})

    with pytest.raises(FrozenInstanceError):
        record.value = 0.5
    with pytest.raises(TypeError):
        record.attributes["new"] = "value"
    with pytest.raises(TypeError):
        record.attributes["nested"]["new"] = "value"


def test_canonical_serialization_is_deterministic_and_compact():
    first = {"z": 1, "nested": {"b": 2, "a": 1}, "a": [True, None]}
    second = {"a": [True, None], "nested": {"a": 1, "b": 2}, "z": 1}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_json_bytes(first) == (
        b'{"a":[true,null],"nested":{"a":1,"b":2},"z":1}'
    )


def test_identical_identity_and_different_dict_order_have_stable_id():
    first = _record(identity_attributes={"outer": {"b": 2, "a": 1}})
    second = _record(identity_attributes={"outer": {"a": 1, "b": 2}})

    assert first.evidence_id == second.evidence_id


def test_display_only_attributes_do_not_change_evidence_id():
    first = _record(attributes={"display_label": "First"})
    second = _record(attributes={"display_label": "Renamed"})

    assert first.evidence_id == second.evidence_id


def test_selected_identity_attributes_change_evidence_id():
    first = _record(identity_attributes={"stable_fact": 1})
    second = _record(identity_attributes={"stable_fact": 2})

    assert first.evidence_id != second.evidence_id


@pytest.mark.parametrize(
    "override",
    [
        {"subject_id": "investor:other"},
        {"method_version": "2"},
        {"calculation_code_version": "different-code-version"},
        {"observation_end": pd.Timestamp("2025-01-09")},
    ],
)
def test_identity_fields_change_evidence_id(override):
    assert _record().evidence_id != _record(**override).evidence_id


def test_none_is_preserved_instead_of_fabricated_as_zero():
    record = _record(
        value=None,
        numerator=None,
        denominator=None,
        observation_count=None,
    )

    assert record.value is None
    assert record.numerator is None
    assert record.denominator is None
    assert record.observation_count is None


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("complete", None),
        ("partial", "Open episode evaluated through valuation_time"),
        ("insufficient_evidence", "Missing benchmark data"),
    ],
)
def test_selection_adapter_preserves_supported_statuses(selection, status, reason):
    source = replace(
        selection,
        evidence_status=status,
        evidence_reason=reason,
        asset_return=None if status == "insufficient_evidence" else 0.30,
    )

    record = adapt_selection_evidence(
        source,
        subject_id=SUBJECT_ID,
        data_tier="demo",
        calculation_code_version=CODE_VERSION,
    )

    assert record.evidence_status == status
    assert record.evidence_reason == reason


@pytest.mark.parametrize("data_tier", ["production", "authorized_beta"])
def test_synthetic_provenance_hard_fails_restricted_tiers(
    selection,
    data_tier,
):
    with pytest.raises(ValueError, match="Synthetic provenance"):
        adapt_selection_evidence(
            selection,
            subject_id=SUBJECT_ID,
            data_tier=data_tier,
            calculation_code_version=CODE_VERSION,
        )


def test_price_provenance_mapping_is_complete(price_provenance):
    result = adapt_price_provenance(price_provenance)

    assert result.source_type == "price_series"
    assert result.source_name == price_provenance.data_source
    assert result.data_version == price_provenance.data_version
    assert result.as_of == price_provenance.as_of
    assert result.price_type == price_provenance.price_type
    assert result.is_synthetic is True
    assert result.instrument == price_provenance.instrument


def test_benchmark_provenance_mapping_is_complete(benchmark_provenance):
    result = adapt_benchmark_provenance(benchmark_provenance)

    assert result.source_type == "benchmark_price_series"
    assert result.source_name == benchmark_provenance.data_source
    assert result.data_version == benchmark_provenance.data_version
    assert result.as_of == benchmark_provenance.as_of
    assert result.price_type == benchmark_provenance.price_type
    assert result.is_synthetic is True
    assert result.benchmark_id == benchmark_provenance.benchmark_id
    assert result.attributes["benchmark_name"] == benchmark_provenance.benchmark_name
    assert result.attributes["benchmark_type"] == benchmark_provenance.benchmark_type


def test_industry_provenance_mapping_is_complete(industry_provenance):
    result = adapt_industry_provenance(industry_provenance)

    assert result.source_type == "industry_classification"
    assert result.source_name == industry_provenance.data_source
    assert result.data_version == industry_provenance.data_version
    assert result.as_of == industry_provenance.as_of
    assert result.price_type is None
    assert result.is_synthetic is True
    assert result.source_id == industry_provenance.industry_id
    assert result.attributes["industry_name"] == industry_provenance.industry_name
    assert result.attributes["classification"] == industry_provenance.classification


def test_decision_statistics_preserves_wilson_interval(statistics):
    record = adapt_decision_evidence_statistics(
        statistics,
        subject_id=SUBJECT_ID,
        data_tier="demo",
        calculation_code_version=CODE_VERSION,
    )

    assert record.evidence_kind == "aggregate_statistics"
    assert record.evidence_status == "complete"
    assert record.attributes["source_evidence_status"] == "available"
    assert record.value == statistics.hit_rate
    assert record.numerator == statistics.positive_n
    assert record.denominator == statistics.valid_n
    assert record.ci_lower == statistics.hit_rate_ci95_low
    assert record.ci_upper == statistics.hit_rate_ci95_high


def test_all_four_behavior_types_have_thin_adapters(behavior_evidence):
    adapters = (
        adapt_turnover_intensity_evidence,
        adapt_portfolio_concentration_evidence,
        adapt_disposition_effect_evidence,
        adapt_loss_averaging_evidence,
    )

    records = [
        adapter(
            evidence,
            subject_id=SUBJECT_ID,
            data_tier="demo",
            calculation_code_version=CODE_VERSION,
        )
        for adapter, evidence in zip(adapters, behavior_evidence)
    ]

    assert [record.metric_id for record in records] == [
        "mean_daily_turnover",
        "portfolio_concentration_hhi",
        "disposition_effect",
        "loss_averaging_event_rate",
    ]
    assert all(record.evidence_kind == "behavior_evidence" for record in records)
    assert all(record.evidence_status == "complete" for record in records)


def test_all_five_decision_types_have_thin_adapters(
    selection,
    sizing,
    exit_evidence,
    friction,
    statistics,
):
    evidence_items = (selection, sizing, exit_evidence, friction, statistics)
    records = [
        adapt_evidence(
            evidence,
            subject_id=SUBJECT_ID,
            data_tier="demo",
            calculation_code_version=CODE_VERSION,
        )
        for evidence in evidence_items
    ]

    assert [record.evidence_kind for record in records] == [
        "decision_evidence",
        "decision_evidence",
        "decision_evidence",
        "decision_evidence",
        "aggregate_statistics",
    ]
    assert all(record.evidence_id.startswith("ev_") for record in records)


def test_adapters_do_not_mutate_any_source_evidence(
    behavior_evidence,
    selection,
    sizing,
    exit_evidence,
    friction,
    statistics,
):
    evidence_items = (
        *behavior_evidence,
        selection,
        sizing,
        exit_evidence,
        friction,
        statistics,
    )
    before = copy.deepcopy(evidence_items)

    for evidence in evidence_items:
        adapt_evidence(
            evidence,
            subject_id=SUBJECT_ID,
            data_tier="demo",
            calculation_code_version=CODE_VERSION,
        )

    assert evidence_items == before


def test_attributes_are_json_safe_and_contain_no_timestamp_objects(
    behavior_evidence,
):
    record = adapt_loss_averaging_evidence(
        behavior_evidence[-1],
        subject_id=SUBJECT_ID,
        data_tier="demo",
        calculation_code_version=CODE_VERSION,
    )

    decoded = json.loads(canonical_json_bytes(record.attributes))
    assert json.loads(json.dumps(record.attributes)) == decoded
    assert decoded["events"][0]["event_time"] == END.isoformat()
    assert decoded["events"][0]["event_detected"] is True


def test_registry_is_queryable_and_separates_spec_from_metadata():
    definition = get_method_definition(SELECTION_METHOD_ID, METHOD_VERSION_V1)

    assert definition.method_id == SELECTION_METHOD_ID
    assert definition.method_version == "1"
    assert definition.source
    assert definition.sample_basis
    assert definition.limitations
    assert definition.metadata["producer"] == "personal-investment-twin"
    assert definition.metadata["registry_revision"] == 1
    assert definition.metadata["spec_digest"].startswith("sha256:")
    assert len(list_method_definitions()) == 9
    with pytest.raises(TypeError):
        definition.metadata["registry_revision"] = 2

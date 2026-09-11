import math

import pytest

from src.compare.lookthrough import (
    AccountPosition,
    Classification,
    FundMembership,
    LookthroughCycleError,
    build_lookthrough,
)


AS_OF = "2025-02-01"


def position(asset_id, kind, weight, source_id=None, observed_at="2025-01-31"):
    return AccountPosition(asset_id, kind, weight, observed_at, source_id or f"position:{asset_id}")


def member(fund_id, asset_id, kind, weight, source_id=None, *, effective="2025-01-01",
           published="2025-01-15", observed="2025-01-16"):
    return FundMembership(
        fund_id, asset_id, kind, weight, effective, published, observed,
        source_id or f"membership:{fund_id}:{asset_id}",
    )


def exposure(result, asset_id):
    return next(item for item in result.exposures if item.asset_id == asset_id)


def test_direct_and_fund_overlap_is_combined_without_keeping_expanded_fund():
    result = build_lookthrough(
        [position("AAPL", "security", 0.20), position("ETF", "fund", 0.50), position("USD", "cash", 0.30)],
        [member("ETF", "AAPL", "security", 0.40), member("ETF", "MSFT", "security", 0.60)],
        as_of=AS_OF,
        classifications=[Classification("AAPL", "Technology", "US", "2025-01-01", "2025-01-15", "2025-01-16", "class:aapl")],
    )

    apple = exposure(result, "AAPL")
    assert apple.weight == pytest.approx(0.40)
    assert apple.direct_weight == pytest.approx(0.20)
    assert apple.indirect_weight == pytest.approx(0.20)
    assert {path.direct for path in apple.paths} == {False, True}
    assert all(item.asset_id != "ETF" for item in result.exposures)
    assert result.sector_breakdown.denominator_weight == pytest.approx(0.70)
    assert result.sector_breakdown.classified_weight == pytest.approx(0.40)
    assert result.sector_breakdown.unclassified_weight == pytest.approx(0.30)
    assert math.isclose(result.total_weight, 1.0)


@pytest.mark.parametrize("newer", [
    member("ETF", "NEW", "security", 1.0, effective="2025-03-01"),
    member("ETF", "NEW", "security", 1.0, published="2025-03-01"),
])
def test_effective_or_published_future_disclosure_does_not_look_ahead(newer):
    older = member("ETF", "OLD", "security", 1.0)
    result = build_lookthrough([position("ETF", "fund", 1.0)], [older, newer], as_of=AS_OF)

    assert [item.asset_id for item in result.exposures] == ["OLD"]
    assert exposure(result, "OLD").weight == pytest.approx(1.0)


def test_partial_disclosure_keeps_uncovered_weight_and_does_not_renormalize():
    result = build_lookthrough(
        [position("ETF", "fund", 0.80), position("USD", "cash", 0.20)],
        [member("ETF", "KNOWN", "security", 0.75)], as_of=AS_OF,
    )

    assert exposure(result, "KNOWN").weight == pytest.approx(0.60)
    uncovered = exposure(result, "unknown:ETF:uncovered")
    assert uncovered.weight == pytest.approx(0.20)
    assert uncovered.paths[0].source_ids == ("position:ETF", "membership:ETF:KNOWN")
    assert result.selected_disclosures[0].fund_id == "ETF"
    assert result.selected_disclosures[0].source_ids == ("membership:ETF:KNOWN",)
    assert exposure(result, "USD").weight == pytest.approx(0.20)
    assert result.sector_breakdown.denominator_weight == pytest.approx(0.60)
    assert result.sector_breakdown.unclassified_weight == pytest.approx(0.60)
    assert result.total_weight == pytest.approx(1.0)


def test_disclosed_fund_cash_is_preserved_as_cash_not_unknown():
    result = build_lookthrough(
        [position("ETF", "fund", 1.0)],
        [member("ETF", "USD", "cash", 0.08), member("ETF", "AAPL", "security", 0.92)],
        as_of=AS_OF,
    )

    assert exposure(result, "USD").kind == "cash"
    assert exposure(result, "USD").weight == pytest.approx(0.08)
    assert all(item.kind != "unknown" for item in result.exposures)
    assert result.sector_breakdown.denominator_weight == pytest.approx(0.92)


def test_nested_expansion_is_bounded_and_does_not_count_parent_funds_twice():
    positions = [position("TOP", "fund", 1.0)]
    memberships = [
        member("TOP", "INNER", "fund", 1.0),
        member("INNER", "AAPL", "security", 0.70),
        member("INNER", "BOND", "security", 0.30),
    ]

    one_level = build_lookthrough(positions, memberships, as_of=AS_OF, max_depth=1)
    nested = build_lookthrough(positions, memberships, as_of=AS_OF, max_depth=2)

    assert [(item.kind, item.asset_id, item.weight) for item in one_level.exposures] == [("fund", "INNER", 1.0)]
    assert {item.asset_id for item in nested.exposures} == {"AAPL", "BOND"}
    assert all(item.kind != "fund" for item in nested.exposures)
    assert nested.total_weight == pytest.approx(1.0)


def test_cycles_are_rejected_or_preserved_as_explicit_unknown_by_policy():
    memberships = [member("A", "B", "fund", 1.0), member("B", "A", "fund", 1.0)]
    with pytest.raises(LookthroughCycleError, match="cycle"):
        build_lookthrough([position("A", "fund", 1.0)], memberships, as_of=AS_OF, max_depth=5)

    result = build_lookthrough(
        [position("A", "fund", 1.0)], memberships, as_of=AS_OF, max_depth=5,
        cycle_policy="unknown",
    )
    assert [(item.kind, item.asset_id, item.weight) for item in result.exposures] == [
        ("unknown", "unknown:A:cycle", 1.0)
    ]


def test_result_hash_paths_and_breakdowns_are_independent_of_input_order():
    positions = [position("AAPL", "security", 0.25), position("ETF", "fund", 0.75)]
    memberships = [member("ETF", "MSFT", "security", 0.50), member("ETF", "AAPL", "security", 0.50)]
    classifications = [
        Classification("MSFT", "Technology", "US", "2025-01-01", "2025-01-15", "2025-01-16", "class:msft"),
        Classification("AAPL", "Technology", "US", "2025-01-01", "2025-01-15", "2025-01-16", "class:aapl"),
    ]

    first = build_lookthrough(positions, memberships, as_of=AS_OF, classifications=classifications)
    second = build_lookthrough(
        list(reversed(positions)), list(reversed(memberships)), as_of=AS_OF,
        classifications=list(reversed(classifications)),
    )

    assert first == second
    assert first.lookthrough_id == second.lookthrough_id
    assert first.sector_breakdown.components[0].weight == pytest.approx(1.0)


def test_disclosure_dates_are_output_and_change_the_lookthrough_identity_even_when_weights_match():
    positions = [position("ETF", "fund", 1.0)]
    first = build_lookthrough(
        positions,
        [member("ETF", "AAPL", "security", 1.0, source_id="disclosure-row",
                effective="2025-01-01", published="2025-01-05", observed="2025-01-06")],
        as_of="2025-02-01",
    )
    second = build_lookthrough(
        positions,
        [member("ETF", "AAPL", "security", 1.0, source_id="disclosure-row",
                effective="2025-01-02", published="2025-01-06", observed="2025-01-07")],
        as_of="2025-02-01",
    )

    assert first.exposures == second.exposures
    assert first.lookthrough_id != second.lookthrough_id
    assert first.selected_disclosures[0].published_at.isoformat().startswith("2025-01-05")
    assert second.selected_disclosures[0].published_at.isoformat().startswith("2025-01-06")


def test_future_or_untraversed_disclosures_do_not_change_a_past_lookthrough_identity():
    positions = [position("ETF", "fund", 1.0)]
    current = member("ETF", "AAPL", "security", 1.0, source_id="current")
    baseline = build_lookthrough(positions, [current], as_of=AS_OF)
    augmented = build_lookthrough(
        positions,
        [
            current,
            member("ETF", "MSFT", "security", 1.0, source_id="future", effective="2025-03-01"),
            member("UNUSED", "OTHER", "security", 1.0, source_id="untraversed"),
        ],
        as_of=AS_OF,
    )

    assert augmented == baseline
    assert [item.fund_id for item in augmented.selected_disclosures] == ["ETF"]


def test_rejects_invalid_authoritative_or_membership_weights():
    with pytest.raises(ValueError, match="account weights exceed"):
        build_lookthrough(
            [position("A", "security", 0.7), position("B", "security", 0.7)], [], as_of=AS_OF,
        )
    with pytest.raises(ValueError, match="selected disclosure weights exceed"):
        build_lookthrough(
            [position("F", "fund", 1.0)],
            [member("F", "A", "security", 0.8), member("F", "B", "security", 0.8)],
            as_of=AS_OF,
        )

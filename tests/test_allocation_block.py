"""Known-answer tests for the investments allocation block."""
import math

from src.presentation.allocation import allocation_block


def _entry(instrument_id, market_value, status="open", quantity=10):
    return {"instrument_id": instrument_id, "display_name": instrument_id, "status": status,
            "quantity": quantity, "market_value": market_value, "currency": "CNY",
            "valuation_at": "2025-01-02T15:00:00" if market_value is not None else None}


def test_weights_sorted_and_normalized():
    block = allocation_block([
        _entry("BIG", 500.0), _entry("SMALL", 100.0), _entry("TIE", 500.0, quantity=1),
    ])
    positions = block["positions"]
    # Value descending, then instrument id ascending on ties.
    assert [item["instrument_id"] for item in positions] == ["BIG", "TIE", "SMALL"]
    assert [item["weight"] for item in positions] == [0.45454545454545453, 0.45454545454545453, 0.09090909090909091]
    assert math.isclose(sum(item["weight"] for item in positions), 1.0)
    assert block["positions_value"] == 1100.0
    assert block["position_count"] == 3
    assert all(item["currency"] == "CNY" for item in block["positions"])
    assert block["hhi"] == sum(item["weight"] ** 2 for item in positions)


def test_closed_and_markless_positions_excluded_but_counted():
    block = allocation_block([
        _entry("OPEN", 400.0),
        _entry("DONE", 999.0, status="closed", quantity=0),
        _entry("NOMARK", None),
    ])
    assert [item["instrument_id"] for item in block["positions"]] == ["OPEN"]
    assert block["positions"][0]["weight"] == 1.0
    assert block["skipped_no_market_value"] == 1
    assert block["position_count"] == 1


def test_empty_and_all_markless_stay_honest():
    empty = allocation_block([])
    assert empty["positions"] == [] and empty["positions_value"] == 0
    assert empty["hhi"] is None and empty["skipped_no_market_value"] == 0
    markless = allocation_block([_entry("A", None), _entry("B", None)])
    assert markless["positions"] == []
    assert markless["skipped_no_market_value"] == 2
    assert markless["hhi"] is None
    assert "definition" in markless

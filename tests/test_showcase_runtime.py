"""Synthetic showcase runtime routing; no provider or real-account access."""

from __future__ import annotations

import pytest

from src.demo import showcase
from src.demo.showcase_runtime import (
    DATA_MODE,
    _first_growth_episode,
    build_showcase_pair,
    load_showcase_review,
    simulate_showcase_trade,
    source_fingerprint,
)
from src.pretrade.impact import ProposedTrade
from toujing_core_runtime import review


def test_source_fingerprint_is_stable_and_scope_is_closed() -> None:
    assert source_fingerprint(showcase.SUBJECT_ID, showcase.ACCOUNT_ID) == source_fingerprint(
        showcase.SUBJECT_ID, showcase.ACCOUNT_ID
    )
    with pytest.raises(ValueError, match="unregistered"):
        source_fingerprint(showcase.SUBJECT_ID, "other-account")
    with pytest.raises(ValueError, match="unregistered"):
        source_fingerprint("other-subject", "other-subject")


def test_selected_episode_uses_full_owned_account_and_preserves_identity_mapping() -> None:
    raw, _ = showcase.showcase_inputs(showcase.SUBJECT_ID)
    _, pair_mapping = build_showcase_pair()
    legacy = pair_mapping["A"]["display_episode_id"]
    own, frame, market, mapping = load_showcase_review(
        showcase.SUBJECT_ID, showcase.ACCOUNT_ID, legacy
    )

    assert len(frame) == len(raw) == len(showcase.MAIN_TRADES)
    assert frame.subject_id.eq(showcase.SUBJECT_ID).all()
    assert frame.account_id.eq(showcase.ACCOUNT_ID).all()
    assert market.instrument.ne("SYN_GROWTH").any()  # qualified replay inputs
    assert own.episode.episode_id == mapping["canonical_episode_id"]
    assert mapping["display_episode_id"] != ""
    assert own.instrument.instrument_id == mapping["canonical_instrument_id"]
    with pytest.raises(ValueError, match="unregistered"):
        load_showcase_review(showcase.SUBJECT_ID, "foreign", legacy)


def test_pair_is_first_growth_episodes_from_exact_main_and_reference_scopes() -> None:
    comparison, mapping = build_showcase_pair()
    assert comparison.a.episode.subject_id == showcase.SUBJECT_ID
    assert comparison.a.episode.account_id == showcase.ACCOUNT_ID
    assert comparison.b.episode.subject_id == showcase.REFERENCE_SUBJECT
    assert comparison.b.episode.account_id == showcase.REFERENCE_SUBJECT
    assert comparison.a.episode.episode_id == mapping["A"]["canonical_episode_id"]
    assert comparison.b.episode.episode_id == mapping["B"]["canonical_episode_id"]
    assert comparison.a.instrument.local_symbol == comparison.b.instrument.local_symbol == "SYN_GROWTH"
    assert comparison.a.episode.opened_at == comparison.b.episode.opened_at == comparison.common_start
    assert comparison.a.episode.closed_at == comparison.b.episode.closed_at == comparison.common_end
    assert comparison.status == "comparable"


def test_showcase_trade_uses_2025_source_and_reports_insufficient_peer_context() -> None:
    trade = ProposedTrade(
        showcase.SUBJECT_ID, showcase.AS_OF, "SYN_GROWTH", "BUY", 100, 14.4, 5
    )
    result = simulate_showcase_trade(trade)
    assert result.simulation_status == "complete"
    assert result.before is not None and result.after is not None
    assert result.peer_context is None
    assert result.simulation_reason is None

    wrong_date = simulate_showcase_trade(
        ProposedTrade(showcase.SUBJECT_ID, "2025-07-02 23:59:00", "SYN_GROWTH", "BUY", 100, 14.4, 5)
    )
    assert wrong_date.simulation_status == "insufficient_evidence"
    with pytest.raises(ValueError, match="subject"):
        simulate_showcase_trade(
            ProposedTrade("not-showcase", showcase.AS_OF, "SYN_GROWTH", "BUY", 100, 14.4, 5)
        )


def test_runtime_mode_name_is_explicit_and_not_legacy_mode() -> None:
    assert DATA_MODE == "synthetic_showcase"


def test_pair_fingerprint_stales_when_reference_source_changes(monkeypatch) -> None:
    """Pair mode binds both registered synthetic sources, without repo access."""
    values = {
        showcase.SUBJECT_ID: "main-v1",
        showcase.REFERENCE_SUBJECT: "reference-v1",
    }
    monkeypatch.setattr(
        review,
        "showcase_source_fingerprint",
        lambda subject, account: values[subject] if account == subject else pytest.fail("foreign scope"),
    )
    service = object.__new__(review.ReviewRuntime)
    own_params = {
        "subject_id": showcase.SUBJECT_ID,
        "account_id": showcase.SUBJECT_ID,
        "data_mode": DATA_MODE,
    }
    pair_params = own_params | {"compare_pair": True, "pair_side": "A"}
    own_before = service._source_fingerprint(own_params)
    pair_before = service._source_fingerprint(pair_params)
    values[showcase.REFERENCE_SUBJECT] = "reference-v2"

    assert service._source_fingerprint(own_params) == own_before
    assert service._source_fingerprint(pair_params) != pair_before

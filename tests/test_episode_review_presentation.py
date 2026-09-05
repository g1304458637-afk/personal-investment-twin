from dataclasses import replace

import pandas as pd
import pytest

from test_episode_path_analysis import _complex_path, _lifecycle, CASH
from src.path.analysis import build_episode_path_analysis
from src.presentation.episode_review import review_presentation


@pytest.fixture(scope="module")
def case():
    executions, prices = _complex_path()
    lifecycle = _lifecycle(executions, prices, as_of="2025-06-11")
    analysis = build_episode_path_analysis(lifecycle, executions, prices,
        episode_id=lifecycle.episodes[0].episode_id, init_cash=CASH)
    return lifecycle, analysis


def test_story_preserves_existing_phase_order_counts_and_sources(case):
    lifecycle, analysis = case
    view = review_presentation(lifecycle, analysis)
    assert view == review_presentation(lifecycle, analysis)
    assert [step["phase_id"] for step in view["story_steps"]] == [phase.phase_id for phase in analysis.phases]
    assert [step["decision_count"] for step in view["story_steps"]] == [1, 2, 2, 1]
    assert [phase.quantity_after for phase in analysis.phases] == [400, 1100, 400, 0]
    assert view["story_abbreviated"] is False


def test_facts_keep_existing_order_with_dedupe_and_at_most_three(case):
    lifecycle, analysis = case
    view = review_presentation(lifecycle, analysis)
    assert 1 <= len(view["facts"]) <= 3
    assert len({fact["item_id"] for fact in view["facts"]}) == len(view["facts"])
    ids = [item.item_id for item in analysis.presentation_items]
    positions = [ids.index(fact["item_id"]) for fact in view["facts"]]
    assert positions == sorted(positions)
    doubled = replace(analysis, presentation_items=tuple(item for item in analysis.presentation_items for _ in range(2)))
    assert view == review_presentation(lifecycle, doubled)
    assert review_presentation(lifecycle, replace(analysis, presentation_items=()))["facts"] == []


def test_future_or_foreign_facts_do_not_become_review_text(case):
    lifecycle, analysis = case
    past = replace(lifecycle, as_of=pd.Timestamp("2025-01-25"))
    view = review_presentation(past, analysis)
    assert all(pd.Timestamp(item["end_at"]) <= past.as_of for item in view["facts"])
    phases = {phase.phase_id: phase for phase in analysis.phases}
    assert all(phases[step["phase_id"]].ended_at <= past.as_of for step in view["story_steps"])
    foreign = replace(analysis, patterns=tuple(replace(pattern, episode_id="foreign") for pattern in analysis.patterns))
    assert review_presentation(lifecycle, foreign)["facts"] == []

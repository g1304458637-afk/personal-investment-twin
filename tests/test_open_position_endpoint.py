from test_long_horizon_path import _open


def test_open_path_reaches_authoritative_as_of_without_new_execution():
    trades, _prices, lifecycle, episode, analysis = _open()
    snapshot = next(item for item in lifecycle.snapshots if item.episode_id == episode.episode_id)
    state = next(item for item in lifecycle.states if item.state_id == snapshot.position_state_ref)
    point = analysis.position_path.points[-1]
    assert point.as_of == snapshot.as_of
    assert point.state_id == state.state_id
    assert point.boundary == "as_of_valuation"
    assert point.quantity == state.quantity == 900
    assert point.average_cost == state.average_cost
    assert point.execution_id is point.decision_event_id is None
    assert len(episode.execution_refs) == len(trades)
    assert len(lifecycle.decisions) == len(trades)
    assert point.as_of.year == 2026
    assert lifecycle.decisions[-1].occurred_at.year == 2022

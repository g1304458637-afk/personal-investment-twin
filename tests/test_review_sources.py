import pandas as pd
import pytest

from src.agents.review_sources import build_owned_self_history
from src.compare.demo import AS_OF, pair_inputs
from src.self_baseline.core import list_self_baseline_metrics


def test_review_self_history_uses_existing_registered_methods_and_account_scope():
    frames, prices = pair_inputs()
    kwargs = dict(subject_id="SYN_COMPARE_A", account_id="SYN_COMPARE_ACCOUNT_A",
                  as_of=AS_OF, init_cash=100_000, data_tier="synthetic")
    result = build_owned_self_history(frames["A"], prices, **kwargs)
    assert result.subject_id == "SYN_COMPARE_A"
    assert {m.metric_id for m in result.metrics} == {"portfolio_concentration_hhi", "mean_daily_turnover"}
    assert result == build_owned_self_history(frames["A"], prices, **kwargs)
    with pytest.raises(ValueError, match="account"):
        build_owned_self_history(frames["A"], prices, **(kwargs | {"account_id": "OTHER"}))

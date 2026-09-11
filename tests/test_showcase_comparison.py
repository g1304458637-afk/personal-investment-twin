import numpy as np
import pandas as pd
import pytest

from src.behavior.replay_state import prepare_behavior_replay
from src.compare.research_demo import VERSION as COMPARISON_SCHEMA_VERSION
from src.demo import showcase
from src.demo.showcase_comparison import build_showcase_comparison


def _account(payload: dict[str, object], subject: str) -> dict[str, object]:
    accounts = payload["accounts"]
    assert isinstance(accounts, list)
    return next(item for item in accounts if item["subject_id"] == subject)


@pytest.fixture(scope="module")
def comparison() -> dict[str, object]:
    return build_showcase_comparison()


def test_showcase_comparison_uses_the_shared_accounts_and_adapter_schema(comparison):
    assert comparison["schema_version"] == COMPARISON_SCHEMA_VERSION
    assert comparison["source_version"] == showcase.VERSION
    assert comparison["as_of"] == showcase.AS_OF
    assert comparison["default_subject"] == showcase.SUBJECT_ID == showcase.ACCOUNT_ID
    assert [item["account_id"] for item in comparison["accounts"]] == list(showcase.SUBJECTS)
    assert all(item["subject_id"] == item["account_id"] for item in comparison["accounts"])

    reference = _account(comparison, showcase.REFERENCE_SUBJECT)
    assert comparison["comparisons"]["professional"].keys() == {showcase.REFERENCE_SUBJECT}
    assert reference["periods"]["full"]["performance"]["account_id"] == showcase.REFERENCE_SUBJECT
    for account in comparison["accounts"]:
        assert account["periods"]["full"]["benchmark"]["name"] == "SYN_MARKET"


def test_showcase_account_values_remain_the_existing_replay_values(comparison):
    account = _account(comparison, showcase.SUBJECT_ID)
    executions, prices = showcase.showcase_inputs(showcase.SUBJECT_ID)
    cutoff = pd.Timestamp(showcase.END) + pd.Timedelta(days=1)
    context = prepare_behavior_replay(
        executions.loc[executions["event_time"] < cutoff].copy(),
        prices.loc[prices["date"] < cutoff].copy(),
        init_cash=showcase.INITIAL_CASH,
    )
    values = context.portfolio.value()
    dates = pd.Index(item.date() for item in values.index)
    eod = values.loc[(dates >= pd.Timestamp(showcase.START).date()) & (dates <= pd.Timestamp(showcase.END).date())]
    eod = eod.groupby(pd.Index(item.date() for item in eod.index), sort=True).tail(1)

    points = account["periods"]["full"]["performance"]["points"]
    np.testing.assert_allclose([point["account_value"] for point in points], eod.to_numpy())
    assert account["periods"]["full"]["performance"]["period_return"] == pytest.approx(
        eod.iloc[-1] / eod.iloc[0] - 1.0
    )


def test_showcase_fund_lookthrough_uses_the_declared_start_disclosure(comparison):
    allocation = _account(comparison, showcase.SUBJECT_ID)["periods"]["full"]["allocation"]
    lookthrough = allocation["lookthrough"]
    disclosure = lookthrough["selected_disclosures"]

    assert len(disclosure) == 1
    assert disclosure[0]["fund_id"] == "SYN_FUND"
    assert disclosure[0]["effective_at"] == pd.Timestamp(showcase.START)
    assert disclosure[0]["published_at"] == pd.Timestamp(showcase.START)
    assert disclosure[0]["observed_at"] == pd.Timestamp(showcase.START)
    assert set(disclosure[0]["source_ids"]) == {showcase.VERSION}

    exposures = {item["asset_id"]: item for item in lookthrough["exposures"]}
    fund_weight = next(item["weight"] for item in allocation["direct"] if item["asset_id"] == "SYN_FUND")
    assert exposures["SYN_GROWTH"]["indirect_weight"] == pytest.approx(fund_weight * 0.40)
    assert exposures["SYN_VALUE"]["indirect_weight"] == pytest.approx(fund_weight * 0.35)
    assert exposures["SYN_INDUSTRIAL"]["indirect_weight"] == pytest.approx(fund_weight * 0.25)

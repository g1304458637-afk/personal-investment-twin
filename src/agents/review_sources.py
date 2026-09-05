"""Thin retrieval of registered self-history; no additional metric formula."""

import pandas as pd

from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.evidence.adapters import adapt_evidence
from src.history.metric_series import build_portfolio_hhi_history_with_records, build_turnover_history
from src.self_baseline.core import build_self_baseline_summary
from src.twin.state import build_twin_snapshot_from_facts


def build_owned_self_history(executions, prices, *, subject_id, account_id, as_of, init_cash, data_tier):
    """Rebuild registered account facts through the exact review cutoff."""
    frame = executions.loc[pd.to_datetime(executions.event_time) <= as_of].copy()
    market = prices.loc[pd.to_datetime(prices.date).dt.normalize() <= as_of.normalize()].copy()
    if "account_id" not in frame or not frame.account_id.eq(account_id).all():
        raise ValueError("self_history_account_mismatch")
    if "subject_id" not in frame or not frame.subject_id.eq(subject_id).all():
        raise ValueError("self_history_subject_mismatch")
    # Canonical v2 supplies a date-valued metadata column; the existing Twin
    # input fingerprint expects its JSON representation. Preserve the exact
    # calendar date and all execution timestamps/sequence, without new math.
    if "market_date" in frame:
        frame["market_date"] = frame["market_date"].map(lambda value: pd.Timestamp(value).date().isoformat())
    hhi, records = build_portfolio_hhi_history_with_records(
        frame, market, init_cash=init_cash, subject_id=subject_id, data_tier=data_tier,
        calculation_code_version="review_sources_v1")
    turnover = build_turnover_intensity_evidence(frame, market, init_cash=init_cash)
    record = adapt_evidence(turnover, subject_id=subject_id, data_tier=data_tier,
                            calculation_code_version="review_sources_v1")
    series = (hhi, build_turnover_history(turnover, parent_record=record))
    evidence = (*records, record)
    snapshot = build_twin_snapshot_from_facts(
        frame, market, evidence, series, subject_id=subject_id, account_id=account_id,
        as_of=as_of, init_cash=init_cash, data_tier=data_tier, calculation_code_version="review_sources_v1")
    return build_self_baseline_summary(snapshot, series, evidence)

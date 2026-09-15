"""Orchestration for the single deterministic synthetic peer benchmark."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.cohort.engine import build_peer_benchmark_results, exact_cohort_members
from src.cohort.models import CohortDefinition, CohortMember, PeerBenchmarkResult
from src.cohort.synthetic import (
    SyntheticCohortAccount,
    build_account_peer_metric_values,
    build_synthetic_peer_metric_values,
    generate_synthetic_cohort_accounts,
    synthetic_cohort_definition,
)


@dataclass(frozen=True, slots=True)
class SyntheticPeerBenchmark:
    """Export-sized result; generated account transactions remain internal."""

    cohort: CohortDefinition
    cohort_n: int
    metrics: tuple[PeerBenchmarkResult, ...]


def build_synthetic_peer_benchmark(
    *,
    subject_id: str,
    subject_executions: pd.DataFrame,
    market_prices: pd.DataFrame,
    init_cash: float,
    calculation_code_version: str,
    data_tier: str = "synthetic",
) -> SyntheticPeerBenchmark:
    """Compare one existing demo subject with 72 separately replayed peer accounts.

    The cohort is synthetic by construction, so the subject must be one too:
    a real account's executions must never be percentile-ranked against
    synthetic fixtures and exported as synthetic.  The frame's
    ``data_tier`` column (normalized executions carry one) is checked when
    present, and an explicit non-synthetic ``data_tier`` argument is refused.
    """
    if data_tier != "synthetic":
        raise ValueError(
            "synthetic peer benchmark refuses non-synthetic subject data_tier "
            f"(received {data_tier!r})"
        )
    tier_column = subject_executions.get("data_tier")
    if tier_column is not None and not (tier_column == "synthetic").all():
        raise ValueError(
            "synthetic peer benchmark requires synthetic-tier subject executions"
        )

    definition = synthetic_cohort_definition()
    peer_accounts = generate_synthetic_cohort_accounts(
        market_prices,
        definition=definition,
        init_cash=init_cash,
    )
    members = tuple(account.member for account in peer_accounts)
    peer_metric_values = build_synthetic_peer_metric_values(
        peer_accounts,
        calculation_code_version=calculation_code_version,
    )

    subject_member = CohortMember(
        subject_id=subject_id,
        market=definition.market,
        asset_types=definition.asset_types,
        direction=definition.direction,
        observation_start=definition.observation_start,
        observation_end=definition.observation_end,
        leverage=False,
        data_tier="synthetic",
        data_quality_status="complete",
    )
    subject_account = SyntheticCohortAccount(
        member=subject_member,
        executions=subject_executions,
        market_prices=market_prices,
        init_cash=float(init_cash),
    )
    subject_metric_values = build_account_peer_metric_values(
        subject_account,
        calculation_code_version=calculation_code_version,
    )
    metrics = build_peer_benchmark_results(
        definition,
        members,
        peer_metric_values,
        subject_metric_values,
        subject_id=subject_id,
    )
    cohort_n = len(exact_cohort_members(definition, members))
    return SyntheticPeerBenchmark(
        cohort=definition,
        cohort_n=cohort_n,
        metrics=metrics,
    )

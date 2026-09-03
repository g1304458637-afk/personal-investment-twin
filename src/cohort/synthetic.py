"""Deterministic synthetic account inputs for the bounded demo cohort."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import pandas as pd

from src.behavior.portfolio_concentration import (
    build_portfolio_concentration_evidence,
)
from src.behavior.replay_state import BehaviorReplayError, prepare_behavior_replay
from src.behavior.turnover_intensity import build_turnover_intensity_evidence
from src.attribution.selection_evidence import _EvidenceDataError, _synthetic_flag
from src.cohort.models import CohortDefinition, CohortMember, PeerMetricValue
from src.evidence.adapters import (
    adapt_portfolio_concentration_evidence,
    adapt_turnover_intensity_evidence,
)
from src.evidence.contracts import canonical_json_bytes
from src.episodes.investment_episode import from_vectorbt_position_record


SYNTHETIC_COHORT_ID = "synthetic-cn-equity-long-only-2025-01-v1"
SYNTHETIC_OBSERVATION_START = pd.Timestamp("2025-01-02")
SYNTHETIC_OBSERVATION_END = pd.Timestamp("2025-01-08")
SYNTHETIC_OBSERVATION_DATES = (
    pd.Timestamp("2025-01-02"),
    pd.Timestamp("2025-01-03"),
    pd.Timestamp("2025-01-06"),
    pd.Timestamp("2025-01-07"),
    pd.Timestamp("2025-01-08"),
)
SYNTHETIC_PEER_COUNT = 72
SYNTHETIC_MARKET = "synthetic-cn-equity-demo"


@dataclass(frozen=True, slots=True)
class SyntheticCohortAccount:
    """One generated account plus the canonical facts supplied to existing engines."""

    member: CohortMember
    executions: pd.DataFrame
    market_prices: pd.DataFrame
    init_cash: float


def _require_synthetic_prices(market_prices: pd.DataFrame) -> None:
    if "is_synthetic" not in market_prices.columns:
        raise ValueError("Synthetic cohort prices require is_synthetic provenance")
    try:
        flags = tuple(
            _synthetic_flag(value, "Synthetic cohort prices")
            for value in market_prices["is_synthetic"]
        )
    except _EvidenceDataError as exc:
        raise ValueError(str(exc)) from exc
    if flags and not all(flags):
        raise ValueError("Synthetic cohort prices must all have synthetic provenance")


def synthetic_cohort_definition() -> CohortDefinition:
    """Return the one exact cohort supported by v1."""

    return CohortDefinition(
        cohort_id=SYNTHETIC_COHORT_ID,
        market=SYNTHETIC_MARKET,
        asset_types=("equity",),
        direction="long_only",
        observation_start=SYNTHETIC_OBSERVATION_START,
        observation_end=SYNTHETIC_OBSERVATION_END,
        leverage_allowed=False,
        data_tier="synthetic",
        min_descriptive_n=30,
        description=(
            "72 deterministic synthetic long-only equity accounts observed from "
            "2025-01-02 through 2025-01-08, with no leverage."
        ),
        limitations=(
            "Synthetic accounts are deterministic plumbing fixtures, not real people.",
            "This short demo window does not represent long-term investor behavior.",
            "The distribution does not represent real Chinese investors.",
            "Percentiles are descriptive positions, not quality or skill scores.",
        ),
    )


def _execution_rows(
    subject_id: str,
    *,
    concentration_index: int,
    activity_index: int,
    closed_episode_target: int,
) -> pd.DataFrame:
    scale = activity_index + 1
    core_quantities = (
        (80, 300, 160),
        (120, 240, 180),
        (180, 180, 200),
        (260, 130, 220),
        (360, 90, 240),
        (500, 60, 260),
    )[concentration_index]
    rows: list[dict[str, object]] = []

    def add(
        event_time: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
    ) -> None:
        sequence = len(rows) + 1
        execution_id = f"{subject_id}:execution:{sequence:02d}"
        rows.append(
            {
                "event_time": pd.Timestamp(event_time),
                "symbol": symbol,
                "side": side,
                "executed_quantity": float(quantity),
                "executed_price": float(price),
                "fee": 0.0,
                "order_id": f"{subject_id}:order:{sequence:02d}",
                "execution_id": execution_id,
            }
        )

    for symbol, quantity, price in zip(
        ("SYN_PAPER_WIN", "SYN_PAPER_LOSS", "SYN_NEUTRAL"),
        core_quantities,
        (10.0, 10.0, 5.0),
        strict=True,
    ):
        add("2025-01-02", symbol, "BUY", quantity * scale, price)

    if closed_episode_target >= 1:
        quantity = (50 + concentration_index * 10) * scale
        add("2025-01-02", "SYN_WIN_SOLD", "BUY", quantity, 10.0)
        add("2025-01-07", "SYN_WIN_SOLD", "SELL", quantity, 12.0)
    if closed_episode_target >= 2:
        quantity = (40 + concentration_index * 5) * scale
        add("2025-01-02", "SYN_LOSS_SOLD", "BUY", quantity, 20.0)
        add("2025-01-08", "SYN_LOSS_SOLD", "SELL", quantity, 16.0)

    return pd.DataFrame(rows)


def generate_synthetic_cohort_accounts(
    market_prices: pd.DataFrame,
    *,
    definition: CohortDefinition | None = None,
    init_cash: float = 100_000.0,
) -> tuple[SyntheticCohortAccount, ...]:
    """Generate a fixed 6 x 4 x 3 grid without random values or metric fixtures."""

    cohort = definition or synthetic_cohort_definition()
    if cohort != synthetic_cohort_definition():
        raise ValueError("Synthetic cohort v1 supports only its exact fixed definition")
    if not isinstance(market_prices, pd.DataFrame) or market_prices.empty:
        raise ValueError("market_prices must contain the synthetic market fixture")
    if not math.isfinite(float(init_cash)) or float(init_cash) <= 0:
        raise ValueError("init_cash must be finite and positive")
    if "date" not in market_prices.columns:
        raise ValueError("market_prices.date is required")
    _require_synthetic_prices(market_prices)

    dates = pd.to_datetime(market_prices["date"], errors="raise").dt.normalize()
    prices = market_prices.loc[
        (dates >= cohort.observation_start) & (dates <= cohort.observation_end)
    ].copy()
    if tuple(
        sorted(pd.Timestamp(item) for item in dates.loc[prices.index].unique())
    ) != SYNTHETIC_OBSERVATION_DATES:
        raise ValueError("Synthetic prices must use the fixed cohort observation dates")
    if dates.loc[prices.index].min() != cohort.observation_start:
        raise ValueError("Synthetic prices do not start at the cohort observation_start")
    if dates.loc[prices.index].max() != cohort.observation_end:
        raise ValueError("Synthetic prices do not end at the cohort observation_end")

    accounts: list[SyntheticCohortAccount] = []
    for concentration_index in range(6):
        for activity_index in range(4):
            for closed_episode_target in range(3):
                number = len(accounts) + 1
                subject_id = f"synthetic-peer:{number:03d}"
                executions = _execution_rows(
                    subject_id,
                    concentration_index=concentration_index,
                    activity_index=activity_index,
                    closed_episode_target=closed_episode_target,
                )
                executed_symbols = set(executions["symbol"])
                account_prices = prices.loc[
                    prices["instrument"].isin(executed_symbols)
                ].copy()
                member = CohortMember(
                    subject_id=subject_id,
                    market=cohort.market,
                    asset_types=cohort.asset_types,
                    direction=cohort.direction,
                    observation_start=cohort.observation_start,
                    observation_end=cohort.observation_end,
                    leverage=False,
                    data_tier="synthetic",
                    data_quality_status="complete",
                )
                accounts.append(
                    SyntheticCohortAccount(
                        member=member,
                        executions=executions,
                        market_prices=account_prices,
                        init_cash=float(init_cash),
                    )
                )

    if len(accounts) != SYNTHETIC_PEER_COUNT:  # pragma: no cover - grid invariant
        raise RuntimeError("Synthetic cohort grid did not produce 72 accounts")
    return tuple(accounts)


def _window_inputs(
    account: SyntheticCohortAccount,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    end = account.member.observation_end
    execution_dates = pd.to_datetime(
        account.executions["event_time"], errors="raise"
    ).dt.normalize()
    price_times = pd.to_datetime(account.market_prices["date"], errors="raise")
    return (
        account.executions.loc[execution_dates <= end].copy(),
        account.market_prices.loc[price_times.dt.normalize() <= end].copy(),
    )


def _episode_source_id(
    subject_id: str,
    episodes: tuple[object, ...],
    *,
    observation_start: pd.Timestamp,
    observation_end: pd.Timestamp,
) -> str:
    payload = {
        "subject_id": subject_id,
        "observation_start": observation_start.isoformat(),
        "observation_end": observation_end.isoformat(),
        "episodes": [
            {
                "episode_id": episode.episode_id,
                "status": episode.status,
                "exit_time": (
                    episode.exit_time.isoformat() if episode.exit_time is not None else None
                ),
                "valuation_time": (
                    episode.valuation_time.isoformat()
                    if episode.valuation_time is not None
                    else None
                ),
            }
            for episode in episodes
        ],
    }
    return "episode_set:" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_account_peer_metric_values(
    account: SyntheticCohortAccount,
    *,
    calculation_code_version: str,
) -> tuple[PeerMetricValue, ...]:
    """Map existing builder outputs to three account-level peer metric values."""

    executions, prices = _window_inputs(account)
    member = account.member
    if member.data_tier != "synthetic":
        raise ValueError("Synthetic cohort accounts must use the synthetic data tier")
    _require_synthetic_prices(prices)
    execution_dates = pd.to_datetime(executions["event_time"], errors="raise").dt.normalize()
    executed_symbols = tuple(sorted(executions["symbol"].astype(str).unique()))
    price_dates = pd.to_datetime(prices["date"], errors="raise").dt.normalize()
    price_calendar_complete = bool(executed_symbols) and all(
        tuple(
            sorted(
                pd.Timestamp(value)
                for value in price_dates.loc[
                    prices["instrument"].astype(str) == symbol
                ].unique()
                if member.observation_start <= value <= member.observation_end
            )
        )
        == SYNTHETIC_OBSERVATION_DATES
        for symbol in executed_symbols
    )
    account_history_available = (
        not execution_dates.empty
        and execution_dates.min() <= member.observation_start
    )
    comparable_window = price_calendar_complete and account_history_available
    hhi = build_portfolio_concentration_evidence(
        executions,
        prices,
        init_cash=account.init_cash,
    )
    hhi_record = adapt_portfolio_concentration_evidence(
        hhi,
        subject_id=member.subject_id,
        data_tier="synthetic",
        calculation_code_version=calculation_code_version,
    )
    hhi_complete = (
        hhi.evidence_status == "complete"
        and comparable_window
        and hhi.as_of_time is not None
        and hhi.as_of_time.normalize() == member.observation_end
        and hhi.hhi is not None
    )
    hhi_reason = (
        hhi.evidence_reason
        if hhi.evidence_status != "complete"
        else (
            None
            if hhi_complete
            else "HHI evidence does not cover the exact cohort window"
        )
    )

    turnover = build_turnover_intensity_evidence(
        executions,
        prices,
        init_cash=account.init_cash,
    )
    turnover_record = adapt_turnover_intensity_evidence(
        turnover,
        subject_id=member.subject_id,
        data_tier="synthetic",
        calculation_code_version=calculation_code_version,
    )
    turnover_dates = tuple(item.observation_date for item in turnover.daily_turnover)
    turnover_complete = (
        turnover.evidence_status == "complete"
        and comparable_window
        and bool(turnover_dates)
        and turnover_dates[0] == member.observation_start
        and turnover_dates[-1] == member.observation_end
        and turnover.mean_daily_turnover is not None
    )
    turnover_reason = (
        turnover.evidence_reason
        if turnover.evidence_status != "complete"
        else (
            None
            if turnover_complete
            else "Turnover evidence does not cover the exact cohort window"
        )
    )

    episode_status = "complete" if comparable_window else "insufficient_evidence"
    episode_reason: str | None = (
        None if comparable_window else "Account facts do not cover the exact cohort window"
    )
    episode_count: float | None
    episode_source_id: str
    try:
        context = prepare_behavior_replay(
            executions,
            prices,
            init_cash=account.init_cash,
        )
        episodes = tuple(
            from_vectorbt_position_record(record)
            for _, record in context.portfolio.positions.records_readable.iterrows()
        )
        closed = tuple(
            episode
            for episode in episodes
            if episode.status == "Closed"
            and episode.exit_time is not None
            and member.observation_start <= episode.exit_time.normalize()
            and episode.exit_time.normalize() <= member.observation_end
        )
        episode_count = float(len(closed)) if comparable_window else None
        episode_source_id = _episode_source_id(
            member.subject_id,
            closed,
            observation_start=member.observation_start,
            observation_end=member.observation_end,
        )
    except (BehaviorReplayError, KeyError, TypeError, ValueError) as exc:
        episode_status = "insufficient_evidence"
        episode_reason = str(exc)
        episode_count = None
        episode_source_id = _episode_source_id(
            member.subject_id,
            (),
            observation_start=member.observation_start,
            observation_end=member.observation_end,
        )

    return (
        PeerMetricValue(
            subject_id=member.subject_id,
            metric_id="portfolio_concentration_hhi",
            value=float(hhi.hhi) if hhi_complete else None,
            evidence_status="complete" if hhi_complete else "insufficient_evidence",
            source_evidence_id=hhi_record.evidence_id,
            as_of=member.observation_end,
            evidence_reason=hhi_reason,
        ),
        PeerMetricValue(
            subject_id=member.subject_id,
            metric_id="mean_daily_turnover",
            value=(
                float(turnover.mean_daily_turnover)
                if turnover_complete
                else None
            ),
            evidence_status=(
                "complete" if turnover_complete else "insufficient_evidence"
            ),
            source_evidence_id=turnover_record.evidence_id,
            as_of=member.observation_end,
            evidence_reason=turnover_reason,
        ),
        PeerMetricValue(
            subject_id=member.subject_id,
            metric_id="closed_episode_count",
            value=episode_count,
            evidence_status=episode_status,
            source_evidence_id=episode_source_id,
            as_of=member.observation_end,
            evidence_reason=episode_reason,
        ),
    )


def build_synthetic_peer_metric_values(
    accounts: tuple[SyntheticCohortAccount, ...],
    *,
    calculation_code_version: str,
) -> tuple[PeerMetricValue, ...]:
    """Build one value per account per metric, in stable account/metric order."""

    return tuple(
        metric
        for account in accounts
        for metric in build_account_peer_metric_values(
            account,
            calculation_code_version=calculation_code_version,
        )
    )

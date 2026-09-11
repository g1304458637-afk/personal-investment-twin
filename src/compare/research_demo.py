"""Explicit synthetic comparison study; source inputs, not hand-written results.

Three fixed long-only accounts share a six-month *synthetic weekday calendar*.
Prices/transactions are scenario inputs. All financial outputs delegate to the
existing replay/builders or the separately versioned comparison projections.
No brokerage data, true professional identity, model call, or persistence.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from collections.abc import Callable
from typing import Final, Sequence

import empyrical
import numpy as np
import pandas as pd

from src.behavior.replay_state import prepare_behavior_replay
from src.compare.account_comparison import compare_account_periods
from src.compare.lookthrough import (
    AccountPosition,
    Classification,
    FundMembership,
    LookthroughResult,
    build_lookthrough,
)
from src.compare.periods import PeriodBehaviorSummary, build_period_behavior
from src.episodes.position_episode import build_position_episode_lifecycle
from src.performance.account_series import (
    AccountPerformanceSeries,
    DailyRiskPolicy,
    build_account_performance_from_replay,
)

VERSION: Final = "comparison_research_demo_v1"
SYNTHETIC_SCHEDULE: Final = "declared_synthetic_weekdays_not_exchange_calendar"
START, MIDDLE, END = "2025-01-02", "2025-04-02", "2025-07-02"
INITIAL_CASH: Final = 100_000.0
SYMBOLS: Final = ("SYN_GROWTH", "SYN_VALUE", "SYN_FUND")
SUBJECTS: Final = (
    "SYN_STUDY_SELF",
    "SYN_STUDY_BALANCED",
    "SYN_STUDY_FOCUSED",
)
NAMES = {
    "SYN_GROWTH": {"zh": "成长示例股", "en": "Growth example"},
    "SYN_VALUE": {"zh": "价值示例股", "en": "Value example"},
    "SYN_FUND": {"zh": "混合示例基金", "en": "Mixed example fund"},
    "SYN_INDUSTRIAL": {"zh": "制造示例股", "en": "Industrial example"},
    "cash": {"zh": "现金", "en": "Cash"},
}


@dataclass(frozen=True, slots=True)
class ComparisonExportConfig:
    """Source-owned facts that label a comparison projection.

    The replay, performance, behavior, lookthrough, and comparison engines are
    deliberately shared by every configured synthetic export.  This object
    only supplies input-source identity and the bounded synthetic disclosure
    used to describe an allocation.
    """

    source_version: str
    synthetic_schedule: str
    study_start: str
    initial_cash: float
    fund_symbol: str
    benchmark_symbol: str
    fund_memberships: tuple[tuple[str, str, float], ...]
    classifications: tuple[tuple[str, str], ...]


RESEARCH_DEMO_CONFIG: Final = ComparisonExportConfig(
    source_version=VERSION,
    synthetic_schedule=SYNTHETIC_SCHEDULE,
    study_start=START,
    initial_cash=INITIAL_CASH,
    fund_symbol="SYN_FUND",
    benchmark_symbol="SYN_MARKET",
    fund_memberships=(
        ("SYN_GROWTH", "security", 0.4),
        ("SYN_VALUE", "security", 0.35),
        ("SYN_INDUSTRIAL", "security", 0.25),
    ),
    classifications=(
        ("SYN_GROWTH", "growth"),
        ("SYN_VALUE", "value"),
        ("SYN_INDUSTRIAL", "industrial"),
    ),
)


@dataclass(frozen=True, slots=True)
class _AllocationBuild:
    """Export projection plus the typed lookthrough used by comparisons."""

    payload: dict[str, object]
    lookthrough: LookthroughResult


@dataclass(frozen=True, slots=True)
class _PeriodBuild:
    """One replay/build pass retained in typed form until comparisons finish."""

    payload: dict[str, object]
    performance: AccountPerformanceSeries
    behavior: PeriodBehaviorSummary
    lookthrough: LookthroughResult


def study_inputs(subject: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if subject not in SUBJECTS:
        raise ValueError("Unknown synthetic study subject")
    dates = pd.bdate_range(START, END)  # declared synthetic schedule, not an exchange calendar
    anchors = [0, 20, 43, 65, 88, 110, len(dates) - 1]
    curves = {
        "SYN_GROWTH": [10, 12, 9, 10.5, 13, 11, 12.5],
        "SYN_VALUE": [20, 20.8, 19.2, 21, 22.4, 21.8, 23],
        "SYN_FUND": [10, 10.7, 9.8, 10.6, 11.4, 11, 11.7],
        "SYN_MARKET": [100, 107, 96, 105, 114, 108, 116],
    }
    marks = {s: np.round(np.interp(np.arange(len(dates)), anchors, v), 6) for s, v in curves.items()}
    prices = pd.DataFrame([
        dict(date=date, instrument=s, close=float(values[i]), price_type="synthetic",
             data_source=VERSION, data_version="1", is_synthetic=True)
        for s, values in marks.items() for i, date in enumerate(dates)
    ])
    # (observation index, security index, side, shares): fixed facts, no optimized strategy.
    schedules = {
        SUBJECTS[0]: [(0,0,"BUY",1800),(0,1,"BUY",1500),(0,2,"BUY",1500),
          (15,0,"BUY",800),(30,0,"SELL",400),(42,0,"BUY",600),(50,2,"BUY",500),
          (66,0,"SELL",1200),(78,1,"BUY",300),(90,0,"SELL",800),
          (105,2,"SELL",500),(118,0,"SELL",800),(125,2,"BUY",300)],
        SUBJECTS[1]: [(0,0,"BUY",1200),(0,1,"BUY",1400),(0,2,"BUY",3000),
          (20,0,"SELL",200),(42,1,"BUY",200),(66,2,"SELL",400),
          (85,0,"BUY",200),(105,1,"SELL",200)],
        SUBJECTS[2]: [(0,0,"BUY",5500),(0,1,"BUY",500),(0,2,"BUY",1000),
          (20,0,"SELL",1800),(43,0,"BUY",1400),(65,0,"SELL",1000),
          (88,0,"SELL",1600),(111,0,"BUY",1000)],
    }
    rows = []
    for seq, (day, asset, side, quantity) in enumerate(schedules[subject]):
        symbol = SYMBOLS[asset]
        rows.append(dict(event_time=dates[day] + pd.Timedelta(hours=10, minutes=seq),
            symbol=symbol, side=side, executed_quantity=float(quantity),
            executed_price=float(marks[symbol][day]), fee=5.0,
            order_id=f"{subject}-{seq}", execution_id=f"{subject}-{seq}",
            execution_sequence=seq, subject_id=subject, account_id=subject))
    return pd.DataFrame(rows), prices


def _canonical_frame_bytes(frame: pd.DataFrame, *, sort_by: Sequence[str]) -> bytes:
    """Serialize one input fact collection without mutating caller-owned rows."""

    missing = [column for column in sort_by if column not in frame.columns]
    if missing:
        raise ValueError(f"Cannot hash input frame without columns: {missing}")
    normalized = frame.copy(deep=True)
    normalized = normalized.sort_values(list(sort_by), kind="stable").reset_index(drop=True)
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    return normalized.to_json(
        orient="split",
        date_format="iso",
        date_unit="ns",
        double_precision=15,
        force_ascii=False,
    ).encode("utf-8")


def _study_input_sha256(
    inputs: Sequence[tuple[str, pd.DataFrame, pd.DataFrame]],
) -> str:
    """Hash every synthetic execution and price fact, with explicit framing."""

    digest = hashlib.sha256()
    for subject, executions, prices in sorted(inputs, key=lambda item: item[0]):
        for label, payload in (
            ("subject", subject.encode("utf-8")),
            (
                "executions",
                _canonical_frame_bytes(
                    executions,
                    sort_by=("event_time", "execution_sequence", "execution_id"),
                ),
            ),
            (
                "prices",
                _canonical_frame_bytes(
                    prices,
                    sort_by=("date", "instrument", "data_source", "data_version"),
                ),
            ),
        ):
            label_bytes = label.encode("ascii")
            digest.update(len(label_bytes).to_bytes(4, "big"))
            digest.update(label_bytes)
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return digest.hexdigest()


def _allocation(
    context,
    at: str,
    *,
    config: ComparisonExportConfig = RESEARCH_DEMO_CONFIG,
) -> _AllocationBuild:
    target_date = pd.Timestamp(at).normalize()
    pf = context.portfolio
    portfolio_values = pf.value()
    eligible = portfolio_values.loc[
        pd.DatetimeIndex(portfolio_values.index).normalize() <= target_date
    ]
    if eligible.empty or eligible.index[-1].normalize() != target_date:
        raise ValueError("allocation requires an exact selected portfolio valuation date")
    valuation_observed_at = pd.Timestamp(eligible.index[-1])
    row = pf.asset_value(group_by=False).loc[valuation_observed_at]
    total = float(portfolio_values.loc[valuation_observed_at])
    cash = float(pf.cash().loc[valuation_observed_at])
    positions = [
        AccountPosition(
            "cash", "cash", cash / total, valuation_observed_at, config.source_version
        )
    ]
    direct = [dict(asset_id="cash", kind="cash", value=cash, weight=cash / total)]
    for symbol in sorted(row.index):
        if float(row[symbol]) <= 0:
            continue
        kind = "fund" if symbol == config.fund_symbol else "security"
        positions.append(
            AccountPosition(
                symbol,
                kind,
                float(row[symbol]) / total,
                valuation_observed_at,
                config.source_version,
            )
        )
        direct.append(
            dict(
                asset_id=symbol,
                kind=kind,
                value=float(row[symbol]),
                weight=float(row[symbol]) / total,
            )
        )
    stamp = pd.Timestamp(config.study_start)
    members = [
        FundMembership(
            config.fund_symbol,
            symbol,
            kind,
            weight,
            stamp,
            stamp,
            stamp,
            config.source_version,
        )
        for symbol, kind, weight in config.fund_memberships
    ]
    classifications = [
        Classification(
            symbol,
            sector,
            "synthetic_market",
            stamp,
            stamp,
            stamp,
            config.source_version,
        )
        for symbol, sector in config.classifications
    ]
    # Daily marks are EOD observations even though their actual source record
    # timestamps are midnight.  Keep that record timestamp on positions, and
    # make the point-in-time availability cutoff explicitly end-of-day.
    lookthrough_as_of = target_date + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    lookthrough = build_lookthrough(
        positions,
        members,
        as_of=lookthrough_as_of,
        classifications=classifications,
    )
    return _AllocationBuild(
        payload=dict(
            date=at,
            valuation_observed_at=valuation_observed_at,
            observation_semantics="synthetic_daily_eod_last_actual_replay_observation",
            portfolio_value=total,
            cash=cash,
            direct=direct,
            lookthrough=asdict(lookthrough),
        ),
        lookthrough=lookthrough,
    )


def _period(
    subject,
    executions,
    prices,
    start,
    end,
    *,
    config: ComparisonExportConfig = RESEARCH_DEMO_CONFIG,
) -> _PeriodBuild:
    cutoff = pd.Timestamp(end) + pd.Timedelta(days=1)
    frame = executions[executions.event_time < cutoff].copy()
    market = prices[prices.date < cutoff].copy()
    context = prepare_behavior_replay(frame, market, init_cash=config.initial_cash)
    schedule_dates = tuple(pd.bdate_range(start, end).date)
    schedule_source_ref = (
        f"{config.source_version}:{config.synthetic_schedule}:{start}:{end}"
    )
    performance = build_account_performance_from_replay(
        context.portfolio,
        account_id=subject,
        base_currency="CNY",
        source_refs=(config.source_version, subject, schedule_source_ref),
        data_tier="synthetic",
        start_at=start,
        as_of=end,
        risk_policy=DailyRiskPolicy(
            expected_observation_dates=schedule_dates,
            annualization_factor=252,
        ),
    )
    behavior = build_period_behavior(
        frame,
        market,
        init_cash=config.initial_cash,
        start_date=start,
        end_date=end,
    )
    lifecycle = build_position_episode_lifecycle(
        frame,
        market,
        subject_id=subject,
        account_id=subject,
        as_of=cutoff - pd.Timedelta(nanoseconds=1),
        init_cash=config.initial_cash,
        data_tier="synthetic",
        calculation_code_version=config.source_version,
    )
    state = {s.state_id:s for s in lifecycle.states}
    episodes = {e.episode_id:e for e in lifecycle.episodes}
    operations = []
    for d in lifecycle.decisions:
        if not (pd.Timestamp(start).date() < d.occurred_at.date() <= pd.Timestamp(end).date()):
            continue
        before, after = state[d.state_before_ref], state[d.state_after_ref]
        operations.append(dict(decision_id=d.decision_id, episode_id=d.episode_id,
            date=d.occurred_at.isoformat(), symbol=episodes[d.episode_id].instrument_id,
            kind=d.decision_type, quantity=d.executed_quantity, execution_price=d.execution_price,
            before_quantity=before.quantity, after_quantity=after.quantity,
            before_cost=before.average_cost, after_cost=after.average_cost, fee=d.fees))
    benchmark = market[market.instrument == config.benchmark_symbol].set_index("date")["close"].loc[start:end]
    returns = empyrical.simple_returns(benchmark)
    benchmark_nav = empyrical.cum_returns(returns, starting_value=100)
    points = [dict(date=start, nav=100.0), *[dict(date=d.date().isoformat(), nav=float(v)) for d,v in benchmark_nav.items()]]
    allocation = _allocation(context, end, config=config)
    return _PeriodBuild(
        payload=dict(
            start_date=start,
            end_date=end,
            boundary="start_exclusive_end_inclusive",
            performance=performance.as_dict(),
            risk_schedule=dict(
                kind=config.synthetic_schedule,
                source_ref=schedule_source_ref,
                annualization_factor=252,
                risk_free_source_ref=None,
            ),
            behavior=asdict(behavior),
            allocation=allocation.payload,
            operations=operations,
            benchmark=dict(
                name=config.benchmark_symbol,
                data_tier="synthetic",
                period_return=float(empyrical.cum_returns_final(returns)),
                points=points,
            ),
            source_ref=f"{config.source_version}:{subject}:{start}:{end}",
        ),
        performance=performance,
        behavior=behavior,
        lookthrough=allocation.lookthrough,
    )


def build_comparison_export(
    *,
    subjects: Sequence[str],
    input_provider: Callable[[str], tuple[pd.DataFrame, pd.DataFrame]],
    period_labels: Sequence[tuple[str, str, str]],
    names: dict[str, dict[str, str]],
    config: ComparisonExportConfig,
    schema_version: str = VERSION,
    as_of: object | None = None,
    source_version: str | None = None,
) -> dict[str, object]:
    """Build one adapter-compatible synthetic comparison export.

    This is orchestration only: all financial values continue to be produced
    by the existing replay and projection builders invoked by :func:`_period`.
    """
    if not subjects:
        raise ValueError("comparison export requires at least one subject")
    period_map = {label: (start, end) for label, start, end in period_labels}
    if set(period_map) != {"earlier", "recent", "full"} or len(period_map) != 3:
        raise ValueError("comparison export requires earlier, recent, and full periods")

    accounts = []
    inputs: list[tuple[str, pd.DataFrame, pd.DataFrame]] = []
    typed_periods: dict[str, dict[str, _PeriodBuild]] = {}
    for subject in subjects:
        executions, prices = input_provider(subject)
        inputs.append((subject, executions, prices))
        subject_periods = {
            key: _period(subject, executions, prices, start, end, config=config)
            for key, start, end in period_labels
        }
        typed_periods[subject] = subject_periods
        accounts.append(
            dict(
                subject_id=subject,
                account_id=subject,
                data_tier="synthetic",
                initial_cash=config.initial_cash,
                periods={key: value.payload for key, value in subject_periods.items()},
            )
        )

    default_subject = subjects[0]
    self_earlier = typed_periods[default_subject]["earlier"]
    self_recent = typed_periods[default_subject]["recent"]
    self_comparison = compare_account_periods(
        self_earlier.performance,
        self_recent.performance,
        kind="self_periods",
        left_behavior=self_earlier.behavior,
        right_behavior=self_recent.behavior,
        left_lookthrough=self_earlier.lookthrough,
        right_lookthrough=self_recent.lookthrough,
    )
    professional_comparisons = {}
    for professional_subject in subjects[1:]:
        by_period = {}
        for period_name in ("full", "earlier", "recent"):
            left = typed_periods[default_subject][period_name]
            right = typed_periods[professional_subject][period_name]
            by_period[period_name] = asdict(
                compare_account_periods(
                    left.performance,
                    right.performance,
                    kind="professional",
                    left_behavior=left.behavior,
                    right_behavior=right.behavior,
                    left_lookthrough=left.lookthrough,
                    right_lookthrough=right.lookthrough,
                )
            )
        professional_comparisons[professional_subject] = by_period
    payload = dict(
        schema_version=schema_version,
        data_tier="synthetic",
        as_of=period_map["full"][1] if as_of is None else as_of,
        calendar=config.synthetic_schedule,
        currency="CNY",
        default_subject=default_subject,
        names=names,
        accounts=accounts,
        comparisons=dict(
            self=asdict(self_comparison),
            professional=professional_comparisons,
        ),
        input_sha256=_study_input_sha256(inputs),
        capabilities=dict(
            performance=True,
            cashflow_boundary_performance=True,
            direct_allocation=True,
            dated_lookthrough=True,
            period_behavior=True,
            broker_connection=False,
            corporate_action_replay=False,
            account_agent=False,
        ),
    )
    if source_version is not None:
        # Schema compatibility is intentionally independent from the source
        # facts' version; desktop adapters may keep a stable schema contract.
        payload["source_version"] = source_version
    return payload


def build_research_demo() -> dict[str, object]:
    """Build the legacy three-account demo with its unchanged default facts."""

    return build_comparison_export(
        subjects=SUBJECTS,
        input_provider=study_inputs,
        period_labels=(
            ("earlier", START, MIDDLE),
            ("recent", MIDDLE, END),
            ("full", START, END),
        ),
        names=NAMES,
        config=RESEARCH_DEMO_CONFIG,
    )

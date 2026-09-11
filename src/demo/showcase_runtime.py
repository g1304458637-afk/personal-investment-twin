"""Runtime adapters for the one shared synthetic product showcase.

The source module intentionally contains only inputs.  This module is the
single place that qualifies its display symbols for review facts and binds its
pre-trade request to a declared 2025 synthetic cohort.  It does not implement
portfolio, outcome, HHI, or comparison calculations.
"""

from __future__ import annotations

import pandas as pd

from src.agents.review_sources import build_owned_self_history
from src.cohort.models import CohortDefinition
from src.compare.same_stock import build_episode_compare_facts, compare_same_stock
from src.core.canonical_execution import instrument_ref
from src.demo import showcase
from src.episodes.position_episode import build_position_episode_lifecycle
from src.history.metric_series import build_portfolio_hhi_history
from src.pretrade.impact import ProposedTrade, TradeImpact, simulate_trade_impact


DATA_MODE = "synthetic_showcase"
CALCULATION_CODE_VERSION = "showcase_runtime_v1"
SHOWCASE_COHORT_ID = "synthetic-showcase-2025-reference-v1"


def _account_for(subject_id: str) -> str:
    if subject_id not in showcase.SUBJECTS:
        raise ValueError("unregistered_showcase_subject")
    return subject_id


def is_showcase_scope(subject_id: object, account_id: object) -> bool:
    return (
        isinstance(subject_id, str)
        and isinstance(account_id, str)
        and subject_id in showcase.SUBJECTS
        and account_id == subject_id
    )


def source_fingerprint(subject_id: str, account_id: str) -> str:
    """Fingerprint only an exact registered showcase account scope."""
    if not is_showcase_scope(subject_id, account_id):
        raise ValueError("unregistered_showcase_scope")
    return showcase.source_fingerprint(subject_id)


def _instrument(symbol: str):
    security_type = "fund" if symbol == "SYN_FUND" else "equity"
    names = showcase.NAMES[symbol]
    return instrument_ref(
        local_symbol=symbol,
        market="SYNTHETIC",
        security_type=security_type,
        currency="CNY",
        display_symbol=symbol,
        display_name=names["en"],
    )


def _inputs(subject_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    account_id = _account_for(subject_id)
    executions, prices = showcase.showcase_inputs(subject_id)
    if not executions.subject_id.eq(subject_id).all() or not executions.account_id.eq(account_id).all():
        raise ValueError("showcase_execution_scope_mismatch")
    return executions, prices


def _qualified_inputs(subject_id: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    executions, prices = _inputs(subject_id)
    instruments = {symbol: _instrument(symbol) for symbol in showcase.SYMBOLS}
    if not executions.symbol.isin(instruments).all():
        raise ValueError("showcase_execution_instrument_mismatch")
    # SYN_MARKET is an explicitly declared price-only series; retaining it in
    # the full-account market frame preserves all source observations.
    qualified_prices = prices.copy(deep=True)
    qualified_prices["instrument"] = qualified_prices["instrument"].map(
        lambda value: instruments[value].instrument_id if value in instruments else value
    )
    qualified = executions.copy(deep=True)
    qualified["symbol"] = qualified["symbol"].map(lambda value: instruments[value].instrument_id)
    return qualified, qualified_prices, instruments


def _lifecycle(executions: pd.DataFrame, prices: pd.DataFrame, *, subject_id: str):
    return build_position_episode_lifecycle(
        executions,
        prices,
        subject_id=subject_id,
        account_id=_account_for(subject_id),
        as_of=showcase.AS_OF,
        init_cash=showcase.INITIAL_CASH,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
    )


def _episode_mapping(subject_id: str) -> tuple[dict[str, dict[str, object]], pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Map each legacy display Episode to its qualified replay Episode by refs."""
    legacy_executions, raw_prices = _inputs(subject_id)
    frame, market, instruments = _qualified_inputs(subject_id)
    legacy = _lifecycle(legacy_executions, raw_prices, subject_id=subject_id)
    canonical = _lifecycle(frame, market, subject_id=subject_id)
    canonical_by_refs = {item.execution_refs: item for item in canonical.episodes}
    legacy_decisions = {item.execution_id: item.decision_id for item in legacy.decisions}
    canonical_decisions = {item.execution_id: item.decision_id for item in canonical.decisions}
    mapping: dict[str, dict[str, object]] = {}
    for display in legacy.episodes:
        qualified = canonical_by_refs.get(display.execution_refs)
        if qualified is None:
            raise ValueError("showcase_episode_identity_mismatch")
        display_symbol = next(
            symbol for symbol, item in instruments.items()
            if item.instrument_id == qualified.instrument_id
        )
        decision_mapping = {
            canonical_decisions[execution_id]: legacy_decisions[execution_id]
            for execution_id in display.execution_refs
        }
        value = {
            "version": CALCULATION_CODE_VERSION,
            "display_episode_id": display.episode_id,
            "canonical_episode_id": qualified.episode_id,
            "display_instrument_id": display_symbol,
            "canonical_instrument_id": qualified.instrument_id,
            "decision_display_ids": decision_mapping,
        }
        mapping[display.episode_id] = value
        mapping[qualified.episode_id] = value
    return mapping, frame, market, instruments


def load_showcase_review(subject_id: str, account_id: str, episode_id: str):
    """Build one selected showcase Episode from the full registered account."""
    if not is_showcase_scope(subject_id, account_id):
        raise ValueError("unregistered_showcase_scope")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise ValueError("episode_id_required")
    mapping, frame, market, instruments = _episode_mapping(subject_id)
    identity = mapping.get(episode_id)
    if identity is None:
        raise ValueError("showcase_episode_scope_mismatch")
    instrument = next(
        item for item in instruments.values()
        if item.instrument_id == identity["canonical_instrument_id"]
    )
    own = build_episode_compare_facts(
        frame,
        market,
        subject_id=subject_id,
        account_id=account_id,
        instrument=instrument,
        as_of=showcase.AS_OF,
        init_cash=showcase.INITIAL_CASH,
        data_tier="synthetic",
        episode_id=str(identity["canonical_episode_id"]),
    )
    if own.episode.execution_refs != tuple(
        next(item.execution_refs for item in _lifecycle(frame, market, subject_id=subject_id).episodes
             if item.episode_id == own.episode.episode_id)
    ):
        raise ValueError("showcase_selected_episode_identity_mismatch")
    return own, frame, market, dict(identity)


def _first_growth_episode(subject_id: str) -> str:
    mapping, frame, market, instruments = _episode_mapping(subject_id)
    growth_id = instruments["SYN_GROWTH"].instrument_id
    lifecycle = _lifecycle(frame, market, subject_id=subject_id)
    selected = next((item for item in lifecycle.episodes if item.instrument_id == growth_id), None)
    if selected is None:
        raise ValueError("showcase_growth_episode_unavailable")
    return str(mapping[selected.episode_id]["canonical_episode_id"])


def build_showcase_pair():
    """Return the existing comparison plus its A/B display-to-canonical maps."""
    main_id = _first_growth_episode(showcase.SUBJECT_ID)
    reference_id = _first_growth_episode(showcase.REFERENCE_SUBJECT)
    main, _, _, main_mapping = load_showcase_review(showcase.SUBJECT_ID, showcase.SUBJECT_ID, main_id)
    reference, _, _, reference_mapping = load_showcase_review(
        showcase.REFERENCE_SUBJECT, showcase.REFERENCE_SUBJECT, reference_id
    )
    return compare_same_stock(main, reference), {"A": main_mapping, "B": reference_mapping}


def build_showcase_same_stock_comparison():
    """Compatibility wrapper for callers that only need comparison facts."""
    return build_showcase_pair()[0]


def showcase_cohort_definition() -> CohortDefinition:
    """Declared full-2025 reference cohort; one account is not descriptive."""
    return CohortDefinition(
        cohort_id=SHOWCASE_COHORT_ID,
        market="synthetic-showcase-market",
        asset_types=("equity", "fund"),
        direction="long_only",
        observation_start=pd.Timestamp(showcase.START),
        observation_end=pd.Timestamp(showcase.END),
        leverage_allowed=False,
        data_tier="synthetic",
        min_descriptive_n=30,
        description="Full-2025 synthetic showcase reference-account cohort.",
        limitations=(
            "The reference account is fictional and is not a population sample.",
            "One reference account is insufficient for descriptive peer statistics.",
        ),
    )


def simulate_showcase_trade(trade: ProposedTrade) -> TradeImpact:
    """Run pre-trade replay for the main showcase account only.

    The full-year definition deliberately requires 30 peers.  No peer
    population is fabricated from the reference account, so the result exposes
    the existing replay, Evidence adapters, self context, and delta only.
    """
    if trade.subject_id != showcase.SUBJECT_ID:
        raise ValueError("showcase_trade_subject_not_available")
    executions, prices = _inputs(showcase.SUBJECT_ID)
    history = build_portfolio_hhi_history(
        executions,
        prices,
        init_cash=showcase.INITIAL_CASH,
        subject_id=showcase.SUBJECT_ID,
        data_tier="synthetic",
        calculation_code_version=CALCULATION_CODE_VERSION,
    )
    definition = showcase_cohort_definition()
    return simulate_trade_impact(
        trade,
        executions,
        prices,
        init_cash=showcase.INITIAL_CASH,
        hhi_history=history,
        cohort_definition=definition,
        peer_members=(),
        peer_metric_values=(),
        calculation_code_version=CALCULATION_CODE_VERSION,
        include_peer_context=False,
    )


def build_showcase_self_history():
    """Expose the same full account review history used by showcase Episodes."""
    frame, market, _ = _qualified_inputs(showcase.SUBJECT_ID)
    return build_owned_self_history(
        frame, market, subject_id=showcase.SUBJECT_ID, account_id=showcase.SUBJECT_ID,
        as_of=showcase.AS_OF, init_cash=showcase.INITIAL_CASH, data_tier="synthetic",
    )

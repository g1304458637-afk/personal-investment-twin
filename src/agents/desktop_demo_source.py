"""Explicit legacy-display to qualified-instrument mapping for three examples.

Only identifiers change in the replay input. Execution IDs, ordering, prices,
quantities and fees are preserved. Agent facts use canonical identities; the
display mapping is navigation metadata, never substituted into Evidence refs.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path

import pandas as pd

from src.compare.same_stock import build_episode_compare_facts
from src.core.canonical_execution import instrument_ref
from src.data.csv_importer import load_normalized_csv
from src.episodes.position_episode import build_position_episode_lifecycle


@dataclass(frozen=True, slots=True)
class DemoSource:
    name: str
    symbol: str
    executions: str
    prices: str
    as_of: str
    market_symbol: str


SOURCES = (
    DemoSource("product-story", "SYN_PRODUCT", "product_demo_executions_v1.csv",
               "product_demo_market_prices_v1.csv", "2025-05-20 23:59:00", "600000.SH"),
    DemoSource("long-horizon-closed", "SYN_LONG_CLOSED", "long_horizon_closed_executions_v1.csv",
               "long_horizon_closed_market_prices_v1.csv", "2025-07-16 23:59:00", "SYN_LONG_CLOSED"),
    DemoSource("long-horizon-open", "SYN_LONG_OPEN", "long_horizon_open_executions_v1.csv",
               "long_horizon_open_market_prices_v1.csv", "2026-01-15 23:59:00", "SYN_LONG_OPEN"),
)
SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "data" / "sample"


def source_for(subject, account):
    for source in SOURCES:
        if (subject, account) == (f"demo-user:{source.name}", f"demo-account:{source.name}"):
            return source
    raise ValueError("unregistered_synthetic_episode_scope")


def source_fingerprint(subject, account):
    source = source_for(subject, account)
    digest = hashlib.sha256(repr(source).encode())
    for filename in (source.executions, source.prices):
        digest.update((SAMPLE_ROOT / filename).read_bytes())
    return digest.hexdigest()


def load_demo_review(subject, account, episode_id):
    source = source_for(subject, account)
    original = load_normalized_csv(SAMPLE_ROOT / source.executions)
    market = pd.read_csv(SAMPLE_ROOT / source.prices)
    if not original.symbol.eq(source.symbol).all() or not market.instrument.eq(source.market_symbol).all():
        raise ValueError("synthetic_source_instrument_mismatch")
    market = market.assign(instrument=source.symbol)
    kwargs = dict(subject_id=subject, account_id=account, as_of=pd.Timestamp(source.as_of),
                  init_cash=100_000.0, data_tier="synthetic")
    legacy = build_position_episode_lifecycle(original, market, **kwargs,
                                             calculation_code_version="demo_review_identity_v1")
    if len(legacy.episodes) != 1:
        raise ValueError("ambiguous_synthetic_episode")
    instrument = instrument_ref(local_symbol=source.symbol, market="SYNTHETIC",
                                security_type="equity", currency="CNY")
    frame = original.assign(symbol=instrument.instrument_id, subject_id=subject, account_id=account)
    market = market.assign(instrument=instrument.instrument_id)
    own = build_episode_compare_facts(frame, market, instrument=instrument, **kwargs)
    if episode_id not in {legacy.episodes[0].episode_id, own.episode.episode_id}:
        raise ValueError("synthetic_episode_scope_mismatch")
    if own.episode.execution_refs != legacy.episodes[0].execution_refs:
        raise ValueError("synthetic_execution_identity_mismatch")
    canonical = build_position_episode_lifecycle(frame, market, **kwargs,
                                                calculation_code_version="demo_review_identity_v1")
    old_decisions = {d.execution_id: d.decision_id for d in legacy.decisions}
    mapping = {d.decision_id: old_decisions[d.execution_id] for d in canonical.decisions}
    return own, frame, market, {"version": "demo_review_identity_v1",
        "display_episode_id": legacy.episodes[0].episode_id,
        "canonical_episode_id": own.episode.episode_id,
        "display_instrument_id": source.symbol,
        "canonical_instrument_id": instrument.instrument_id,
        "decision_display_ids": mapping}

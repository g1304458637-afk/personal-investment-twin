"""Deterministic review_pack.v1 builder over a LocalRepository.

``build_review_pack(repo, subject_id, account_id)`` assembles the fixed
review_pack.v1 schema (exit quality, realized-PnL calendar, tilt observations,
playbook tag aggregation) purely from canonical facts already stored in the
repository: executions, daily closes and the user's own episode tags.

Iron rules honored here:
- every financial number is computed deterministically from canonical facts;
- every section carries explicit limitations;
- insufficient evidence yields empty sections / null fields, never a guess;
- only observable facts are described; no psychological motive is inferred;
- no network access and no clock: ``as_of`` is the repository's data boundary
  (the latest market observation, falling back to the latest execution day).

Episode segmentation and realized PnL are delegated to the existing
vectorbt-backed builders (``src.episodes.position_episode`` and
``src.attribution.decision_outcome``) — the same sources the investments
endpoint uses; this package never reinvents position accounting.
"""

from __future__ import annotations

import pandas as pd

from src.core.canonical_execution import CanonicalExecutionError, canonical_executions_to_frame
from src.market_data.models import facts_to_market_data_frame
from src.review_pack.calendar_pnl import build_calendar_rows
from src.review_pack.exit_quality import build_exit_quality_rows
from src.review_pack.playbook import build_playbook
from src.review_pack.tilt import SECTION_LIMITATIONS as TILT_SECTION_LIMITATIONS
from src.review_pack.tilt import detect_tilt

SCHEMA_VERSION = "review_pack.v1"
CALCULATION_CODE_VERSION = "review_pack_v1"
DATA_TIER = "authorized_beta"
MIN_EXECUTIONS_FOR_TILT = 20


def build_review_pack(repo, subject_id: str, account_id: str) -> dict:
    """Return the fixed review_pack.v1 dict for one account.

    Pure and deterministic: no network, no wall clock — ``as_of`` is derived
    from the repository data boundary.  Raises ``ValueError`` only when the
    account itself does not exist; every data-insufficiency case degrades to
    explicit limitations inside the fixed schema instead.
    """

    if not isinstance(subject_id, str) or not subject_id.strip() or not isinstance(account_id, str) or not account_id.strip():
        raise ValueError("subject_id and account_id must be non-empty strings")
    subject_id, account_id = subject_id.strip(), account_id.strip()
    accounts = [item for item in repo.list_accounts()
                if item["subject_id"] == subject_id and item["account_id"] == account_id]
    if not accounts:
        raise ValueError("account not found")
    init_cash = float(accounts[0]["initial_cash"])

    executions = repo.executions(subject_id, account_id)
    price_facts = repo.prices(subject_id, account_id)
    execution_count = len(executions)
    execution_dates = [pd.Timestamp(item.event_time.calendar_date) for item in executions]
    price_dates = [pd.Timestamp(item.date) for item in price_facts]
    as_of = max(price_dates).date().isoformat() if price_dates else (
        max(execution_dates).date().isoformat() if execution_dates else None)

    empty_pack = _empty_sections()
    if not executions:
        return _assemble(subject_id, account_id, as_of, execution_count, 0,
                         execution_dates, empty_pack)
    try:
        frame = canonical_executions_to_frame(executions)
    except CanonicalExecutionError as exc:  # canonical contract failure: fail closed, explain
        return _degraded_pack(subject_id, account_id, as_of, execution_count,
                              execution_dates, empty_pack, f"canonical 成交不可重放：{exc}")

    price_frame = facts_to_market_data_frame(price_facts) if price_facts else pd.DataFrame(
        columns=["date", "instrument", "close", "price_type", "data_source", "data_version", "is_synthetic"])
    mixed_currencies = _mixed_currencies(executions, price_facts)

    lifecycle = None
    actual = None
    degrade_reasons: list[str] = []
    if price_facts:
        try:
            from src.attribution.decision_outcome import build_actual_outcomes
            from src.episodes.position_episode import build_position_episode_lifecycle
            lifecycle, actual = _build_lifecycle_and_outcomes(
                build_position_episode_lifecycle, build_actual_outcomes,
                frame, price_frame, max(price_dates).normalize(), subject_id, account_id, init_cash)
        except (ValueError, KeyError) as exc:
            # Contract-level data failures degrade with an explanation; genuine
            # programming errors still propagate loudly.
            degrade_reasons.append(f"episode 生命周期不可用（等待完整日线市场数据）：{exc}")
    else:
        degrade_reasons.append("账户无任何日线市场数据，episode 生命周期不可用。")

    closed_items: list[dict] = []
    all_episode_ids: set[str] = set()
    panel_days = sorted({pd.Timestamp(value).normalize() for value in price_frame["date"]}) if not price_frame.empty else []
    if lifecycle is not None and actual is not None:
        pnl_by_episode = {outcome.episode_id: float(outcome.actual_result.pnl)
                          for outcome in actual.episode_outcomes}
        outcome_by_decision = {item.decision_event_id: item.immediate_result
                               for item in actual.decision_outcomes}
        decisions_by_episode: dict[str, list] = {}
        for decision in lifecycle.decisions:
            decisions_by_episode.setdefault(decision.episode_id, []).append(decision)
        for episode in lifecycle.episodes:
            all_episode_ids.add(episode.episode_id)
            if episode.status != "closed" or episode.closed_at is None:
                continue
            exit_pnl: dict[str, float] = {}
            for decision in decisions_by_episode.get(episode.episode_id, ()):
                immediate = outcome_by_decision.get(decision.decision_id)
                if immediate is not None:
                    exit_pnl[decision.decision_id] = float(immediate.pnl)
            open_day = pd.Timestamp(episode.opened_at).normalize()
            close_day = pd.Timestamp(episode.closed_at).normalize()
            closes = _window_closes(price_frame, str(episode.instrument_id), open_day, close_day)
            missing_days = sum(1 for day in panel_days if open_day <= day <= close_day and day not in closes)
            closed_items.append({
                "episode_id": episode.episode_id,
                "instrument_id": str(episode.instrument_id),
                "realized_pnl": pnl_by_episode[episode.episode_id],
                "closed_at": episode.closed_at,
                "hold_days": int(episode.duration_days),
                "decisions": tuple(decisions_by_episode.get(episode.episode_id, ())),
                "exit_pnl_by_decision": exit_pnl,
                "closes": closes,
                "missing_days": missing_days,
            })

    exit_rows, exit_limitations = build_exit_quality_rows(closed_items)
    calendar_rows = build_calendar_rows(closed_items)

    if price_dates:
        boundary_day = max(price_dates).normalize()
        beyond_boundary = int(sum(1 for row in frame.itertuples()
                                  if pd.Timestamp(row.market_date).normalize() > boundary_day))
        if beyond_boundary:
            note = f"有 {beyond_boundary} 笔成交晚于最后市场观测日，等待市场数据，未纳入 episode 分析。"
            exit_limitations.append(note)
            calendar_rows["limitations"].append(note)
    if mixed_currencies:
        note = "账户内存在多种币种或币种未知，金额未做汇率换算，跨标的大小不可直接相加。"
        exit_limitations.append(note)
        calendar_rows["limitations"].append(note)
    exit_limitations.extend(degrade_reasons)

    trading_days = sorted({pd.Timestamp(value).normalize() for value in price_dates} |
                          {pd.Timestamp(value).normalize() for value in execution_dates})
    tilt_observations: list[dict] = []
    tilt_limitations = list(TILT_SECTION_LIMITATIONS)
    if lifecycle is not None:
        closed_exits = [{
            "exit_day": pd.Timestamp(episode.closed_at).normalize(),
            "instrument_id": str(episode.instrument_id),
            "realized_pnl": pnl_by_episode[episode.episode_id],
        } for episode in lifecycle.episodes if episode.status == "closed" and episode.closed_at is not None]
        closed_exits.sort(key=lambda item: item["exit_day"])  # streaks run in close order
        tilt_observations = detect_tilt(
            [pd.Timestamp(value).normalize() for value in frame["market_date"]],
            [str(value) for value in frame["symbol"]],
            [str(value) for value in frame["side"]],
            [float(quantity) * float(price) for quantity, price
             in zip(frame["executed_quantity"], frame["executed_price"])],
            trading_days,
            closed_exits,
        )
    else:
        tilt_limitations.extend(degrade_reasons)
    if execution_count < MIN_EXECUTIONS_FOR_TILT:
        tilt_limitations.append(
            f"当前全历史成交 {execution_count} 笔，不足 {MIN_EXECUTIONS_FOR_TILT} 笔，样本不足，不输出观察。")

    tags_by_episode, tag_limitations = _load_tags(repo, subject_id, account_id)
    playbook = build_playbook(closed_items, tags_by_episode, all_episode_ids)
    episode_tags = [{"episode_id": episode_id, "tags": tags}
                    for episode_id, tags in sorted(tags_by_episode.items())
                    if episode_id in all_episode_ids]

    return _assemble(
        subject_id, account_id, as_of, execution_count, len(all_episode_ids),
        execution_dates,
        {
            "exit_quality": {"episodes": exit_rows, "limitations": exit_limitations},
            "calendar": calendar_rows,
            "behavior_flags": {"tilt": tilt_observations, "limitations": tilt_limitations},
            "playbook": playbook,
            "episode_tags": episode_tags,
        },
    )


def _build_lifecycle_and_outcomes(build_lifecycle, build_outcomes, frame, price_frame,
                                  valuation_date, subject_id, account_id, init_cash):
    """Reuse the exact product-runtime lifecycle path (no re-invented replay)."""

    # Same convention as product.py: a daily observation date is not a
    # midnight cutoff; include the canonical instants of supported days.
    execution_cutoff = valuation_date
    supported = frame.loc[frame["market_date"] <= valuation_date, "event_time"]
    if not supported.empty:
        execution_cutoff = max(execution_cutoff, pd.Timestamp(supported.max()))
    lifecycle = build_lifecycle(
        frame, price_frame, subject_id=subject_id, account_id=account_id,
        as_of=execution_cutoff, init_cash=init_cash, data_tier=DATA_TIER,
        calculation_code_version=CALCULATION_CODE_VERSION)
    actual = build_outcomes(
        lifecycle, frame, price_frame, subject_id=subject_id, account_id=account_id,
        analysis_as_of=lifecycle.as_of, init_cash=init_cash)
    return lifecycle, actual


def _window_closes(price_frame: pd.DataFrame, instrument_id: str,
                   open_day: pd.Timestamp, close_day: pd.Timestamp) -> dict[pd.Timestamp, float]:
    """Observed closes of one instrument inside one episode window; no fill."""

    if price_frame.empty:
        return {}
    rows = price_frame[price_frame["instrument"] == instrument_id]
    if rows.empty:
        return {}
    dates = pd.to_datetime(rows["date"], errors="raise").dt.normalize()
    selected = rows.loc[(dates >= open_day) & (dates <= close_day)]
    if selected.empty:
        return {}
    selected_dates = pd.to_datetime(selected["date"], errors="raise").dt.normalize()
    return {pd.Timestamp(day).normalize(): float(close)
            for day, close in zip(selected_dates, selected["close"])}


def _load_tags(repo, subject_id: str, account_id: str) -> tuple[dict[str, list[str]], list[str]]:
    """Read the user's own tags through the existing ReviewStore read-model."""

    from src.agents.review_store import ReviewStore
    try:
        store = ReviewStore(repo.connection)
        rows = store.list_tags(subject_id, account_id)
    except Exception as exc:  # read-model failure must not break the pack
        return {}, [f"episode 标签读取失败：{exc}"]
    return {row["episode_id"]: list(row["tags"]) for row in rows}, []


def _mixed_currencies(executions, price_facts) -> bool:
    currencies = {item.fee.currency.upper() for item in executions if item.fee.currency}
    currencies.update(item.instrument.currency.upper() for item in executions if item.instrument.currency)
    currencies.update(item.currency.upper() for item in price_facts if item.currency)
    if not currencies:
        return False
    if any(not item.instrument.currency for item in executions):
        return True
    return len(currencies) > 1


def _empty_sections() -> dict:
    exit_rows, exit_limitations = build_exit_quality_rows([])
    return {
        "exit_quality": {"episodes": [], "limitations": list(exit_limitations)},
        "calendar": build_calendar_rows([]),
        "behavior_flags": {"tilt": [], "limitations": list(TILT_SECTION_LIMITATIONS)},
        "playbook": build_playbook([], {}, set()),
        "episode_tags": [],
    }


def _degraded_pack(subject_id, account_id, as_of, execution_count, execution_dates,
                   sections, reason: str) -> dict:
    sections["exit_quality"]["limitations"].append(reason)
    sections["behavior_flags"]["limitations"].append(reason)
    return _assemble(subject_id, account_id, as_of, execution_count, 0, execution_dates, sections)


def _assemble(subject_id, account_id, as_of, execution_count, episode_count,
              execution_dates, sections) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "subject_id": subject_id,
        "account_id": account_id,
        "as_of": as_of,
        "coverage": {
            "execution_count": execution_count,
            "episode_count": episode_count,
            "first_date": min(execution_dates).date().isoformat() if execution_dates else None,
            "last_date": max(execution_dates).date().isoformat() if execution_dates else None,
        },
        "exit_quality": sections["exit_quality"],
        "calendar": sections["calendar"],
        "behavior_flags": sections["behavior_flags"],
        "playbook": sections["playbook"],
        "episode_tags": sections["episode_tags"],
    }

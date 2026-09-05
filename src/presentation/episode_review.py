"""Product disclosure projection over existing Path facts; no financial arithmetic."""

import pandas as pd


def review_presentation(lifecycle, analysis):
    episode = next(item for item in lifecycle.episodes if item.episode_id == analysis.episode_id)
    decisions = {item.decision_id: item for item in lifecycle.decisions if item.episode_id == episode.episode_id}
    phases = {item.phase_id: item for item in analysis.phases}
    patterns = {item.pattern_id: item for item in analysis.patterns}
    # Preserve canonical Path phase order; never sort executions a second time.
    eligible_phases = [phase for phase in analysis.phases
                       if phase.episode_id == episode.episode_id
                       and phase.ended_at <= lifecycle.as_of
                       and all(ref in decisions for ref in phase.decision_event_ids)]
    story_phases = eligible_phases if len(eligible_phases) <= 4 else eligible_phases[:1]
    facts, seen = [], set()
    # The existing selector owns ordering. This layer only gates/deduplicates it.
    for item in analysis.presentation_items:
        pattern = patterns.get(item.pattern_id)
        if pattern is None or pattern.episode_id != episode.episode_id:
            continue
        if any(ref not in decisions for ref in pattern.decision_event_ids):
            continue
        phase = phases.get(item.phase_id)
        data = pattern.facts
        start = data.get("window_start") or data.get("started_at") or data.get("peak_observed_at")
        end = data.get("window_end") or data.get("ended_at") or data.get("trough_observed_at")
        start = pd.Timestamp(start) if start is not None else phase.started_at if phase else None
        end = pd.Timestamp(end) if end is not None else phase.ended_at if phase else None
        if start is None or end is None or pd.isna(start) or pd.isna(end) or start > end:
            continue
        if end > lifecycle.as_of or any(decisions[ref].occurred_at > lifecycle.as_of for ref in pattern.decision_event_ids):
            continue
        if pattern.pattern_code == "high_quantity_during_daily_price_drawdown" and data.get("quantity_at_trough_status") != "available":
            continue
        key = (pattern.pattern_code, tuple(sorted(pattern.decision_event_ids)), start.isoformat(), end.isoformat())
        if key in seen:
            continue
        seen.add(key)
        facts.append({"item_id": item.item_id, "pattern_id": pattern.pattern_id,
                      "phase_id": item.phase_id, "decision_ids": pattern.decision_event_ids,
                      "start_at": start.isoformat(), "end_at": end.isoformat()})
        if len(facts) == 3:
            break
    return {"version": "1", "episode_id": episode.episode_id,
            "story_steps": [{"phase_id": phase.phase_id, "decision_count": len(phase.decision_event_ids)}
                            for phase in story_phases],
            "story_abbreviated": len(eligible_phases) > 4, "facts": facts}

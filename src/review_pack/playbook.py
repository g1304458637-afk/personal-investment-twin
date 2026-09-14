"""Playbook aggregation over user-authored episode tags.

Tags come exclusively from the user's own retrospective labels (the
review_episode_tags_v1 read-model); the pack never invents tags.  Each tag is
joined with the closed episodes that carry it:

- win = closed episode's net realized PnL > 0;
- total_pnl sums those episodes' realized PnL;
- win_rate is reported ONLY when at least MIN_EPISODES_FOR_WIN_RATE episodes
  carry the tag (otherwise it is null and confidence is "insufficient" —
  insufficient evidence is never scored);
- untagged_episode_count reports closed episodes without any tag.
"""

from __future__ import annotations

MIN_EPISODES_FOR_WIN_RATE = 5

SECTION_LIMITATIONS: tuple[str, ...] = (
    "标签来自用户事后人工标注（review_episode_tags_v1），不是系统推断；标签口径由用户自定义。",
    "win_rate 仅在携带该标签的已闭合 episode 数 ≥ 5 时给出，否则置信度为 insufficient 且不给评分。",
    "win 定义为已闭合 episode 净已实现盈亏 > 0（含费净额口径）。",
    "标签聚合是描述性统计，不构成任何策略建议或因果结论。",
)


def build_playbook(
    closed_episodes: list[dict],
    tags_by_episode: dict[str, list[str]],
    known_episode_ids: set[str],
) -> dict:
    """Aggregate tags over closed episodes.

    ``closed_episodes`` items carry episode_id and realized_pnl.  Tags whose
    episode id is unknown to this account's lifecycle are dropped and counted
    in the limitations instead of being silently mixed in.
    """

    stats: dict[str, dict] = {}
    dropped_unknown = 0
    for episode_id, tags in sorted(tags_by_episode.items()):
        if episode_id not in known_episode_ids:
            dropped_unknown += 1
            continue
        matched = next((item for item in closed_episodes if item["episode_id"] == episode_id), None)
        if matched is None:
            continue  # open episodes exist but are outside every closed-only aggregate
        pnl = float(matched["realized_pnl"])
        for tag in tags:
            entry = stats.setdefault(
                tag, {"tag": tag, "episode_count": 0, "win_count": 0, "total_pnl": 0.0})
            entry["episode_count"] += 1
            entry["win_count"] += int(pnl > 0)
            entry["total_pnl"] += pnl

    tags_rows: list[dict] = []
    for tag in sorted(stats):
        entry = stats[tag]
        sufficient = entry["episode_count"] >= MIN_EPISODES_FOR_WIN_RATE
        tags_rows.append({
            "tag": entry["tag"],
            "episode_count": entry["episode_count"],
            "win_count": entry["win_count"],
            "total_pnl": entry["total_pnl"],
            "win_rate": entry["win_count"] / entry["episode_count"] if sufficient else None,
            "confidence": "sufficient" if sufficient else "insufficient",
        })
    untagged = sum(
        1 for item in closed_episodes
        if not tags_by_episode.get(item["episode_id"]))
    limitations = list(SECTION_LIMITATIONS)
    if dropped_unknown:
        limitations.append(f"有 {dropped_unknown} 个标签记录指向本账户未知的 episode，已忽略。")
    return {
        "tags": tags_rows,
        "untagged_episode_count": untagged,
        "limitations": limitations,
    }

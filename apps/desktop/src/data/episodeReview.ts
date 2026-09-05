import type { EpisodePathAnalysisView, PositionEpisodeView } from "./positionEpisode";

export interface EpisodeReview {
  version: string;
  storySteps: { phaseId: string; decisionCount: number }[];
  abbreviated: boolean;
  facts: { itemId: string; patternId: string; phaseId: string | null; decisionIds: string[]; startAt: string; endAt: string }[];
}

export function adaptEpisodeReview(value: unknown, episode: PositionEpisodeView, path: EpisodePathAnalysisView): EpisodeReview | null {
  if (value === undefined || value === null) return null; // Older payloads remain readable, without invented summaries.
  const raw = value as { version: string; episode_id: string; story_steps: {phase_id: string; decision_count: number}[]; story_abbreviated: boolean; facts: {item_id: string; pattern_id: string; phase_id: string | null; decision_ids: string[]; start_at: string; end_at: string}[] };
  if (raw.version !== "1" || raw.episode_id !== episode.episodeId || !Array.isArray(raw.story_steps) || !Array.isArray(raw.facts) || raw.facts.length > 3) throw new Error("Invalid review presentation scope");
  const storySteps = raw.story_steps.map((step) => {
    const phase = path.phases.find((item) => item.phaseId === step.phase_id);
    if (!phase || step.decision_count !== phase.decisionEventIds.length) throw new Error("Invalid review story source");
    return {phaseId: step.phase_id, decisionCount: step.decision_count};
  });
  const seen = new Set<string>();
  const facts = raw.facts.map((fact) => {
    const source = path.presentationItems.find((item) => item.itemId === fact.item_id);
    const pattern = path.patterns.find((item) => item.patternId === fact.pattern_id);
    if (!source || !pattern || source.patternId !== fact.pattern_id || source.phaseId !== fact.phase_id || seen.has(fact.item_id)
      || !Array.isArray(fact.decision_ids) || fact.decision_ids.length !== pattern.decisionEventIds.length
      || fact.decision_ids.some((id, index) => id !== pattern.decisionEventIds[index])
      || !Number.isFinite(Date.parse(fact.start_at)) || !Number.isFinite(Date.parse(fact.end_at)) || Date.parse(fact.start_at) > Date.parse(fact.end_at)) throw new Error("Invalid review fact source");
    seen.add(fact.item_id);
    return {itemId: fact.item_id, patternId: fact.pattern_id, phaseId: fact.phase_id, decisionIds: fact.decision_ids, startAt: fact.start_at, endAt: fact.end_at};
  });
  return {version: raw.version, storySteps, abbreviated: raw.story_abbreviated, facts};
}

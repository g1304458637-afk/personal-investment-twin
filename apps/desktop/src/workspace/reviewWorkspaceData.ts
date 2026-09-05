import type { RuntimeInvestments } from "@/data/runtimeService";
import type { PositionEpisodeEntryView } from "@/data/positionEpisode";

/** A deliberately thin index over already-authoritative Episode projections. */
export interface ReviewEpisodeCandidate {
  episodeId: string;
  subjectId: string;
  accountId: string;
  instrumentName: string;
  instrumentId: string;
  status: "open" | "closed";
  openedAt: string;
  closedAt: string | null;
  durationDays: number;
  decisionCount: number | null;
  reviewFactCount: number | null;
  source: "runtime" | "synthetic_fixture";
}

function chronological<T extends ReviewEpisodeCandidate>(items: T[]) {
  return items.sort((left, right) => Date.parse(right.openedAt) - Date.parse(left.openedAt) || left.episodeId.localeCompare(right.episodeId));
}

export function reviewCandidatesFromFixture(entries: readonly PositionEpisodeEntryView[], subjectId: string, accountId: string): ReviewEpisodeCandidate[] {
  return chronological(entries
    .filter((entry) => entry.episode.subjectId === subjectId && entry.episode.accountId === accountId)
    .map((entry) => ({
      episodeId: entry.episode.episodeId,
      subjectId: entry.episode.subjectId,
      accountId: entry.episode.accountId,
      instrumentName: entry.instrument.displayName,
      instrumentId: entry.instrument.instrumentId,
      status: entry.episode.status,
      openedAt: entry.episode.openedAt,
      closedAt: entry.episode.closedAt,
      durationDays: entry.episode.durationDays,
      decisionCount: entry.decisions.length,
      reviewFactCount: entry.reviewPresentation?.facts.length ?? 0,
      source: "synthetic_fixture",
    })));
}

export function reviewCandidatesFromRuntime(value: RuntimeInvestments): ReviewEpisodeCandidate[] {
  return chronological(value.episodes.map((episode) => ({
    episodeId: episode.episode_id,
    subjectId: value.subject_id,
    accountId: value.account_id,
    instrumentName: episode.display_name,
    instrumentId: episode.instrument_id,
    status: episode.status,
    openedAt: episode.opened_at,
    closedAt: episode.closed_at,
    durationDays: episode.duration_days,
    // investments.list is intentionally an index projection; it makes no claim about review facts.
    decisionCount: null,
    reviewFactCount: null,
    source: "runtime",
  })));
}

export function scopedCandidate(candidates: readonly ReviewEpisodeCandidate[], episodeId: string | null): ReviewEpisodeCandidate | null {
  return candidates.find((candidate) => candidate.episodeId === episodeId) ?? candidates[0] ?? null;
}

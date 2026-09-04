import type {
  PositionEpisodeDemoView,
  PositionEpisodeEntryView,
  PositionEpisodeStatus,
} from "./positionEpisode";

export type InvestmentsPortfolioStatus = "available" | "not_started" | "unavailable";

export interface BackendInvestmentsPayload {
  subject_id: string;
  as_of: string;
  data_tier: "synthetic";
  portfolio_state_status: InvestmentsPortfolioStatus;
  portfolio_state_reason: string | null;
  summary: {
    open_episode_count: number;
    closed_episode_count: number;
    current_position_count: number;
  };
  open_episode_ids: string[];
  closed_episode_ids: string[];
}

export interface InvestmentEpisodeRowView {
  episodeId: string;
  subjectId: string;
  instrumentId: string;
  displayName: string;
  isSynthetic: true;
  status: PositionEpisodeStatus;
  openedAt: string;
  closedAt: string | null;
  durationDays: number;
  durationKind: "final" | "so_far";
  quantity: number | null;
  averageCost: number | null;
  valuationAt: string | null;
  valuationPrice: number | null;
  marketValue: number | null;
}

export interface InvestmentsView {
  subjectId: string;
  asOf: string;
  dataTier: "synthetic";
  portfolioState: {
    status: InvestmentsPortfolioStatus;
    reason: string | null;
  };
  summary: {
    openEpisodeCount: number;
    closedEpisodeCount: number;
    currentPositionCount: number;
  };
  openEpisodes: InvestmentEpisodeRowView[];
  closedEpisodes: InvestmentEpisodeRowView[];
}

function requiredText(value: unknown, name: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Investments ${name} is required.`);
  }
  return value;
}

function count(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(`Investments ${name} must be a non-negative integer.`);
  }
  return value;
}

function row(entry: PositionEpisodeEntryView): InvestmentEpisodeRowView {
  const state = entry.snapshot?.positionState ?? null;
  return {
    episodeId: entry.episode.episodeId,
    subjectId: entry.episode.subjectId,
    instrumentId: entry.episode.instrumentId,
    displayName: entry.instrument.displayName,
    isSynthetic: true,
    status: entry.episode.status,
    openedAt: entry.episode.openedAt,
    closedAt: entry.episode.closedAt,
    durationDays: entry.episode.durationDays,
    durationKind: entry.episode.durationKind,
    quantity: state?.quantity ?? null,
    averageCost: state?.averageCost ?? null,
    valuationAt: state?.valuationAt ?? null,
    valuationPrice: state?.valuationPrice ?? null,
    marketValue: state?.marketValue ?? null,
  };
}

export function adaptInvestmentsPayload(
  value: BackendInvestmentsPayload,
  episodes: PositionEpisodeDemoView,
): InvestmentsView {
  if (value.data_tier !== "synthetic" || episodes.dataTier !== "synthetic") {
    throw new Error("Desktop investments demo must remain explicitly synthetic.");
  }
  const subjectId = requiredText(value.subject_id, "subject_id");
  if (Number.isNaN(Date.parse(value.as_of))) {
    throw new Error("Investments as_of must be a timestamp.");
  }
  if (!["available", "not_started", "unavailable"].includes(value.portfolio_state_status)) {
    throw new Error("Investments portfolio state is unsupported.");
  }
  const byId = new Map(episodes.entries.map((entry) => [entry.episode.episodeId, entry]));
  const resolve = (episodeId: string, expected: PositionEpisodeStatus) => {
    const entry = byId.get(episodeId);
    if (!entry || entry.episode.subjectId !== subjectId || entry.episode.status !== expected) {
      throw new Error(`Investments ${expected} Episode ${episodeId} does not resolve for this subject.`);
    }
    return row(entry);
  };
  const openEpisodes = value.open_episode_ids.map((id) => resolve(id, "open"));
  const closedEpisodes = value.closed_episode_ids.map((id) => resolve(id, "closed"));
  const openEpisodeCount = count(value.summary.open_episode_count, "open_episode_count");
  const closedEpisodeCount = count(value.summary.closed_episode_count, "closed_episode_count");
  const currentPositionCount = count(value.summary.current_position_count, "current_position_count");
  if (openEpisodeCount !== openEpisodes.length || closedEpisodeCount !== closedEpisodes.length) {
    throw new Error("Investments summary counts must match the authoritative Episode references.");
  }
  return {
    subjectId,
    asOf: value.as_of,
    dataTier: "synthetic",
    portfolioState: {
      status: value.portfolio_state_status,
      reason: value.portfolio_state_reason,
    },
    summary: { openEpisodeCount, closedEpisodeCount, currentPositionCount },
    openEpisodes,
    closedEpisodes,
  };
}

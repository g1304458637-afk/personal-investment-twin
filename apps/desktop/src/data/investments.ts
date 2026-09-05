import type {
  PositionEpisodeDemoView,
  PositionEpisodeEntryView,
  PositionEpisodeStatus,
} from "./positionEpisode";

export type InvestmentsPortfolioStatus = "available" | "not_started" | "unavailable";

export interface ArchiveOutcome {
  result_kind: "realized" | "marked" | "unavailable";
  pnl: number | null;
  return_value: number | null;
  result_at: string | null;
  availability: "available" | "unavailable";
  reason: string | null;
  outcome_id: string | null;
}

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
  isSynthetic: boolean;
  currency: string | null;
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
  outcome: ArchiveOutcome;
}

export interface InvestmentsView {
  subjectId: string;
  asOf: string;
  dataTier: "synthetic" | "authorized_beta";
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
  primaryEpisodeId: string | null;
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
  const actual = entry.outcomeStory.episodeOutcome;
  return {
    episodeId: entry.episode.episodeId,
    subjectId: entry.episode.subjectId,
    instrumentId: entry.episode.instrumentId,
    displayName: entry.instrument.displayName,
    isSynthetic: true,
    currency: entry.instrument.currency,
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
    outcome: {
      result_kind: actual.actualResult.resultKind === "marked" ? "marked" : "realized",
      pnl: actual.actualResult.pnl, return_value: actual.actualResult.returnValue,
      result_at: entry.episode.status === "open" ? actual.actualResult.valuationAt : entry.episode.closedAt,
      availability: "available", reason: null, outcome_id: actual.outcomeId,
    },
  };
}

export function archiveRows(rows: InvestmentEpisodeRowView[], status: "open" | "closed" | "all", query: string): InvestmentEpisodeRowView[] {
  const term = query.trim().toLocaleLowerCase();
  return rows.filter((item) => (status === "all" || item.status === status)
    && `${item.displayName} ${item.instrumentId}`.toLocaleLowerCase().includes(term))
    .sort((a, b) => Date.parse(b.openedAt) - Date.parse(a.openedAt) || a.episodeId.localeCompare(b.episodeId));
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
    primaryEpisodeId: null,
  };
}

export function adaptDemoInvestmentsCatalog(
  episodes: PositionEpisodeDemoView,
): InvestmentsView {
  const primary = episodes.entries.find((entry) => entry.episode.episodeId === episodes.defaultEpisodeId);
  if (!primary) {
    throw new Error("Demo investments catalog is missing the primary Product Demo Episode.");
  }
  const remainder = episodes.entries.filter((entry) => entry.episode.episodeId !== episodes.defaultEpisodeId);
  const ordered = [primary, ...remainder];
  const openEpisodes = ordered.filter((entry) => entry.episode.status === "open").map(row);
  const closedEpisodes = ordered.filter((entry) => entry.episode.status === "closed").map(row);
  let asOf = primary.episode.closedAt ?? primary.episode.openedAt;
  for (const entry of ordered) {
    const candidate = entry.episode.closedAt ?? entry.snapshot?.asOf ?? entry.episode.openedAt;
    if (Date.parse(candidate) > Date.parse(asOf)) asOf = candidate;
  }
  return {
    subjectId: primary.episode.subjectId,
    asOf,
    dataTier: "synthetic",
    portfolioState: { status: "available", reason: null },
    summary: {
      openEpisodeCount: openEpisodes.length,
      closedEpisodeCount: closedEpisodes.length,
      currentPositionCount: openEpisodes.length,
    },
    openEpisodes,
    closedEpisodes,
    primaryEpisodeId: primary.episode.episodeId,
  };
}

/**
 * Transport adapter for the account-level review_pack.v1 artifact.
 *
 * Validation only: no finance is computed in the browser. Every number shown
 * by the review panels comes from this validated payload (backend runtime, or
 * the fail-closed-checked demo artifact); malformed or hostile payloads fail
 * closed as a whole instead of rendering partially trusted numbers.
 */

export type ReviewPackConfidence = "sufficient" | "insufficient";

export interface ReviewPackCoverageView {
  executionCount: number;
  episodeCount: number;
  firstDate: string | null;
  lastDate: string | null;
}

export interface ReviewPackExitEpisodeView {
  episodeId: string;
  instrument: string;
  mfeAmount: number | null;
  maeAmount: number | null;
  mfePct: number | null;
  maePct: number | null;
  realizedPnl: number | null;
  status: string;
  exitEfficiency: number | null;
  givebackRatio: number | null;
  facts: { peakDate: string | null; troughDate: string | null; holdDays: number | null };
  limitations: string[];
}

export interface ReviewPackCalendarMonthView { month: string; realizedPnl: number; closedCount: number; winCount: number }
export interface ReviewPackCalendarDayView { date: string; realizedPnl: number; closedCount: number }

export interface ReviewPackCalendarView {
  months: ReviewPackCalendarMonthView[];
  days: ReviewPackCalendarDayView[];
  limitations: string[];
}

export interface ReviewPackTiltFlagView {
  trigger: string;
  triggerDate: string;
  window: {
    days: number;
    // Nullable when the trigger day has no observed trading day after it:
    // the window could not be evaluated and the item says so.
    tradeCount: number | null;
    baselineTradeCount: number | null;
    avgSizeChangePct: number | null;
    sameInstrumentRebuyCount: number | null;
  };
  note: string;
  limitations: string[];
}

export interface ReviewPackPlaybookTagView {
  tag: string;
  episodeCount: number;
  winCount: number;
  totalPnl: number;
  winRate: number | null;
  confidence: ReviewPackConfidence;
}

export interface ReviewPackView {
  subjectId: string;
  accountId: string;
  asOf: string;
  coverage: ReviewPackCoverageView;
  exitQuality: { episodes: ReviewPackExitEpisodeView[]; limitations: string[] };
  calendar: ReviewPackCalendarView;
  behaviorFlags: { tilt: ReviewPackTiltFlagView[]; limitations: string[] };
  playbook: { tags: ReviewPackPlaybookTagView[]; untaggedEpisodeCount: number; limitations: string[] };
  episodeTags: { episodeId: string; tags: string[] }[];
}

const fail = (): never => { throw new Error("review_pack_invalid"); };
const object = (x: unknown): Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x) ? x as Record<string, unknown> : fail();
const text = (x: unknown): string => typeof x === "string" && x.trim().length > 0 && x.length <= 6000 ? x : fail();
const finite = (x: unknown): number => typeof x === "number" && Number.isFinite(x) ? x : fail();
const nonNegativeFinite = (x: unknown): number => { const value = finite(x); return value >= 0 ? value : fail(); };
const nullableFinite = (x: unknown): number | null => x === null ? null : finite(x);
const nullableNonNegativeFinite = (x: unknown): number | null => x === null ? null : nonNegativeFinite(x);
const array = (x: unknown): unknown[] => Array.isArray(x) && x.length <= 50000 ? x : fail();
const textList = (x: unknown): string[] => array(x).map((item) => text(item));
const day = (x: unknown): string => {
  const s = text(x);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !Number.isFinite(Date.parse(s)) || new Date(s).toISOString().slice(0, 10) !== s) fail();
  return s;
};
const nullableDay = (x: unknown): string | null => x === null ? null : day(x);
const monthKey = (x: unknown): string => {
  const s = text(x);
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(s)) fail();
  return s;
};
const confidence = (x: unknown): ReviewPackConfidence => x === "sufficient" || x === "insufficient" ? x : fail();

function coverage(raw: unknown): ReviewPackCoverageView {
  const value = object(raw);
  return {
    executionCount: nonNegativeFinite(value.execution_count),
    episodeCount: nonNegativeFinite(value.episode_count),
    firstDate: nullableDay(value.first_date),
    lastDate: nullableDay(value.last_date),
  };
}

function exitEpisode(raw: unknown): ReviewPackExitEpisodeView {
  const value = object(raw);
  const facts = object(value.facts);
  return {
    episodeId: text(value.episode_id),
    instrument: text(value.instrument),
    mfeAmount: nullableFinite(value.mfe_amount),
    maeAmount: nullableFinite(value.mae_amount),
    mfePct: nullableFinite(value.mfe_pct),
    maePct: nullableFinite(value.mae_pct),
    realizedPnl: nullableFinite(value.realized_pnl),
    status: text(value.status),
    exitEfficiency: nullableFinite(value.exit_efficiency),
    givebackRatio: nullableFinite(value.giveback_ratio),
    facts: {
      peakDate: nullableDay(facts.peak_date),
      troughDate: nullableDay(facts.trough_date),
      holdDays: nullableNonNegativeFinite(facts.hold_days),
    },
    limitations: textList(value.limitations),
  };
}

function calendarMonth(raw: unknown): ReviewPackCalendarMonthView {
  const value = object(raw);
  const closedCount = nonNegativeFinite(value.closed_count);
  const winCount = nonNegativeFinite(value.win_count);
  // Structural invariant: more wins than closed episodes is impossible.
  if (winCount > closedCount) fail();
  return { month: monthKey(value.month), realizedPnl: finite(value.realized_pnl), closedCount, winCount };
}

function calendarDay(raw: unknown): ReviewPackCalendarDayView {
  const value = object(raw);
  return { date: day(value.date), realizedPnl: finite(value.realized_pnl), closedCount: nonNegativeFinite(value.closed_count) };
}

function tiltFlag(raw: unknown): ReviewPackTiltFlagView {
  const value = object(raw);
  const window = object(value.window);
  return {
    trigger: text(value.trigger),
    triggerDate: day(value.trigger_date),
    window: {
      days: nonNegativeFinite(window.days),
      tradeCount: nullableNonNegativeFinite(window.trade_count),
      baselineTradeCount: nullableNonNegativeFinite(window.baseline_trade_count),
      avgSizeChangePct: nullableFinite(window.avg_size_change_pct),
      sameInstrumentRebuyCount: nullableNonNegativeFinite(window.same_instrument_rebuy_count),
    },
    note: text(value.note),
    limitations: textList(value.limitations),
  };
}

function playbookTag(raw: unknown): ReviewPackPlaybookTagView {
  const value = object(raw);
  const episodeCount = nonNegativeFinite(value.episode_count);
  const winCount = nonNegativeFinite(value.win_count);
  if (winCount > episodeCount) fail();
  return {
    tag: text(value.tag),
    episodeCount,
    winCount,
    totalPnl: finite(value.total_pnl),
    winRate: nullableFinite(value.win_rate),
    confidence: confidence(value.confidence),
  };
}

function episodeTags(raw: unknown): { episodeId: string; tags: string[] }[] {
  const rows = array(raw).map((item) => {
    const value = object(item);
    return { episodeId: text(value.episode_id), tags: textList(value.tags) };
  });
  if (new Set(rows.map((row) => row.episodeId)).size !== rows.length) fail();
  return rows;
}

export function adaptReviewPack(raw: unknown): ReviewPackView {
  const value = object(raw);
  if (value.schema_version !== "review_pack.v1") fail();
  const exitEpisodes = array(object(value.exit_quality).episodes).map(exitEpisode);
  // Episode ids must be unique: matching by episode_id downstream would
  // otherwise be ambiguous and could render another episode's numbers.
  if (new Set(exitEpisodes.map((episode) => episode.episodeId)).size !== exitEpisodes.length) fail();
  const months = array(object(value.calendar).months).map(calendarMonth);
  for (let index = 1; index < months.length; index += 1) {
    if (months[index].month <= months[index - 1].month) fail();
  }
  const days = array(object(value.calendar).days).map(calendarDay);
  for (let index = 1; index < days.length; index += 1) {
    if (days[index].date <= days[index - 1].date) fail();
  }
  const playbook = object(value.playbook);
  const tags = array(playbook.tags).map(playbookTag);
  if (new Set(tags.map((tag) => tag.tag)).size !== tags.length) fail();
  return {
    subjectId: text(value.subject_id),
    accountId: text(value.account_id),
    asOf: text(value.as_of),
    coverage: coverage(value.coverage),
    exitQuality: {
      episodes: exitEpisodes,
      limitations: textList(object(value.exit_quality).limitations),
    },
    calendar: {
      months,
      days,
      limitations: textList(object(value.calendar).limitations),
    },
    behaviorFlags: {
      tilt: array(object(value.behavior_flags).tilt).map(tiltFlag),
      limitations: textList(object(value.behavior_flags).limitations),
    },
    playbook: {
      tags,
      untaggedEpisodeCount: nonNegativeFinite(playbook.untagged_episode_count),
      limitations: textList(playbook.limitations),
    },
    episodeTags: episodeTags(value.episode_tags),
  };
}

/** Exit-quality facts for one episode, or null when the pack has no record. */
export function episodeExitQuality(pack: ReviewPackView, episodeId: string): ReviewPackExitEpisodeView | null {
  return pack.exitQuality.episodes.find((episode) => episode.episodeId === episodeId) ?? null;
}

/** Current tags for one episode, or an empty list when none are recorded. */
export function episodeTagsFor(pack: ReviewPackView, episodeId: string): string[] {
  return pack.episodeTags.find((row) => row.episodeId === episodeId)?.tags ?? [];
}

/** Playbook aggregate for one tag, or null when the tag has no aggregate yet. */
export function playbookTagFor(pack: ReviewPackView, tag: string): ReviewPackPlaybookTagView | null {
  return pack.playbook.tags.find((row) => row.tag === tag) ?? null;
}

export interface ReviewHeatmapCell {
  month: string;
  realizedPnl: number;
  closedCount: number;
  winCount: number;
}

export interface ReviewHeatmapYear {
  year: string;
  /** Twelve fixed calendar slots; null where the backend reported no month. */
  cells: (ReviewHeatmapCell | null)[];
}

/**
 * Pure layout preparation for the monthly heatmap: groups the backend-provided
 * months into years with twelve fixed calendar slots. No financial value is
 * derived here — every rendered number is copied from the payload.
 */
export function prepareMonthlyHeatmap(months: readonly ReviewPackCalendarMonthView[]): ReviewHeatmapYear[] {
  const byYear = new Map<string, Map<string, ReviewHeatmapCell>>();
  for (const month of months) {
    const year = month.month.slice(0, 4);
    (byYear.get(year) ?? byYear.set(year, new Map()).get(year)!).set(month.month, { ...month });
  }
  return [...byYear.keys()].sort().map((year) => ({
    year,
    cells: Array.from({ length: 12 }, (_unused, index) => {
      const key = `${year}-${String(index + 1).padStart(2, "0")}`;
      return byYear.get(year)!.get(key) ?? null;
    }),
  }));
}

// ---------------------------------------------------------------------------
// Episode tag editor client validation. The desktop runtime enforces the same
// limits server-side; the client mirrors them so the chips input never emits
// a payload the backend would reject.
// ---------------------------------------------------------------------------

export const EPISODE_TAG_MAX_LENGTH = 24;
export const EPISODE_TAG_MAX_COUNT = 8;

export type EpisodeTagEditResult =
  | { ok: true; tags: string[] }
  | { ok: false; reason: "tag_too_long" | "too_many_tags" | "duplicate_tag" };

/**
 * Adds one user-typed tag to an episode's tag list: strips surrounding
 * whitespace, drops empties, rejects over-long tags, and dedupes against the
 * existing tags (exact match after trimming). Never mutates the input.
 */
export function addEpisodeTag(existing: readonly string[], rawInput: string): EpisodeTagEditResult {
  const tag = rawInput.trim();
  if (tag.length === 0) return { ok: false, reason: "duplicate_tag" };
  if (tag.length > EPISODE_TAG_MAX_LENGTH) return { ok: false, reason: "tag_too_long" };
  if (existing.some((candidate) => candidate === tag)) return { ok: false, reason: "duplicate_tag" };
  if (existing.length >= EPISODE_TAG_MAX_COUNT) return { ok: false, reason: "too_many_tags" };
  return { ok: true, tags: [...existing, tag] };
}

/** Removes one tag; unknown tags leave the list unchanged. */
export function removeEpisodeTag(existing: readonly string[], tag: string): string[] {
  return existing.filter((candidate) => candidate !== tag);
}

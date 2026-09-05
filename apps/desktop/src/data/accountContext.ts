import type { PositionEpisodeEntryView } from "./positionEpisode";

export interface ExampleAccount {
  key: string;
  subjectId: string;
  accountId: string;
  label: string;
}

export function exampleAccounts(entries: PositionEpisodeEntryView[]): ExampleAccount[] {
  const accounts = new Map<string, ExampleAccount>();
  for (const entry of entries) {
    const { subjectId, accountId } = entry.episode;
    const key = JSON.stringify([subjectId, accountId]);
    if (!accounts.has(key)) accounts.set(key, { key, subjectId, accountId, label: entry.instrument.displayName });
  }
  return [...accounts.values()];
}

export function belongsToExample(entry: PositionEpisodeEntryView, account: ExampleAccount): boolean {
  return entry.episode.subjectId === account.subjectId && entry.episode.accountId === account.accountId;
}

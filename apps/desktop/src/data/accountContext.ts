import type { PositionEpisodeEntryView } from "./positionEpisode";

export interface ExampleAccount {
  key: string;
  subjectId: string;
  accountId: string;
  label: { zh: string; en: string };
}

export function exampleAccounts(entries: PositionEpisodeEntryView[], labelFor?: (entry: PositionEpisodeEntryView) => ExampleAccount["label"]): ExampleAccount[] {
  const accounts = new Map<string, ExampleAccount>();
  for (const entry of entries) {
    const { subjectId, accountId } = entry.episode;
    const key = JSON.stringify([subjectId, accountId]);
    if (!accounts.has(key)) accounts.set(key, { key, subjectId, accountId, label: labelFor?.(entry) ?? { zh: entry.instrument.displayName, en: entry.instrument.displayName } });
  }
  return [...accounts.values()];
}

export function exampleAccountLabel(account: ExampleAccount, locale: string): string {
  return locale === "zh-CN" ? account.label.zh : account.label.en;
}

export function belongsToExample(entry: PositionEpisodeEntryView, account: ExampleAccount): boolean {
  return entry.episode.subjectId === account.subjectId && entry.episode.accountId === account.accountId;
}

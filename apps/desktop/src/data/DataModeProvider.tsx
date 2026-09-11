import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { isTauriRuntime, realUserApi, type RuntimeAccount } from "./runtimeService";
import { readCurrentAccounts } from "./currentAccountRead";
import { positionEpisodeDemo } from "./backendEvidence";
import { exampleAccounts, type ExampleAccount } from "./accountContext";
import { showcaseDemo } from "./showcaseDemo";
import { reviewSessions } from "./reviewService";

const examples = exampleAccounts(positionEpisodeDemo.entries, () => showcaseDemo.showcase.display_name);
const primary = positionEpisodeDemo.entries.find((entry) => entry.episode.episodeId === positionEpisodeDemo.defaultEpisodeId)!;
const defaultExample = examples.find((account) => account.subjectId === primary.episode.subjectId && account.accountId === primary.episode.accountId)!;

type DataMode = "demo" | "real_user";
interface State { mode: DataMode; setMode: (mode: DataMode) => void; accounts: RuntimeAccount[]; activeAccount: RuntimeAccount | null; setActiveAccount: (account: RuntimeAccount | null) => void; refresh: () => Promise<void>; runtimeAvailable: boolean; accountsLoading: boolean; accountError: string | null; examples: ExampleAccount[]; exampleAccount: ExampleAccount; setExampleAccount: (account: ExampleAccount) => void }
const Context = createContext<State | null>(null);

export function DataModeProvider({ children }: { children: ReactNode }) {
  const runtimeAvailable = isTauriRuntime();
  // A new app session always starts with the user's accounts, never an old demo preference.
  const [mode, setModeState] = useState<DataMode>("real_user");
  const [exampleAccount, setExampleAccount] = useState(defaultExample);
  const [accountsLoading, setAccountsLoading] = useState(runtimeAvailable);
  const [accounts, setAccounts] = useState<RuntimeAccount[]>([]);
  const [activeAccount, setActiveAccount] = useState<RuntimeAccount | null>(null);
  const generation = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const refresh = async () => {
    if (!runtimeAvailable) return;
    const request = ++generation.current;
    setAccountsLoading(true);
    let result;
    try {
      result = await readCurrentAccounts(realUserApi.accounts, () => request === generation.current);
    } catch (value) {
      if (request !== generation.current) return;
      setError(String(value));
      setAccountsLoading(false);
      throw value;
    }
    if (!result || request !== generation.current) return;
    setError(null);
    setAccountsLoading(false);
    setAccounts(result.accounts);
    setActiveAccount((current) => result.accounts.find((x) => x.account_id === current?.account_id && x.subject_id === current?.subject_id) ?? result.accounts[0] ?? null);
  };
  useEffect(() => {
    void refresh().catch(() => { /* Current failures are already displayed by refresh. */ });
    return () => { generation.current += 1; };
  }, []); // runtime lifecycle is app-scoped
  useEffect(() => {
    if (!runtimeAvailable || accountsLoading) return;
    let cancelled = false;
    // Allow first paint/account selection first. Warm one likely review, not a
    // queue of every account's expensive histories. No model or public API call.
    const timer = setTimeout(() => {
      const warm = async () => {
        if (mode === "demo" || !activeAccount) {
          const account = mode === "demo" ? exampleAccount : defaultExample;
          const entries = positionEpisodeDemo.entries.filter(entry => entry.episode.subjectId === account.subjectId && entry.episode.accountId === account.accountId);
          const episode = entries.find(entry => entry.episode.episodeId === positionEpisodeDemo.defaultEpisodeId)?.episode ?? entries[0]?.episode;
          if (episode && !cancelled) await reviewSessions.prefetch({subject_id:episode.subjectId, account_id:account.accountId, episode_id:episode.episodeId, data_mode:"synthetic_showcase"});
        } else {
          const result = await realUserApi.investments(activeAccount.subject_id, activeAccount.account_id);
          const episode = result.episodes[0];
          if (episode && !cancelled) await reviewSessions.prefetch({subject_id:activeAccount.subject_id, account_id:activeAccount.account_id, episode_id:episode.episode_id, data_mode:"real_user"});
        }
      };
      void warm().catch(() => { /* Opening analysis offers a retry. */ });
    }, 800);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [runtimeAvailable, accountsLoading, mode, activeAccount?.subject_id, activeAccount?.account_id, exampleAccount.key]);
  const setMode = (next: DataMode) => { setModeState(next); };
  const value = useMemo(() => ({ mode, setMode, accounts, activeAccount, setActiveAccount, refresh, runtimeAvailable, accountsLoading, accountError: error, examples, exampleAccount, setExampleAccount }), [mode, accounts, activeAccount, runtimeAvailable, accountsLoading, error, exampleAccount]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useDataMode() { const value = useContext(Context); if (!value) throw new Error("DataModeProvider missing"); return value; }

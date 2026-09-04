import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { isTauriRuntime, realUserApi, type RuntimeAccount } from "./runtimeService";

type DataMode = "demo" | "real_user";
interface State { mode: DataMode; setMode: (mode: DataMode) => void; accounts: RuntimeAccount[]; activeAccount: RuntimeAccount | null; setActiveAccount: (account: RuntimeAccount | null) => void; refresh: () => Promise<void>; runtimeAvailable: boolean }
const Context = createContext<State | null>(null);

export function DataModeProvider({ children }: { children: ReactNode }) {
  const runtimeAvailable = isTauriRuntime();
  const [mode, setModeState] = useState<DataMode>(() => localStorage.getItem("toujing.dataMode") === "real_user" ? "real_user" : "demo");
  const [accounts, setAccounts] = useState<RuntimeAccount[]>([]);
  const [activeAccount, setActiveAccount] = useState<RuntimeAccount | null>(null);
  const refresh = async () => {
    if (!runtimeAvailable) return;
    const result = await realUserApi.accounts();
    setAccounts(result.accounts);
    setActiveAccount((current) => result.accounts.find((x) => x.account_id === current?.account_id && x.subject_id === current?.subject_id) ?? result.accounts[0] ?? null);
  };
  useEffect(() => { void refresh(); }, []); // runtime lifecycle is app-scoped
  const setMode = (next: DataMode) => { localStorage.setItem("toujing.dataMode", next); setModeState(next); };
  const value = useMemo(() => ({ mode, setMode, accounts, activeAccount, setActiveAccount, refresh, runtimeAvailable }), [mode, accounts, activeAccount, runtimeAvailable]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useDataMode() { const value = useContext(Context); if (!value) throw new Error("DataModeProvider missing"); return value; }

import { AnimatePresence, motion } from "motion/react";
import { ArrowDownUp, ArrowUpRight, BookOpen, ChevronRight, Database, FolderOpen, History, MessageCircle, ScanLine, Search, Settings2, ShieldCheck, Sun, Moon } from "lucide-react";
import { useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { useLocale } from "@/locales/LocaleProvider";
import { useTheme } from "@/components/layout/ThemeProvider";
import { ContextualInspectorHost } from "@/components/inspector/ContextualInspectorHost";
import { useWorkspaceCopy } from "./copy";
import { workspaceDestinations, workspaceSection } from "./workspaceMode";
import "./intelligence-workspace.css";

const icons = { investments: FolderOpen, review: ScanLine, history: History, comparison: ArrowDownUp, pretrade: ScanLine, journal: BookOpen, data: Database, settings: Settings2 };

export function IntelligenceShell({ openCommands }: { openCommands: () => void }) {
  const data = useDataMode();
  const { t } = useLocale();
  const c = useWorkspaceCopy();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const section = workspaceSection(location.pathname);
  const selected = workspaceDestinations.find((item) => item.path === section);
  const account = data.mode === "demo" ? t(data.exampleAccount.label) : data.activeAccount?.display_name ?? c.noAccount;
  const contextKey = data.mode === "demo" ? data.exampleAccount.key : JSON.stringify([data.activeAccount?.subject_id, data.activeAccount?.account_id]);
  useEffect(() => { document.documentElement.dataset.workspace = "intelligence"; return () => { delete document.documentElement.dataset.workspace; }; }, []);
  useEffect(() => { document.querySelector("#workspace-content")?.scrollTo({ top: 0, behavior: "instant" }); }, [location.pathname]);
  const episodeId = location.pathname.startsWith("/investments/episodes/") ? decodeURIComponent(location.pathname.split("/").at(-1)!) : new URLSearchParams(location.search).get("episode");
  const askTarget = location.pathname === "/investments/compare-example" ? "/investments/compare-example?focus=analysis" : `/ask${episodeId ? `?episode=${encodeURIComponent(episodeId)}` : ""}`;
  return <div className="workspace-shell intelligence-workspace">
    <div className="iw-atmosphere" aria-hidden="true"><i /><i /></div>
    <aside className="iw-sidebar" aria-label={t("Primary navigation")}>
      <NavLink to="/investments" className="iw-brand" aria-label="投镜 Toujing">
        <span className="iw-emblem" aria-hidden="true"><i /><i /><i /></span>
        <span><strong>投镜<span>TOUJING</span></strong><small>{c.archive}</small></span>
      </NavLink>
      <div className="iw-account">
        <label htmlFor="account-context">{c.active}</label>
        <select id="account-context" aria-label={c.account}
          value={data.mode === "demo" ? `example:${data.exampleAccount.key}` : data.activeAccount ? `real:${JSON.stringify([data.activeAccount.subject_id, data.activeAccount.account_id])}` : "none"}
          onChange={(event) => {
            const value = event.target.value;
            if (value.startsWith("example:")) {
              const next = data.examples.find((item) => `example:${item.key}` === value);
              if (next) { data.setExampleAccount(next); data.setMode("demo"); }
            } else {
              data.setActiveAccount(data.accounts.find((item) => `real:${JSON.stringify([item.subject_id, item.account_id])}` === value) ?? null);
              data.setMode("real_user");
            }
          }}>
          {!data.accounts.length && <option value="none">{c.notImported}</option>}
          {data.accounts.map((item) => <option key={JSON.stringify([item.subject_id, item.account_id])} value={`real:${JSON.stringify([item.subject_id, item.account_id])}`}>{item.display_name}</option>)}
          <optgroup label={c.samples}>{data.examples.map((item) => <option key={item.key} value={`example:${item.key}`}>{t(item.label)}</option>)}</optgroup>
        </select>
        <span className={`iw-source-dot ${data.mode === "demo" ? "is-demo" : ""}`}>{data.mode === "demo" ? "SYNTHETIC" : "LOCAL / PRIVATE"}</span>
      </div>
      <nav className="iw-nav">
        {(["work", "record", "manage"] as const).map((group) => <div key={group} className="iw-nav-group"><span className="iw-kicker">{c[group]}</span>{workspaceDestinations.filter((item) => item.group === group).map((item) => {
          const Icon = icons[item.label]; const active = section === item.path;
          return <NavLink key={item.path} to={item.path} aria-current={active ? "page" : undefined} className={`iw-nav-link ${active ? "is-active" : ""}`}>
            {active && <motion.span className="iw-nav-selection" layoutId="intelligence-nav-selection" transition={{ type: "spring", stiffness: 360, damping: 35 }} />}
            <Icon size={18} aria-hidden="true" /><span>{c[item.label]}</span>{active && <ChevronRight size={13} aria-hidden="true" />}
          </NavLink>;
        })}</div>)}
      </nav>
      <div className="iw-sidebar-bottom"><ShieldCheck size={15} /><span>{c.scope}</span><a href={`?workspace=classic${location.hash || `#${location.pathname}`}`}>{c.classic}<ArrowUpRight size={12} /></a></div>
    </aside>
    <div className="workspace-main">
      <header className="iw-topbar">
        <div className="iw-breadcrumb" data-tauri-drag-region><span>WORKSPACE</span><ChevronRight size={13} /><strong>{selected ? c[selected.label] : c.ask}</strong></div>
        <div className="iw-top-actions"><span className="iw-runtime">{data.runtimeAvailable ? c.native : c.offline}</span><button className="iw-icon-button" onClick={openCommands} aria-label={c.search}><Search size={17} /></button><button className="iw-icon-button" onClick={toggleTheme} aria-label={t("Switch to {theme} mode", { theme: t(theme === "dark" ? "light" : "dark") })}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button><NavLink className="iw-ask" to={askTarget}><MessageCircle size={16} />{c.ask}<ArrowUpRight size={13} /></NavLink></div>
      </header>
      <div className={`iw-mode-strip ${data.mode === "demo" ? "is-demo" : ""}`}><span><i />{data.mode === "demo" ? c.example : c.local}</span><span className="iw-mode-account">{account}</span><span className="iw-mode-help" title={data.mode === "demo" ? c.modeHint : c.realHint}>{data.mode === "demo" ? c.modeHint : c.realHint}</span><button onClick={() => data.setMode(data.mode === "demo" ? "real_user" : "demo")}>{data.mode === "demo" ? c.exitPreview : c.preview}<ArrowUpRight size={12} /></button></div>
      <main className="workspace-content" id="workspace-content">
        <AnimatePresence mode="wait" initial={false}><motion.div key={`${location.pathname}:${data.mode}:${contextKey}`} className="route-frame" initial={{ opacity: 0, y: 9 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: .19 }}><Outlet /></motion.div></AnimatePresence>
      </main>
    </div>
    <ContextualInspectorHost />
  </div>;
}

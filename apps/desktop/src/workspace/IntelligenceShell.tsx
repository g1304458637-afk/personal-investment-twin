import { AnimatePresence, motion } from "motion/react";
import { ArrowDownUp, ArrowUpRight, BookOpen, ChevronRight, Database, FolderOpen, History, MessageCircle, ScanLine, Search, Settings2, ShieldCheck, Sun, Moon } from "lucide-react";
import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { exampleAccountLabel } from "@/data/accountContext";
import { useLocale } from "@/locales/LocaleProvider";
import { useTheme } from "@/components/layout/ThemeProvider";
import { ContextualInspectorHost } from "@/components/inspector/ContextualInspectorHost";
import { useWorkspaceCopy } from "./copy";
import { analysisLinks, liquidNavigation, liquidSection } from "./liquidNavigation";
import { useLiquidCopy } from "./liquidCopy";
import { LiquidBackdrop } from "./LiquidBackdrop";
import { GlassOrbLogo } from "@/components/common/GlassOrbLogo";

const icons = { investments: FolderOpen, review: ScanLine, history: History, comparison: ArrowDownUp, pretrade: ScanLine, journal: BookOpen, data: Database, settings: Settings2, ask: MessageCircle };

export function IntelligenceShell({ openCommands }: { openCommands: () => void }) {
  const data = useDataMode();
  const { t, locale } = useLocale();
  const c = useWorkspaceCopy();
  const glass = useLiquidCopy();
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const section = liquidSection(location.pathname);
  const selected = liquidNavigation.find((item) => item.path === section);
  const account = data.mode === "demo" ? exampleAccountLabel(data.exampleAccount, locale) : data.activeAccount?.display_name ?? c.noAccount;
  const contextKey = data.mode === "demo" ? data.exampleAccount.key : JSON.stringify([data.activeAccount?.subject_id, data.activeAccount?.account_id]);
  useEffect(() => { document.querySelector("#workspace-content")?.scrollTo({ top: 0, behavior: "instant" }); }, [location.pathname]);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);
  const askTarget = "/ask";
  return <div className={`workspace-shell intelligence-workspace liquid-workspace ${menuOpen ? "lg-menu-open" : ""}`} onPointerMove={(event) => {
    if (event.pointerType !== "mouse") return;
    const card = (event.target as HTMLElement).closest<HTMLElement>(".lg-interactive");
    if (!card) return;
    const rect = card.getBoundingClientRect();
    card.style.setProperty("--pointer-x", `${event.clientX - rect.left}px`);
    card.style.setProperty("--pointer-y", `${event.clientY - rect.top}px`);
  }}>
    <LiquidBackdrop />
    <aside className="iw-sidebar" aria-label={t("Primary navigation")}>
      <NavLink to="/welcome" className="iw-brand" aria-label="投镜 Toujing">
        <GlassOrbLogo />
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
          <optgroup label={c.samples}>{data.examples.map((item) => <option key={item.key} value={`example:${item.key}`}>{exampleAccountLabel(item, locale)}</option>)}</optgroup>
        </select>
        <span className={`iw-source-dot ${data.mode === "demo" ? "is-demo" : ""}`}>{data.mode === "demo" ? "SYNTHETIC" : "LOCAL / PRIVATE"}</span>
      </div>
      <nav className="iw-nav">
        {(["work", "manage"] as const).map((group) => <div key={group} className="iw-nav-group"><span className="iw-kicker">{c[group]}</span>{liquidNavigation.filter((item) => item.group === group).map((item) => {
          const Icon = icons[item.icon]; const active = section === item.path;
          return <NavLink key={item.path} to={item.path} aria-current={active ? "page" : undefined} className={`iw-nav-link ${active ? "is-active" : ""}`}>
            {active && <motion.span className="iw-nav-selection" layoutId="intelligence-nav-selection" transition={{ type: "spring", stiffness: 360, damping: 35 }} />}
            <Icon size={18} aria-hidden="true" /><span>{glass[item.label]}</span>{active && <ChevronRight size={13} aria-hidden="true" />}
          </NavLink>;
        })}</div>)}
      </nav>
      <div className="iw-sidebar-bottom"><ShieldCheck size={15} /><span>{c.scope}</span></div>
    </aside>
    <div className="workspace-main">
      <header className="iw-topbar">
        <button className="iw-icon-button lg-menu-button" onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? glass.close : glass.menu} aria-expanded={menuOpen}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
        <div className="iw-breadcrumb" data-tauri-drag-region><span>TOUJING</span><ChevronRight size={13} /><strong>{selected ? glass[selected.label] : c.ask}</strong></div>
        <div className="iw-top-actions"><span className="iw-runtime">{data.runtimeAvailable ? c.native : c.offline}</span><button className="iw-icon-button" onClick={openCommands} aria-label={c.search}><Search size={17} /></button><button className="iw-icon-button" onClick={toggleTheme} aria-label={t("Switch to {theme} mode", { theme: t(theme === "dark" ? "light" : "dark") })}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button><NavLink className="iw-ask" to={askTarget}><MessageCircle size={16} />{c.ask}<ArrowUpRight size={13} /></NavLink></div>
      </header>
      <div className={`iw-mode-strip ${data.mode === "demo" ? "is-demo" : ""}`}><span><i />{data.mode === "demo" ? c.example : c.local}</span><span className="iw-mode-account">{account}</span><span className="iw-mode-help" title={data.mode === "demo" ? c.modeHint : c.realHint}>{data.mode === "demo" ? c.modeHint : c.realHint}</span><button onClick={() => data.setMode(data.mode === "demo" ? "real_user" : "demo")}>{data.mode === "demo" ? c.exitPreview : c.preview}<ArrowUpRight size={12} /></button></div>
      <main className="workspace-content" id="workspace-content">
        {section === "/analysis" && <nav className="lg-context-nav" aria-label={glass.analysis}>{analysisLinks.map((item) => <NavLink key={item.path} to={item.path} end>{glass[item.label]}</NavLink>)}</nav>}
        {section === "/pretrade" && <nav className="lg-context-nav" aria-label={glass.prepare}><NavLink to="/pretrade">{glass.prepare}</NavLink><NavLink to="/journal">{glass.journal}</NavLink></nav>}
        <AnimatePresence mode="wait" initial={false}><motion.div key={`${location.pathname}:${data.mode}:${contextKey}`} className="route-frame" initial={{ opacity: 0, y: 9 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: .19 }}><Outlet /></motion.div></AnimatePresence>
      </main>
    </div>
    <ContextualInspectorHost />
  </div>;
}

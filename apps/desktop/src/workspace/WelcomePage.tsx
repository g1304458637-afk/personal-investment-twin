import { ArrowDown, ArrowUpRight, Languages } from "lucide-react";
import { useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { GlassOrbLogo } from "@/components/common/GlassOrbLogo";
import { positionEpisodeDemo } from "@/data/backendEvidence";
import { showcaseInstrumentName } from "@/data/showcaseDemo";
import { useDataMode } from "@/data/DataModeProvider";
import { adaptDemoInvestmentsCatalog } from "@/data/investments";
import { useLocale } from "@/locales/LocaleProvider";
import { formatCurrencyValue } from "@/lib/format";
import { LiquidBackdrop } from "./LiquidBackdrop";
import { useWelcomeCopy } from "./welcomeCopy";
import { saveWelcomePreference, welcomeStartupPath } from "./welcomePreference";
import "./welcome.css";

export function WelcomeEntry() {
  let path = "/welcome";
  try { path = welcomeStartupPath(window.localStorage); } catch { /* Restricted storage: show welcome. */ }
  return <Navigate to={path} replace />;
}

const catalog = adaptDemoInvestmentsCatalog(positionEpisodeDemo);
const example = [...catalog.openEpisodes, ...catalog.closedEpisodes].find((row) => row.episodeId === positionEpisodeDemo.defaultEpisodeId);
const entry = positionEpisodeDemo.entries.find((item) => item.episode.episodeId === example?.episodeId);

export function WelcomePage() {
  const c = useWelcomeCopy(); const { t, locale, setLocale, formatPercent } = useLocale();
  const data = useDataMode(); const navigate = useNavigate(); const features = useRef<HTMLElement>(null);
  const [skip, setSkip] = useState(() => { try { return welcomeStartupPath(window.localStorage) === "/investments"; } catch { return false; } });
  const [preferenceError, setPreferenceError] = useState(false);
  const account = entry && data.examples.find((item) => item.subjectId === entry.episode.subjectId && item.accountId === entry.episode.accountId);
  const openExample = () => {
    if (!account || !example) return;
    data.setExampleAccount(account); data.setMode("demo");
    navigate(`/investments/episodes/${example.episodeId}`);
  };
  const date = (value: string) => new Intl.DateTimeFormat(locale, {year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(value));
  return <div className="welcome-screen">
    <LiquidBackdrop />
    <header className="welcome-nav">
      <Link to="/welcome" className="welcome-brand" aria-label={c.brand}><GlassOrbLogo prominent /><strong>投镜</strong><span>TOUJING</span></Link>
      <nav aria-label={c.about}><button onClick={() => features.current?.scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"})}>{c.about}<ArrowDown size={13} /></button></nav>
      <div className="welcome-nav-actions"><button aria-label={locale === "zh-CN" ? "Switch to English" : "切换为简体中文"} onClick={() => setLocale(locale === "zh-CN" ? "en-US" : "zh-CN")}><Languages size={17} /><span>{locale === "zh-CN" ? "EN" : "中文"}</span></button><Link to="/investments">{c.enter}<ArrowUpRight size={15} /></Link></div>
    </header>
    <main>
      <section className="welcome-hero">
        <div className="welcome-copy"><p className="welcome-eyebrow">{c.eyebrow}</p><h1>{c.title}<br /><span>{c.titleEnd}</span></h1><p className="welcome-description">{c.detail}</p>
          <div className="welcome-actions"><Link className="welcome-primary" to="/investments">{c.enter}<ArrowUpRight size={18} /></Link><button className="welcome-secondary" disabled={!account || !example} onClick={openExample}>{c.example}<ArrowUpRight size={17} /></button></div>
          <label className="welcome-skip"><input type="checkbox" checked={skip} onChange={(event) => { const next = event.target.checked; setSkip(next); try { setPreferenceError(!saveWelcomePreference(window.localStorage, next)); } catch { setPreferenceError(true); } }} />{c.skip}</label>
          {preferenceError && <p className="welcome-preference-error" role="status">{c.preferenceError}</p>}
        </div>
        {example && account && <div className="welcome-example"><div className="welcome-card-caption"><span>{c.cardIntro}</span><span>01 / 01</span></div>
          <button className="welcome-card" onClick={openExample} onPointerMove={(event) => { const rect = event.currentTarget.getBoundingClientRect(); event.currentTarget.style.setProperty("--pointer-x", `${event.clientX-rect.left}px`); event.currentTarget.style.setProperty("--pointer-y", `${event.clientY-rect.top}px`); }}>
            <span className="welcome-card-light" aria-hidden="true" /><div className="welcome-card-top"><span>{c.sample}</span><span>{t(example.status === "closed" ? "Closed" : "Holding")}</span></div>
            <h2>{showcaseInstrumentName(example.instrumentId, locale, example.displayName)}</h2><p className="welcome-period">{date(example.openedAt)} <span>—</span> {example.closedAt ? date(example.closedAt) : t("Present")}</p>
            <div className="welcome-result"><div><span>{t(example.outcome.result_kind === "marked" ? "Current marked result" : "Final realized result")}</span><strong>{example.outcome.pnl === null ? "—" : formatCurrencyValue(example.outcome.pnl, locale, example.currency)}</strong></div><div><span>{t("Position Return")}</span><strong>{example.outcome.return_value === null ? "—" : formatPercent(example.outcome.return_value, 2)}</strong></div></div>
            <p className="welcome-card-note">{c.cardNote}</p><div className="welcome-card-action"><span>{c.cardAction}</span><ArrowUpRight size={19} /></div>
          </button>
        </div>}
      </section>
      <section ref={features} className="welcome-features" aria-label={c.about}>{c.features.map((item, index) => <article key={item.title}><span>0{index+1}</span><h2>{item.title}</h2><p>{item.detail}</p></article>)}</section>
    </main>
    <footer className="welcome-footer"><span>TOUJING / PERSONAL INVESTMENT INTELLIGENCE</span><p>{c.footer}</p></footer>
  </div>;
}

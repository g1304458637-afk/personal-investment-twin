import { useState } from "react";
import { ArrowRight, Check, FileText, FolderInput, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useDataMode } from "@/data/DataModeProvider";
import { DataAccountsPage } from "@/pages/DataAccountsPage";
import { useWorkspaceCopy } from "./copy";

/** Browser workflow has no file input, read API or persistence. Native uses the existing contract. */
export function DataWorkspace() {
  const data = useDataMode(); const c = useWorkspaceCopy();
  const [tab, setTab] = useState<"import" | "prices" | "sharing">("import");
  const [step, setStep] = useState(0);
  const [entered, setEntered] = useState(false);
  const [name, setName] = useState("");
  const [zone, setZone] = useState("Asia/Shanghai");
  const preview = entered || data.mode === "demo";
  return <div className="iw-page iw-data"><header className="iw-page-heading"><span className="iw-kicker">DATA / SOURCE OF TRUTH</span><h1>{c.dataTitle}</h1><p>{c.dataDetail}</p></header>
    <div className="iw-tabs" role="group" aria-label={c.data}>{(["import", "prices", "sharing"] as const).map((item) => <button key={item} aria-pressed={tab === item} onClick={() => setTab(item)}>{c[item]}</button>)}</div>
    {tab !== "sharing" && data.runtimeAvailable && data.mode === "real_user" ? <DataAccountsPage key={tab} initialKind={tab === "prices" ? "market" : "trade"} /> : tab !== "sharing" ? <>
      <div className="iw-context-banner"><FolderInput size={18} /><div><strong>{c.browserImport}</strong><p>{tab === "prices" ? c.coverageDetail : c.importDetail}</p></div><span className="iw-badge">{c.previewOnly}</span></div>
      {!preview ? <section className="iw-surface iw-disconnected"><FileText size={32} /><h2>{c.desktopRequired}</h2><p>{c.importDetail}</p><button className="iw-primary" onClick={() => setEntered(true)}>{c.preview}<ArrowRight size={16} /></button></section> : <div className="iw-data-grid"><section className="iw-surface">
        <ol className="iw-stepper" aria-label={c.import}>{[c.source, c.inspect, c.confirm].map((label, index) => <li key={label}><button aria-current={step === index ? "step" : undefined} onClick={() => setStep(index)}><span>{index < step ? <Check size={14} /> : index + 1}</span>{label}</button></li>)}</ol>
        <div className="iw-step-content" key={step}>
          {step === 0 ? <><span className="iw-kicker">01 / SOURCE</span><h2>{c.file}</h2><div className="iw-drop-preview"><FileText size={30} /><strong>{c.desktopRequired}</strong><span>{c.noWrites}</span></div><div className="iw-form-grid"><label>{c.accountName}<input value={name} onChange={(e) => setName(e.target.value)} placeholder={c.accountName} /></label><label>{c.zone}<select value={zone} onChange={(e) => setZone(e.target.value)}><option>Asia/Shanghai</option><option>UTC</option><option>America/New_York</option></select></label></div></> : step === 1 ? <><span className="iw-kicker">02 / CONTRACT</span><h2>{c.mapping}</h2><table className="iw-table"><thead><tr><th>{c.field}</th><th>{c.meaning}</th></tr></thead><tbody>{(tab === "prices" ? [["date / symbol", c.instrument], ["close / price_type", c.prices], ["data_source / data_version", c.context]] : [["event_time / source_sequence", c.event], ["symbol / market / security_type", c.instrument], ["side / quantity / execution_price", c.quantity], ["fee / fee_status", c.fees]]).map(([field, detail]) => <tr key={field}><td><code>{field}</code></td><td>{detail}</td></tr>)}</tbody></table></> : <><span className="iw-kicker">03 / VERIFY</span><h2>{c.quality}</h2><p>{c.qualityDetail}</p><div className="iw-quality-list">{[c.instrument, c.fees, c.prices].map((label) => <div key={label}><span>{label}</span><span className="iw-badge">—</span></div>)}</div><button className="iw-primary" disabled>{c.desktopRequired}</button><p>{c.noWrites}</p></>}
        </div><div className="iw-step-footer"><span>{c.previewOnly} · {step + 1} / 3</span>{step < 2 && <button className="iw-primary" onClick={() => setStep(step + 1)}>{[c.inspect, c.confirm][step]}<ArrowRight size={15} /></button>}</div>
      </section><aside className="iw-surface iw-data-rail"><ShieldCheck size={24} /><h2>{c.privacy}</h2><p>{c.importDetail}</p><hr /><h3>{c.prices}</h3><p>{c.coverageDetail}</p><Link className="iw-text-link" to="/investments">{c.investments}<ArrowRight size={14} /></Link></aside></div>}
    </> : <section className="iw-surface iw-share-intro"><ShieldCheck size={30} /><span className="iw-kicker">EPISODE-BOUND / EXPLICIT CONSENT</span><h2>{c.sharing}</h2><p>{c.shareDetail}</p><div className="iw-quality-list">{["Episode", "Recipient", "Expiry", "Model permission", "Signer fingerprint"].map((label) => <div key={label}><code>{label}</code><ShieldCheck size={16} /></div>)}</div><p>{c.noPermission}</p><Link className="iw-primary" to="/ask">{c.openShare}<ArrowRight size={16} /></Link></section>}
  </div>;
}

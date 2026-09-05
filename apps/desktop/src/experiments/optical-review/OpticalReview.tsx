import { useId } from "react";
import { ArrowUpRight, Focus, FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";
import { useLocale } from "@/locales/LocaleProvider";
import "./optical-review.css";

/** Small optical illustration, never a filter over a chart, value or evidence.
 * Only the decorative reticle is refracted; no pointer listeners or render loop.
 * SVG SourceGraphic filtering does not require SVG backdrop-filter support.
 */
export function DecisionLens({ active = false }: { active?: boolean }) {
  const id = useId().replace(/:/g, "");
  return <span className="optical-lens" data-active={active} aria-hidden="true">
    <svg className="optical-lens__reticle" viewBox="0 0 120 120" focusable="false">
      <defs>
        <filter id={`${id}-refraction`} x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency=".015" numOctaves="1" seed="7" result="map" />
          <feDisplacementMap in="SourceGraphic" in2="map" scale="7" xChannelSelector="R" yChannelSelector="G" />
        </filter>
        <clipPath id={`${id}-aperture`}><circle cx="60" cy="60" r="40" /></clipPath>
      </defs>
      <g className="optical-lens__calibration" fill="none" stroke="currentColor" strokeWidth=".6">
        <path d="M60 4v9 M60 107v9 M4 60h9 M107 60h9 M20 20l5 5 M95 95l5 5 M20 100l5-5 M95 25l5-5" />
        <circle cx="60" cy="60" r="51" strokeDasharray=".6 9.4" />
      </g>
      <g clipPath={`url(#${id}-aperture)`}>
        <g className="optical-lens__etched" filter={`url(#${id}-refraction)`} fill="none" stroke="currentColor" strokeWidth=".65">
          <path d="M0 39h120 M0 60h120 M0 81h120 M39 0v120 M60 0v120 M81 0v120" />
        </g>
      </g>
      <path className="optical-lens__target" d="M48 54v-6h6 M66 48h6v6 M72 66v6h-6 M54 72h-6v-6" fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
    <span className="optical-lens__glass" />
    <span className="optical-lens__rim" />
    <span className="optical-lens__caustic" />
  </span>;
}

export function OpticalReviewSwitch({ enabled, onChange }: { enabled: boolean; onChange: (enabled: boolean) => void }) {
  const { t } = useLocale();
  return <button type="button" data-optical-toggle className="optical-switch" aria-pressed={enabled} onClick={() => onChange(!enabled)}>
    <FlaskConical size={12} aria-hidden="true" />
    {t(enabled ? "Optical experiment · Return to original" : "Try Optical visual experiment")}
  </button>;
}

export function OpticalFocusHint() {
  const { t } = useLocale();
  return <div className="optical-focus-hint">
    <DecisionLens />
    <div><span className="optical-eyebrow">DECISION LENS</span>
      <p>{t("Select an execution. Bring its evidence into focus.")}</p>
      <span>{t("The chart stays precise. The context comes closer.")}</span>
    </div>
  </div>;
}

export function OpticalDecisionFocus({ timestamp }: { timestamp: string }) {
  const { t } = useLocale();
  return <div className="optical-decision-focus">
    <DecisionLens active />
    <div><p className="optical-eyebrow">{t("In focus · Recorded execution")}</p><p>{timestamp}</p></div>
  </div>;
}

/** Presentation boundary for the existing generated Episode examples.
 * Never attaches the unrelated A/B pair to this Episode or invokes a model.
 */
export function OpticalExampleBoundary() {
  const { t } = useLocale();
  return <section className="optical-example-boundary" data-optical-runtime-boundary>
    <div className="optical-section-label"><Focus size={14} aria-hidden="true" /><h2>{t("Beyond the recorded facts")}</h2></div>
    <div className="optical-mode-surface" aria-label={t("Review capabilities")}>
      {["Analyze this investment", "Compare same stock", "Against my own past"].map((label) => <button type="button" key={label} disabled>{t(label)}</button>)}
    </div>
    <div className="optical-boundary-columns">
      <div><h3>{t("What is not established here")}</h3><p>{t("This example contains recorded operations and outcomes, not the investor's contemporaneous intention or an authorized comparison for this Episode.")}</p></div>
      <div><h3>{t("Ask Toujing · Not connected in this example")}</h3><p>{t("No model has been called. Live review remains in the desktop account workflow with explicit permission.")}</p></div>
    </div>
    <Link to="/investments/compare-example" className="optical-example-link">{t("Open separate A/B Synthetic example · not this investment")}<ArrowUpRight size={13} aria-hidden="true" /></Link>
  </section>;
}

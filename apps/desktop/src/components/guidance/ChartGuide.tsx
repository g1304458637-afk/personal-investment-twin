import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { chartGuideFor, type ChartGuideId } from "@/data/chartGuide";
import { useLocale } from "@/locales/LocaleProvider";

import "./chart-guide.css";

const guideAnchorSelector = (anchor: string) => `[data-guide="${anchor}"]`;

function visibleGuideTarget(scope: HTMLElement | null, anchor: string) {
  const target = scope?.querySelector<HTMLElement>(guideAnchorSelector(anchor)) ?? null;
  return target && !target.closest("[hidden], [aria-hidden='true']") && target.getClientRects().length > 0 ? target : null;
}

export function ChartGuide({ guideId, onExit }: { guideId: ChartGuideId; onExit: () => void }) {
  const guide = chartGuideFor(guideId);
  const { locale } = useLocale();
  const zh = locale.startsWith("zh");
  const [stepIndex, setStepIndex] = useState(0);
  const [blocked, setBlocked] = useState(false);
  const previousFocus = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const restoreOnExit = useRef(false);
  const copy = (value: { zh: string; en: string }) => zh ? value.zh : value.en;

  useEffect(() => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = requestAnimationFrame(() => panelRef.current?.querySelector<HTMLElement>("[data-guide-primary]")?.focus());
    return () => {
      cancelAnimationFrame(frame);
      const node = previousFocus.current;
      if (restoreOnExit.current && node?.isConnected) node.focus();
    };
  }, []);

  const step = guide?.steps[stepIndex] ?? null;
  useEffect(() => {
    if (!step) return;
    const scope = panelRef.current?.closest<HTMLElement>("[data-guide-scope]") ?? null;
    const target = visibleGuideTarget(scope, step.anchor);
    if (!target) { setBlocked(true); return; }
    setBlocked(false);
    target.dataset.chartGuideHighlight = "true";
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const frame = requestAnimationFrame(() => target.scrollIntoView({ block: "nearest", behavior: reduced ? "instant" : "smooth" }));
    return () => {
      cancelAnimationFrame(frame);
      delete target.dataset.chartGuideHighlight;
    };
  }, [step]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); restoreOnExit.current = true; onExit(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onExit]);

  if (!guide || !step) return null;
  const lastStep = stepIndex === guide.steps.length - 1;
  const exit = () => { restoreOnExit.current = true; onExit(); };
  const move = (nextIndex: number) => {
    const scope = panelRef.current?.closest<HTMLElement>("[data-guide-scope]") ?? null;
    const next = guide.steps[nextIndex];
    if (!next || !visibleGuideTarget(scope, next.anchor)) { setBlocked(true); return; }
    setBlocked(false); setStepIndex(nextIndex);
  };
  const onPanelKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "ArrowRight" && !lastStep) { event.preventDefault(); move(stepIndex + 1); }
    if (event.key === "ArrowLeft" && stepIndex > 0) { event.preventDefault(); move(stepIndex - 1); }
  };
  const unavailable = zh ? "此区域目前未显示。请先完成页面所需操作，或退出导览。" : "This area is not currently visible. Complete the needed page action first, or exit the guide.";
  return <aside ref={panelRef} className="chart-guide" aria-label={copy(guide.title)} aria-live="polite" onKeyDown={onPanelKeyDown}>
    <div className="chart-guide__head"><div><p>{zh ? "图表导览" : "Chart guide"} · {stepIndex + 1}/{guide.steps.length}</p><h2>{copy(guide.title)}</h2></div><button type="button" onClick={exit} aria-label={zh ? "退出图表导览" : "Exit chart guide"} title={zh ? "退出图表导览" : "Exit chart guide"}><X size={16} /></button></div>
    <h3>{copy(step.title)}</h3><p>{blocked ? unavailable : copy(step.detail)}</p>
    <div className="chart-guide__actions"><button type="button" onClick={() => move(stepIndex - 1)} disabled={stepIndex === 0}><ChevronLeft size={15} />{zh ? "上一步" : "Previous"}</button><button data-guide-primary type="button" onClick={() => lastStep ? exit() : move(stepIndex + 1)}>{lastStep ? (zh ? "完成" : "Done") : <>{zh ? "下一步" : "Next"}<ChevronRight size={15} /></>}</button><button type="button" className="chart-guide__skip" onClick={exit}>{zh ? "跳过" : "Skip"}</button></div>
  </aside>;
}

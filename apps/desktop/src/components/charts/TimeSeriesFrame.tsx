import { useEffect, useId, useRef, useState, useSyncExternalStore, type ReactNode, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, Minus, Plus, RotateCcw } from "lucide-react";

import { useLocale } from "@/locales/LocaleProvider";
import { anchoredZoomVisibleDomain, panVisibleDailyDomainByPixels } from "./dailyTimeNavigation";
import type { DailyTimeNavigationStore } from "./useDailyTimeNavigation";
import "./time-series-frame.css";

/** Presentation-only workspace. Every pane receives the same navigation store. */
export function TimeSeriesFrame({ title, navigation, children, subtitle, toolbar, className = "", onReset }: {
  title: string;
  navigation: DailyTimeNavigationStore;
  children: ReactNode;
  subtitle?: string;
  toolbar?: ReactNode;
  className?: string;
  onReset?: () => void;
}) {
  const { locale } = useLocale();
  const zh = locale.startsWith("zh");
  const domain = useSyncExternalStore(navigation.subscribe, navigation.getDomain, navigation.getDomain);
  const [fullscreen, setFullscreen] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const expandRef = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  const titleId = useId();
  const range = navigation.fullDomain;
  const span = range.end - range.start;
  const startPercent = span > 0 ? (domain.start - range.start) / span * 100 : 0;
  const endPercent = span > 0 ? (domain.end - range.start) / span * 100 : 100;
  const date = (value: number) => new Intl.DateTimeFormat(locale, { year: "numeric", month: "short", day: "numeric" }).format(value);
  const zoom = (scale: number) => navigation.apply(anchoredZoomVisibleDomain(domain,
    (domain.start + domain.end) / 2, scale, navigation.observationTimes, range), "slider");
  const pan = (direction: number) => navigation.apply(panVisibleDailyDomainByPixels(domain,
    direction * 180, 800, navigation.observationTimes, range), "drag");
  const reset = () => { navigation.reset(); onReset?.(); };
  const rangeKey = (event: ReactKeyboardEvent<HTMLInputElement>, side: "start" | "end") => {
    const direction = event.key === "ArrowRight" || event.key === "ArrowUp" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowDown" ? -1 : 0;
    if (!direction) return;
    event.preventDefault();
    const dates = [...new Set([range.start, ...navigation.observationTimes, range.end])].sort((a, b) => a - b);
    const current = domain[side];
    const next = direction > 0 ? dates.find((time) => time > current + 1) : [...dates].reverse().find((time) => time < current - 1);
    if (next === undefined) return;
    navigation.apply(side === "start" ? { start: Math.min(next, domain.end), end: domain.end } : { start: domain.start, end: Math.max(next, domain.start) }, "slider");
  };

  useEffect(() => {
    if (!fullscreen) {
      if (restoreFocus.current) { expandRef.current?.focus(); restoreFocus.current = false; }
      return;
    }
    restoreFocus.current = true;
    expandRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setFullscreen(false); }
      if (event.key !== "Tab") return;
      const controls = [...(rootRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], [tabindex="0"]',
      ) ?? [])].filter((node) => node.getClientRects().length > 0);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  const workspace = <section ref={rootRef} className={`time-series-frame ${fullscreen ? "time-series-frame--fullscreen" : ""} ${className}`}
    role={fullscreen ? "dialog" : undefined} aria-modal={fullscreen || undefined} aria-labelledby={titleId}>
    <header className="time-series-frame-header">
      <div><h3 id={titleId}>{title}</h3>{subtitle && <p>{subtitle}</p>}</div>
      <div className="time-series-frame-tools">
        {toolbar}
        <div className="time-series-frame-actions" role="group" aria-label={zh ? "图表时间导航" : "Chart time navigation"}>
          <button type="button" onClick={() => pan(-1)} title={zh ? "向前查看" : "Earlier"} aria-label={zh ? "向前查看" : "Earlier"}><ChevronLeft size={16} /></button>
          <button type="button" onClick={() => pan(1)} title={zh ? "向后查看" : "Later"} aria-label={zh ? "向后查看" : "Later"}><ChevronRight size={16} /></button>
          <button type="button" onClick={() => zoom(0.8)} title={zh ? "缩小" : "Zoom out"} aria-label={zh ? "缩小" : "Zoom out"}><Minus size={16} /></button>
          <button type="button" onClick={() => zoom(1.25)} title={zh ? "放大" : "Zoom in"} aria-label={zh ? "放大" : "Zoom in"}><Plus size={16} /></button>
          <button type="button" onClick={reset} title={zh ? "完整区间" : "Full range"}><RotateCcw size={14} /><span>{zh ? "全部" : "All"}</span></button>
          <button ref={expandRef} type="button" onClick={() => setFullscreen((value) => !value)} aria-label={fullscreen ? (zh ? "退出全屏" : "Exit fullscreen") : (zh ? "全屏查看图表" : "Expand chart")}
            title={fullscreen ? (zh ? "退出全屏" : "Exit fullscreen") : (zh ? "全屏查看图表" : "Expand chart")}>
            {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>
    </header>
    <div className="time-series-frame-panes">{children}</div>
    <footer className="time-series-frame-footer">
      <div className="time-series-frame-dates"><span>{date(domain.start)} — {date(domain.end)}</span><span>{zh ? "显示区间" : "Visible range"}</span></div>
      <div className="time-series-frame-range">
        <div className="time-series-frame-track" />
        <div className="time-series-frame-selection" style={{ left: `${startPercent}%`, width: `${endPercent - startPercent}%` }} aria-hidden="true" />
        <input type="range" min={range.start} max={range.end} step="any" value={domain.start} disabled={span <= 0}
          aria-label={zh ? "区间开始日期" : "Range start date"} aria-valuetext={date(domain.start)}
          onKeyDown={(event) => rangeKey(event, "start")}
          onChange={(event) => navigation.apply({ start: Math.min(Number(event.target.value), domain.end), end: domain.end }, "slider")} />
        <input type="range" min={range.start} max={range.end} step="any" value={domain.end} disabled={span <= 0}
          aria-label={zh ? "区间结束日期" : "Range end date"} aria-valuetext={date(domain.end)}
          onKeyDown={(event) => rangeKey(event, "end")}
          onChange={(event) => navigation.apply({ start: domain.start, end: Math.max(domain.start, Number(event.target.value)) }, "slider")} />
      </div>
      <div className="time-series-frame-hint"><span>{date(range.start)}</span><span>{zh ? "横向双指滑动 / 拖动平移 · 捏合或 Ctrl / ⌘ + 滚动缩放 · 纵向滚动页面" : "Horizontal swipe / drag to pan · Pinch or Ctrl / ⌘ + scroll to zoom · Vertical scroll moves the page"}</span><span>{date(range.end)}</span></div>
    </footer>
  </section>;
  return fullscreen ? createPortal(workspace, document.body) : workspace;
}

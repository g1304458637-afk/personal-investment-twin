import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import liquidPoster from "@/assets/liquid-backdrop-poster.jpg";
import { useLiquidCopy } from "./liquidCopy";

export const LIQUID_VIDEO = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260511_230229_7c9bc431-46cf-489a-948d-e8144d8eb5d4.mp4";

/** Decorative media only: no account data, no route remount and no model/network API. */
export function LiquidBackdrop() {
  const c = useLiquidCopy();
  const video = useRef<HTMLVideoElement>(null);
  const [paused, setPaused] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reduce = () => { if (preference.matches) { setPaused(true); setReady(false); } };
    preference.addEventListener("change", reduce);
    return () => preference.removeEventListener("change", reduce);
  }, []);
  useEffect(() => {
    const media = video.current;
    if (!media) return;
    let disposed = false;
    let attempt = 0;
    const sync = () => {
      const currentAttempt = ++attempt;
      if (paused || document.hidden) media.pause();
      else void media.play().catch(() => {
        // A superseded play() can reject after StrictMode cleanup or visibility changes.
        if (!disposed && currentAttempt === attempt) setPaused(true);
      });
    };
    sync(); document.addEventListener("visibilitychange", sync);
    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", sync);
      media.pause();
    };
  }, [paused, failed]);
  return <>
    <div className="lg-backdrop" aria-hidden="true">
      {/* Local first frame stays underneath, including offline and reduced-motion mode. */}
      <img className="lg-backdrop-poster" src={liquidPoster} alt="" fetchPriority="high" decoding="sync" />
      {!failed && <video ref={video} src={LIQUID_VIDEO} poster={liquidPoster} className={ready ? "is-ready" : undefined}
        muted loop playsInline preload={paused ? "none" : "auto"} disablePictureInPicture
        onPlaying={() => setReady(true)} onEmptied={() => setReady(false)} onError={() => setFailed(true)} />}
      <div className="lg-backdrop-shade" />
    </div>
    {!failed && <button className="lg-motion-toggle" onClick={() => setPaused(!paused)} aria-label={paused ? c.play : c.pause} title={paused ? c.play : c.pause} aria-pressed={!paused}>{paused ? <Play size={13} /> : <Pause size={13} />}</button>}
  </>;
}

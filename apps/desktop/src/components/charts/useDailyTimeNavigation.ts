import { useRef } from "react";

import {
  applyVisibleDailyDomain,
  domainsEqual,
  fullVisibleDomain,
  type EpisodeVisibleTimeDomain,
} from "./dailyTimeNavigation.ts";

export type TimeNavigationSource = "wheel" | "slider" | "drag" | "reset";

export type DailyTimeNavigationStore = {
  episodeId: string;
  observationTimes: number[];
  fullDomain: EpisodeVisibleTimeDomain;
  getDomain: () => EpisodeVisibleTimeDomain;
  subscribe: (listener: (domain: EpisodeVisibleTimeDomain, source: TimeNavigationSource) => void) => () => void;
  apply: (candidate: EpisodeVisibleTimeDomain, source: TimeNavigationSource) => boolean;
  schedule: (candidate: EpisodeVisibleTimeDomain) => boolean;
  cancelPending: () => void;
  reset: () => boolean;
};

export function createDailyTimeNavigationStore(
  episodeId: string,
  observationTimes: number[],
  boundaryTimes: number[] = [],
  frames = { request: (fn: FrameRequestCallback) => requestAnimationFrame(fn), cancel: (id: number) => cancelAnimationFrame(id) },
): DailyTimeNavigationStore {
  const times = [...observationTimes];
  const fullDomain = fullVisibleDomain([...times, ...boundaryTimes].filter(Number.isFinite));
  let domain = fullDomain;
  let frame: number | null = null;
  const cancelPending = () => { if (frame !== null) frames.cancel(frame); frame = null; };
  const listeners = new Set<(domain: EpisodeVisibleTimeDomain, source: TimeNavigationSource) => void>();

  const apply = (candidate: EpisodeVisibleTimeDomain, source: TimeNavigationSource): boolean => {
    const next = applyVisibleDailyDomain(candidate, times, fullDomain);
    if (domainsEqual(domain, next)) return false;
    domain = next;
    cancelPending();
    listeners.forEach((listener) => listener(domain, source));
    return true;
  };

  return {
    episodeId,
    observationTimes: times,
    fullDomain,
    getDomain: () => domain,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) cancelPending();
      };
    },
    apply,
    schedule: (candidate) => {
      const next = applyVisibleDailyDomain(candidate, times, fullDomain);
      if (domainsEqual(domain, next)) return false;
      domain = next;
      if (frame === null) frame = frames.request(() => {
        frame = null;
        listeners.forEach((listener) => listener(domain, "wheel"));
      });
      return true;
    },
    cancelPending,
    reset: () => apply(fullDomain, "reset"),
  };
}

function observationKey(episodeId: string, observationTimes: number[]): string {
  if (observationTimes.length === 0) return `${episodeId}:empty`;
  return `${episodeId}:${observationTimes.join(",")}`;
}

export function useDailyTimeNavigation(
  episodeId: string,
  observationTimes: number[],
  boundaryTimes: number[] = [],
): DailyTimeNavigationStore {
  const key = observationKey(episodeId, [...observationTimes, ...boundaryTimes]);
  const storeRef = useRef<DailyTimeNavigationStore | null>(null);
  const keyRef = useRef(key);
  if (!storeRef.current || keyRef.current !== key) {
    storeRef.current?.cancelPending();
    keyRef.current = key;
    storeRef.current = createDailyTimeNavigationStore(episodeId, observationTimes, boundaryTimes);
  }
  return storeRef.current;
}

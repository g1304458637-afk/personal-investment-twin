export interface PeerRangeDomainInput {
  p25: number;
  median: number;
  p75: number;
  user: number;
}

export interface PeerRangeDomain {
  min: number;
  max: number;
}

/**
 * Keep the full cohort range and the user's observed value inside the plotted
 * domain, with a small amount of breathing room on both sides.
 */
export function getPeerRangeDomain(metric: PeerRangeDomainInput): PeerRangeDomain {
  const observed = [metric.p25, metric.median, metric.p75, metric.user];
  const observedMin = Math.min(...observed);
  const observedMax = Math.max(...observed);
  const span = observedMax - observedMin || Math.abs(observedMax) || 1;
  const padding = span * 0.18;

  return {
    min: observedMin - padding,
    max: observedMax + padding,
  };
}

/** Deterministic boundary inputs for checking marker visibility outside P25/P75. */
export const peerRangeBoundaryFixtures = {
  belowP25: { p25: 0.22, median: 0.29, p75: 0.38, user: 0.12 },
  aboveP75: { p25: 0.22, median: 0.29, p75: 0.38, user: 0.52 },
} satisfies Record<"belowP25" | "aboveP75", PeerRangeDomainInput>;

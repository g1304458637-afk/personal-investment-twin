// The original 8.2s record → orb → timeline scene leads into the career replay.
// One clock owns both renderers and every control.
export const AWAKENING = {
  ignition: 2.65,
  unfold: 5.15,
  replayStart: 8.2,
  replayEnd: 22.2,
  chargeStart: 25.2,
  revealStart: 26.7,
  reviewReady: 30.7,
  end: 32.2,
} as const;

export const careerTime = (seconds: number) => Math.max(0, seconds - (AWAKENING.replayStart - 2));

export function awakeningPhase(seconds: number) {
  if (seconds < AWAKENING.ignition) return 'collect';
  if (seconds < AWAKENING.unfold) return 'ignite';
  if (seconds < AWAKENING.replayStart) return 'unfold';
  if (seconds < AWAKENING.replayEnd) return 'life';
  if (seconds < AWAKENING.chargeStart) return 'gather';
  if (seconds < AWAKENING.revealStart) return 'charge';
  if (seconds < AWAKENING.reviewReady) return 'reveal';
  return 'ready';
}

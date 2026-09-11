type CursorListener = (time: number | null, source: object) => void;
const channels = new WeakMap<object, Set<CursorListener>>();

/** Coordinate synchronization only; never samples, interpolates, or fills data. */
export function subscribeChartCursor(scope: object, listener: CursorListener) {
  let listeners = channels.get(scope);
  if (!listeners) { listeners = new Set(); channels.set(scope, listeners); }
  listeners.add(listener);
  return () => { listeners.delete(listener); if (!listeners.size) channels.delete(scope); };
}

export function publishChartCursor(scope: object, time: number | null, source: object) {
  if (time !== null && !Number.isFinite(time)) return;
  channels.get(scope)?.forEach((listener) => listener(time, source));
}

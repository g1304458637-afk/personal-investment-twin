/**
 * Draft-state parsing for numeric workshop inputs.  Typing stays a string
 * draft; only on blur/commit is it parsed and clamped to the range the
 * backend spec validation enforces.  This keeps "0", "-" and a cleared
 * field from jumping the value to a fallback mid-typing, and stops
 * out-of-range values (e.g. fraction 5000) from ever reaching a spec.
 */
export function parseClampedNumberInput(text: string, fallback: number, min = -Infinity, max = Infinity): number {
  const trimmed = text.trim();
  if (trimmed.length === 0) return fallback;
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

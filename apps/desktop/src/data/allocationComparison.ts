import type { AllocationView } from "./pretradeImpact.ts";

export type AllocationBasis = "account" | "securities";
const colours = ["#9ccfea", "#b9a6ed", "#efbc8d", "#7ac9b6", "#d998b7", "#bdca8d"];
// Stable identity colour, never rank/weight-dependent and never a random financial value.
export function allocationColour(id: string): string {
  if (id === "cash") return "#566d83";
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return colours[hash % colours.length];
}

export function allocationRows(before: AllocationView[], after: AllocationView[], basis: AllocationBasis) {
  const ids = [...new Set([...before, ...after].map((row) => row.id))].sort();
  const used = new Set<string>();
  return ids.map((id) => {
    const current = before.find((row) => row.id === id) ?? null;
    const proposed = after.find((row) => row.id === id) ?? null;
    const preferred = allocationColour(id);
    const colour = used.has(preferred) ? colours.find((candidate) => !used.has(candidate)) ?? preferred : preferred;
    used.add(colour);
    return { id, identity: (current ?? proposed)!, before: current, after: proposed, colour };
  }).filter((row) => basis === "account" || row.identity.kind !== "cash");
}

export function allocationShare(row: AllocationView | null, basis: AllocationBasis): number {
  return row === null ? 0 : basis === "account" ? row.accountWeight : row.securityWeight ?? 0;
}

/** A result belongs to the exact selection and source revision that launched it. */
export function stableSpec(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableSpec).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableSpec((value as Record<string, unknown>)[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function strategyRunKey(input: {
  strategyId: string; spec: Record<string, unknown>; mode: "demo" | "real_user";
  subjectId: string | null; accountId: string | null; sourceFingerprint: string;
  universe: "synthetic" | "own_account";
}): string {
  return JSON.stringify([input.strategyId, stableSpec(input.spec), input.mode,
    input.subjectId, input.accountId, input.sourceFingerprint, input.universe]);
}

export class LatestRunGate {
  private context = "";
  private generation = 0;

  setContext(key: string) {
    if (key !== this.context) { this.context = key; this.generation += 1; }
  }

  begin(key: string): number {
    this.setContext(key);
    return ++this.generation;
  }

  accepts(key: string, generation: number): boolean {
    return key === this.context && generation === this.generation;
  }

  invalidate() { this.generation += 1; }
}

/** Never revive a cached result or account confirmation after A → B → A. */
export class ScopeRevision {
  private scope = "";
  private revision = 0;

  update(scope: string): number {
    if (scope !== this.scope) { this.scope = scope; this.revision += 1; }
    return this.revision;
  }
}

export interface AccountIdentity { subject_id: string; account_id: string }
export function accountIdentity(account: AccountIdentity): string {
  return JSON.stringify([account.subject_id, account.account_id]);
}

export function confirmedActiveAccount<T extends AccountIdentity>(
  confirmation: { key: string; scopeRevision: number } | null,
  activeAccount: T | null,
  scopeRevision: number,
): T | null {
  return confirmation && activeAccount && confirmation.scopeRevision === scopeRevision
    && confirmation.key === accountIdentity(activeAccount) ? activeAccount : null;
}

export function sensitivityAvailability(
  strategy: "built_in" | "user",
  schemaVersion: unknown,
  universe: "synthetic" | "own_account",
): "available" | "formula_unsupported" | "real_history_unsupported" {
  if (strategy === "user" && universe === "own_account") return "real_history_unsupported";
  if (strategy === "user" && schemaVersion === "user_strategy_formula.v1") return "formula_unsupported";
  return "available";
}

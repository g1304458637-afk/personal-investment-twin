/**
 * Shared, shape-checked access to locally saved user strategies
 * (localStorage key "toujing.userStrategies") and to their spec shapes.
 *
 * Everything on this page is presentation-only: saved strategies are data
 * specs, and all finance numbers still come from the fail-closed backend
 * adapters.  A corrupted or hostile localStorage payload must never crash
 * a page, so reads validate entry shapes and drop anything malformed.
 */
import { conditionStatement } from "./strategyFactors.ts";

export const USER_STRATEGIES_KEY = "toujing.userStrategies";

export interface SavedUserStrategy {
  id: string;
  name: string;
  savedAt: string;
  spec: Record<string, unknown>;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const nonEmptyText = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

/**
 * Reads the saved user strategies, discarding entries that do not have the
 * basic shape (non-empty string id/name/savedAt plus a spec object carrying
 * a schema_version).  Never throws: storage or JSON errors read as empty.
 */
export function readUserStrategies(storage?: Pick<Storage, "getItem">): SavedUserStrategy[] {
  let raw: unknown = null;
  try { raw = storage?.getItem(USER_STRATEGIES_KEY) ?? null; } catch { return []; }
  if (typeof raw !== "string" || raw.length === 0) return [];
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return []; }
  if (!Array.isArray(parsed)) return [];
  return parsed.filter((item): item is SavedUserStrategy =>
    isPlainObject(item)
    && nonEmptyText(item.id)
    && nonEmptyText(item.name)
    && typeof item.savedAt === "string" && item.savedAt.length > 0
    && isPlainObject(item.spec)
    && nonEmptyText(item.spec.schema_version));
}

/**
 * Collision-free id for a locally saved strategy. Older builds keyed entries
 * by content length + timestamp, which could collide when two saves landed
 * in the same millisecond with equal shapes.
 */
export function newUserStrategyId(kind: "user" | "import" | "formula" = "user"): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  return kind === "user" ? `user_${random}` : `user_${kind}_${random}`;
}

export type UserStrategySpecDisplay = {
  kind: "conditions" | "formula";
  entry: string[];
  exit: string[];
};

const FORMULA_SCHEMA_VERSION = "user_strategy_formula.v1";

function conditionLines(group: unknown): string[] {
  if (!Array.isArray(group)) return [];
  return group
    .map((condition) => isPlainObject(condition) ? conditionStatement(condition) : "")
    .filter((line) => line.length > 0);
}

/**
 * Renders a saved spec into display lines without ever throwing.  Two spec
 * shapes exist in the wild:
 *  - user_strategy.v2 (workshop): entry.all_of / entry.any_of / exit.any_of
 *    condition objects, shown through the factor condition statements;
 *  - user_strategy_formula.v1: entry_formula / exit_formula text.
 * Unknown shapes or malformed entries yield empty lists — the caller skips
 * them instead of crashing on missing fields.
 */
export function describeUserStrategySpec(spec: unknown): UserStrategySpecDisplay {
  if (!isPlainObject(spec)) return { kind: "conditions", entry: [], exit: [] };
  if (spec.schema_version === FORMULA_SCHEMA_VERSION) {
    const entry = typeof spec.entry_formula === "string" && spec.entry_formula.trim().length > 0
      ? [spec.entry_formula.trim()] : [];
    const exit = typeof spec.exit_formula === "string" && spec.exit_formula.trim().length > 0
      ? [spec.exit_formula.trim()] : [];
    return { kind: "formula", entry, exit };
  }
  const entry = isPlainObject(spec.entry) ? spec.entry : {};
  const exit = isPlainObject(spec.exit) ? spec.exit : {};
  return {
    kind: "conditions",
    entry: [...conditionLines(entry.all_of), ...conditionLines(entry.any_of)],
    exit: conditionLines(exit.any_of),
  };
}

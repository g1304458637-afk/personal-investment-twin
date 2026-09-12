import source from "@/generated/strategy-library.json";

/**
 * Read-only reference library: the four built-in strategies' rule tables and
 * parameters, embedded as data.  Validation only — no finance in the browser.
 */

export interface LibraryEntry {
  strategyId: string;
  version: string;
  title: string;
  description: string;
  params: Record<string, number | string>;
  ruleTable: { ruleId: string; source: string; statement: string }[];
}

export interface StrategyLibraryView {
  strategies: LibraryEntry[];
}

const fail = (): never => { throw new Error("strategy_library_projection_invalid"); };
const object = (x: unknown): Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x) ? x as Record<string, unknown> : fail();
const text = (x: unknown): string => typeof x === "string" && x.trim().length > 0 && x.length <= 6000 ? x : fail();
const array = (x: unknown): unknown[] => Array.isArray(x) && x.length <= 100 ? x : fail();

export function adaptStrategyLibrary(raw: unknown): StrategyLibraryView {
  const value = object(raw);
  if (value.schema_version !== "strategy_library.v1") fail();
  const strategies = array(value.strategies).map((item) => {
    const entry = object(item);
    const ruleTable = array(entry.rule_table).map((rule) => {
      const r = object(rule);
      return { ruleId: text(r.rule_id), source: text(r.source), statement: text(r.statement) };
    });
    if (!ruleTable.some((rule) => rule.source === "user_defined" || rule.source.startsWith("lens_rule") || rule.source.startsWith("public_rule"))) fail();
    if (!ruleTable.some((rule) => rule.source === "adaptation" || rule.source === "system_execution")) fail();
    const params = object(entry.params);
    return {
      strategyId: text(entry.strategy_id),
      version: text(entry.version),
      title: text(entry.title),
      description: text(entry.description),
      params: Object.fromEntries(Object.entries(params).map(([key, item]) => {
        if (typeof item === "number" && Number.isFinite(item)) return [text(key), item] as const;
        if (typeof item === "string" && item.length <= 100) return [text(key), item] as const;
        return fail();
      })),
      ruleTable,
    };
  });
  if (strategies.length < 2) fail();
  return { strategies };
}

export const strategyLibrary: StrategyLibraryView = adaptStrategyLibrary(source);

/**
 * Export/import of user strategy specs as portable JSON files.
 *
 * Pure frontend concern: specs live in localStorage, and moving them between
 * machines must not involve the desktop runtime. The import path re-uses the
 * same validation strength as readUserStrategies (basic shape + schema
 * version) so a hostile file can only fail with an inline error, never crash
 * a page or poison the saved library.
 */
import type { SavedUserStrategy } from "./userStrategyLibrary.ts";

/** The two spec shapes the deterministic interpreter accepts today. */
export const SPEC_IMPORT_SCHEMA_VERSIONS = ["user_strategy.v2", "user_strategy_formula.v1"] as const;
export type SpecImportSchemaVersion = (typeof SPEC_IMPORT_SCHEMA_VERSIONS)[number];

export interface StrategySpecExportFile {
  schema_version: SpecImportSchemaVersion;
  name: string;
  spec: Record<string, unknown>;
  exported_at: string;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Builds the downloadable export document for one saved strategy. */
export function buildSpecExportFile(entry: SavedUserStrategy, exportedAt = new Date().toISOString()): StrategySpecExportFile {
  return {
    schema_version: entry.spec.schema_version as SpecImportSchemaVersion,
    name: entry.name,
    spec: entry.spec,
    exported_at: exportedAt,
  };
}

export type SpecImportReason =
  | "not_json"
  | "not_object"
  | "unsupported_schema"
  | "bad_name"
  | "bad_spec"
  | "schema_mismatch";

export type SpecImportResult =
  | { ok: true; name: string; spec: Record<string, unknown> }
  | { ok: false; reason: SpecImportReason };

const MAX_NAME_LENGTH = 80;

/**
 * Parses and validates one imported file body. The top-level schema_version
 * must be one of the supported spec schemas, and the embedded spec must carry
 * the same schema_version so the file header can never mask a different spec.
 */
export function parseSpecImport(raw: string): SpecImportResult {
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return { ok: false, reason: "not_json" }; }
  if (!isPlainObject(parsed)) return { ok: false, reason: "not_object" };
  const version = parsed.schema_version;
  if (typeof version !== "string" || !(SPEC_IMPORT_SCHEMA_VERSIONS as readonly string[]).includes(version)) {
    return { ok: false, reason: "unsupported_schema" };
  }
  if (typeof parsed.name !== "string" || parsed.name.trim().length === 0 || parsed.name.trim().length > MAX_NAME_LENGTH) {
    return { ok: false, reason: "bad_name" };
  }
  const spec = parsed.spec;
  if (!isPlainObject(spec)) return { ok: false, reason: "bad_spec" };
  if (typeof spec.schema_version !== "string" || spec.schema_version.trim().length === 0) {
    return { ok: false, reason: "bad_spec" };
  }
  if (spec.schema_version !== version) return { ok: false, reason: "schema_mismatch" };
  return { ok: true, name: parsed.name.trim(), spec };
}

/**
 * Returns an unused display name: identical names get " (2)", " (3)", …
 * appended so an import can never silently overwrite a saved strategy.
 */
export function dedupeStrategyName(existingNames: readonly string[], name: string): string {
  const taken = new Set(existingNames);
  if (!taken.has(name)) return name;
  for (let suffix = 2; ; suffix += 1) {
    const candidate = `${name} (${suffix})`;
    if (!taken.has(candidate)) return candidate;
  }
}

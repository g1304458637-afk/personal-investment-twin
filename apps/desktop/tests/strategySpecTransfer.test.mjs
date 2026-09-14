import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

const { buildSpecExportFile, parseSpecImport, dedupeStrategyName, SPEC_IMPORT_SCHEMA_VERSIONS }
  = await import('../src/lib/strategySpecTransfer.ts');
const { readUserStrategies } = await import('../src/lib/userStrategyLibrary.ts');

const SPEC = {
  schema_version: 'user_strategy.v2',
  name: '突破策略',
  entry: { all_of: [{ factor: 'breakout_high', op: 'true' }], any_of: [] },
  exit: { any_of: [], stop_loss_pct: 0.08, atr_trailing_mult: null },
  sizing: { mode: 'equal_weight', fraction: 0.25 },
  constraints: { max_positions: 4 },
};

function savedEntry() {
  return { id: 'user_1_abc', name: '突破策略', savedAt: '2026-09-15', spec: SPEC };
}

test('export file carries schema_version, name, spec and export time; imports round-trip', () => {
  const file = buildSpecExportFile(savedEntry(), '2026-09-15T08:00:00.000Z');
  assert.deepEqual(Object.keys(file).sort(), ['exported_at', 'name', 'schema_version', 'spec']);
  assert.equal(file.schema_version, 'user_strategy.v2');
  assert.equal(file.name, '突破策略');
  assert.equal(file.exported_at, '2026-09-15T08:00:00.000Z');
  const imported = parseSpecImport(JSON.stringify(file));
  assert.equal(imported.ok, true);
  assert.equal(imported.name, '突破策略');
  assert.deepEqual(imported.spec, SPEC);
});

test('import accepts both supported spec shapes and rejects everything else', () => {
  for (const version of SPEC_IMPORT_SCHEMA_VERSIONS) {
    const result = parseSpecImport(JSON.stringify({
      schema_version: version, name: 'x', spec: { schema_version: version }, exported_at: '2026-09-15',
    }));
    assert.equal(result.ok, true, version);
  }
  const bad = [
    ['not_json', 'this is { not json'],
    ['not_object', JSON.stringify([1, 2])],
    ['not_object', JSON.stringify('user_strategy.v2')],
    ['unsupported_schema', JSON.stringify({ schema_version: 'user_strategy.v1', name: 'x', spec: {} })],
    ['bad_name', JSON.stringify({ schema_version: 'user_strategy.v2', name: '   ', spec: { schema_version: 'user_strategy.v2' } })],
    ['bad_name', JSON.stringify({ schema_version: 'user_strategy.v2', name: 42, spec: { schema_version: 'user_strategy.v2' } })],
    ['bad_name', JSON.stringify({ schema_version: 'user_strategy.v2', name: 'x'.repeat(81), spec: { schema_version: 'user_strategy.v2' } })],
    ['bad_spec', JSON.stringify({ schema_version: 'user_strategy.v2', name: 'x', spec: 'user_strategy.v2' })],
    ['bad_spec', JSON.stringify({ schema_version: 'user_strategy.v2', name: 'x', spec: {} })],
    ['schema_mismatch', JSON.stringify({ schema_version: 'user_strategy.v2', name: 'x', spec: { schema_version: 'user_strategy_formula.v1' } })],
  ];
  for (const [reason, raw] of bad) {
    assert.deepEqual(parseSpecImport(raw), { ok: false, reason }, reason);
  }
});

test('duplicate imported names get a numeric suffix and never overwrite saved strategies', () => {
  assert.equal(dedupeStrategyName(['a', 'b'], 'c'), 'c');
  assert.equal(dedupeStrategyName(['a'], 'a'), 'a (2)');
  assert.equal(dedupeStrategyName(['a', 'a (2)', 'a (3)'], 'a'), 'a (4)');
  // The suffixed import still passes the shared library reader shape.
  const name = dedupeStrategyName(['双均线'], '双均线');
  const entry = { id: 'user_import_x', name, savedAt: '2026-09-15', spec: SPEC };
  assert.deepEqual(readUserStrategies({
    getItem: (key) => (key === 'toujing.userStrategies' ? JSON.stringify([entry]) : null),
  }), [entry]);
});

test('both strategy-list surfaces render export/import through the validated helpers', async () => {
  const page = await readFile(new URL('../src/pages/MyStrategiesPage.tsx', import.meta.url), 'utf8');
  assert.match(page, /buildSpecExportFile/);
  assert.match(page, /parseSpecImport/);
  assert.match(page, /dedupeStrategyName/);
  assert.match(page, /"Import spec"/);
  assert.match(page, /"Export spec"/);
  // Import failures stay inline (role=alert), never a thrown error.
  assert.match(page, /"Import failed"/);
  assert.match(page, /role="alert"/);
  const lib = await readFile(new URL('../src/lib/strategySpecTransfer.ts', import.meta.url), 'utf8');
  assert.match(lib, /"user_strategy\.v2", "user_strategy_formula\.v1"/);
});

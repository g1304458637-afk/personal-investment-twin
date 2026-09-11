import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { modelServiceRequest, modelServiceCopy } from '../src/data/modelService.ts';

test('browser rejects without storing or sending key', async () => {
  await assert.rejects(modelServiceRequest('save', 'test-only-value'), /desktop_runtime_required/);
});
test('only save sends a key to the exact fixed command', async () => {
  const calls = [];
  const call = async (command, args) => { calls.push([command, args]); return { configured: true }; };
  for (const action of ['save', 'status', 'delete', 'test']) await modelServiceRequest(action, 'test-only-value', call);
  assert.deepEqual(calls, [['model_service_save', { apiKey: 'test-only-value' }], ['model_service_status', undefined], ['model_service_delete', undefined], ['model_service_test', undefined]]);
});
test('native unknown error is redacted, known code remains usable', async () => {
  await assert.rejects(modelServiceRequest('test', undefined, async () => { throw 'private-test-value'; }), /^Error: model_service_unavailable$/);
  await assert.rejects(modelServiceRequest('test', undefined, async () => { throw 'model_not_configured'; }), /^Error: model_not_configured$/);
});
test('settings have password input, clear-before-await and duplicate-action guard', () => {
  const source = readFileSync(new URL('../src/components/review/ModelServiceSettings.tsx', import.meta.url), 'utf8');
  assert.match(source, /type="password"/);
  assert.match(source, /if \(locked.current \|\| !desktop\) return/);
  assert.ok(source.indexOf('setKey("");', source.indexOf('async function act')) < source.indexOf('await modelServiceRequest', source.indexOf('async function act')));
  assert.match(source, /disabled=\{busy \|\| !status\?\.configured \|\| !!key\}/);
  assert.doesNotMatch(source, /localStorage|sessionStorage|console\./);
  assert.match(source, /role="status" aria-live="polite"/);
});
test('both locales disclose fixed test cost, browser boundary and in-flight deletion behavior', () => {
  for (const c of Object.values(modelServiceCopy)) {
    assert.ok(c.testNotice && c.browser && c.deleted && c.errors.model_keychain_unavailable);
  }
  assert.match(modelServiceCopy['zh-CN'].deleted, /已经发出的请求/);
});

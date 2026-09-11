import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile, access} from 'node:fs/promises';
const read = file => readFile(new URL(file, import.meta.url), 'utf8');

test('desktop builds only the main window, with no companion entry or capability', async () => {
  const config = JSON.parse(await read('../src-tauri/tauri.conf.json'));
  assert.deepEqual(config.app.windows.map(window => window.label), ['main']);
  assert.doesNotMatch(await read('../vite.config.ts'), /pet\.html/);
  for (const path of ['../pet.html', '../src-tauri/capabilities/pet.json', '../src-tauri/src/pet.rs']) {
    await assert.rejects(access(new URL(path, import.meta.url)), {code: 'ENOENT'});
  }
});

test('removing the pet preserves the native main-window command guard and runtime', async () => {
  const lib = await read('../src-tauri/src/lib.rs');
  assert.match(lib, /webview_ref\(\)\.label\(\) != "main"/);
  assert.ok(lib.indexOf('window_command_not_allowed') < lib.indexOf('tauri::generate_handler!'));
  assert.doesNotMatch(lib, /pet::|mod pet|on_window_event/);
  assert.match(lib, /runtime::runtime_product_request/);
  const runtime = await read('../src-tauri/src/runtime.rs');
  assert.doesNotMatch(runtime, /crate::pet/);
  assert.match(runtime, /RuntimeManager::start/);
});

test('settings and chat no longer depend on companion state', async () => {
  assert.doesNotMatch(await read('../src/App.tsx'), /PetMainBridge/);
  const settings = await read('../src/workspace/SettingsWorkspace.tsx');
  assert.doesNotMatch(settings, /PetSettings/);
  assert.match(settings, /ModelServiceSettings/);
  const chat = await read('../src/data/agentChat.ts');
  assert.doesNotMatch(chat, /publishAgentActivity|activityForTurn|\/pet\//);
  assert.match(chat, /export function saveChat\(/);
  assert.match(chat, /export function restoredAccountTurns\(/);
});

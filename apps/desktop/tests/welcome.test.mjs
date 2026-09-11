import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { welcomeStartupPath, saveWelcomePreference, WELCOME_PREFERENCE } from '../src/workspace/welcomePreference.ts';
test('welcome is default and skipping requires an explicit saved preference', () => {
  for (const value of [null, '', 'false', '1', 'corrupt']) assert.equal(welcomeStartupPath({getItem:()=>value}), '/welcome');
  assert.equal(welcomeStartupPath({getItem:()=> 'true'}), '/investments');
});
test('restricted storage keeps welcome usable', () => {
  assert.equal(welcomeStartupPath({getItem:()=>{throw Error();}}), '/welcome');
  assert.equal(saveWelcomePreference({setItem:()=>{throw Error();}}, true), false);
});
test('preference writes only the presentation key', () => {
  const writes=[];
  assert.equal(saveWelcomePreference({setItem:(...args)=>writes.push(args)}, false), true);
  assert.deepEqual(writes, [[WELCOME_PREFERENCE, 'false']]);
});
test('welcome is outside workspace; explicit example preserves subject and account scope', async () => {
  const src = await readFile(new URL('../src/workspace/WelcomePage.tsx', import.meta.url), 'utf8');
  assert.match(src, /item.subjectId === entry.episode.subjectId && item.accountId === entry.episode.accountId/);
  assert.match(src, /onClick=\{openExample\}/);
  assert.doesNotMatch(src, /useEffect|invoke\(|fetch\(/);
  const app = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.ok(app.indexOf('path="/welcome"') < app.indexOf('<Route element={<WorkspaceShell'));
});
test('sphere is independent local artwork and supports reduced motion', async () => {
  const component=await readFile(new URL('../src/components/common/GlassOrbLogo.tsx',import.meta.url),'utf8');
  const css=await readFile(new URL('../src/components/common/glass-orb-logo.css',import.meta.url),'utf8');
  assert.match(component,/assets\/glass-orb.png/);
  assert.match(css,/prefers-reduced-motion/);
  assert.match(css,/animation:none/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {startChatTurn} from '../src/data/chatTurnState.ts';
import {chatContextErrorText, chatErrorText} from '../src/workspace/agentChatCopy.ts';

test('failed answer retries in place without losing question or prior answer', () => {
  const completed = {id:'one',question:'first',status:'complete',result:{inference_id:'kept'}};
  const failed = {id:'two',question:'follow up',status:'failed',result:null,reason:'failed'};
  const turns = [completed,failed]; const original = structuredClone(turns);
  const next = startChatTurn(turns,'ignored','new','two');
  assert.deepEqual(turns,original);
  assert.equal(next.length,2); assert.equal(next[0],completed);
  assert.deepEqual(next[1],{id:'two',question:'follow up',status:'running',result:null});
});
test('cannot overwrite later turns, completed answers or a running request', () => {
  const failed = {id:'a',question:'A',status:'failed',result:null};
  const done = {id:'b',question:'B',status:'complete',result:{}};
  assert.throws(()=>startChatTurn([failed,done],'Q','new','a'),/retry_not_latest/);
  assert.throws(()=>startChatTurn([done],'Q','new','b'),/retry_not_latest/);
  assert.throws(()=>startChatTurn([{...failed,status:'running'}],'Q','new'),/already_running/);
  assert.equal(startChatTurn([],'new question','new')[0].question,'new question');
});
test('context failure and answer failure have separate recovery language', () => {
  assert.match(chatContextErrorText('timeout','zh-CN'),/资料.*读取/);
  assert.match(chatErrorText('review_failed','zh-CN'),/回答/);
  assert.notEqual(chatContextErrorText('timeout','en-US'),chatErrorText('review_failed','en-US'));
});
test('UI preserves transcript, contains scrolling, auto-sizes input and collapses help', async () => {
  const page = await readFile(new URL('../src/workspace/AgentWorkspace.tsx',import.meta.url),'utf8');
  const css = await readFile(new URL('../src/workspace/agent-chat.css',import.meta.url),'utf8');
  assert.match(page,/!turns.length && !contextError/);
  assert.match(page,/role="log"/); assert.match(page,/submit\(turn.id\)/);
  assert.doesNotMatch(page,/Promise\.all/);
  assert.match(page,/useState<ChatContext \| null>\(\(\) => readChatContext\(scope\)\)/);
  assert.doesNotMatch(page,/setContext\(null\)/);
  assert.match(page,/context \? c.refreshing : c.loading/);
  assert.match(page,/loading \|\| contextError \|\| !context/);
  assert.match(page,/setModelError/);
  assert.match(page,/modelLoading \? <p role="status"/);
  assert.match(page,/<details className="agent-chat__guide-disclosure">/);
  // New capability examples may focus/scroll the composer after a user click.
  // Transcript updates must still never scroll the outer page.
  const chooser = page.slice(page.indexOf('const chooseQuestion ='), page.indexOf('return <div className="agent-chat__workspace"'));
  assert.match(chooser, /scrollIntoView/);
  assert.doesNotMatch(page.replace(chooser, ''), /scrollIntoView/);
  assert.match(page,/Math.min\(160/); assert.match(page,/if \(!retryId\) setDraft/);
  assert.match(css,/overflow-y: auto/); assert.match(css,/flex: 0 0 auto/);
});

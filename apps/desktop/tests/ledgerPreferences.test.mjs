import test from 'node:test';
import assert from 'node:assert/strict';
import { backupPreferences, applyRestoredPreferences } from '../src/data/ledgerPreferences.ts';
const storage = () => { const data=new Map([['toujing.theme','dark'],['secret','never-export']]); return {data,getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}; };
test('backup exports only allowed preferences, restoring removes absent allowlisted preferences',()=>{const s=storage();assert.deepEqual(backupPreferences(s),{'toujing.theme':'dark'});applyRestoredPreferences(s,{'toujing.userStrategies':'[]'});assert.equal(s.data.has('toujing.theme'),false);assert.equal(s.data.get('toujing.userStrategies'),'[]');assert.equal(s.data.get('secret'),'never-export');});
test('invalid restore preferences fail before modifying storage',()=>{const s=storage();assert.throws(()=>applyRestoredPreferences(s,{'toujing.theme':'light',secret:'bad'}));assert.equal(s.data.get('toujing.theme'),'dark');assert.throws(()=>applyRestoredPreferences(s,{'toujing.theme':1}));});

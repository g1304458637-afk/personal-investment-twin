import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import type {DemoData} from '../src/model.ts';
import {buildCareerReview} from '../src/entry/careerReview.ts';
const fixture=JSON.parse(readFileSync(new URL('../public/demo-data.json',import.meta.url),'utf8')) as DemoData;
const copy=()=>structuredClone(fixture);
test('教学档案回顾与实际成交、账户和年度记录一致',()=>{
 const r=buildCareerReview(fixture);
 assert.equal(r.tradeCount,54); assert.equal(r.assetCount,8);
 assert.equal(r.addCount,11); assert.equal(r.lowerAddCount,7); assert.equal(r.counterCount,4);
 assert.equal(r.drawdownDate,'2022-10-31'); assert.ok(Math.abs(r.maxDrawdown+0.19711680364954828)<1e-12);
 assert.equal(r.equity,791282.78); assert.equal(r.netInvested,630000); assert.equal(r.pnl,161282.78);
 assert.equal(r.findings[0].evidence.length,11);
 assert.equal(r.findings[0].evidence.filter(e=>e.kind==='counter').length,4);
 for(const y of r.years) {assert.equal(fixture.dates[y.index].slice(0,4),y.year); assert.ok(!fixture.dates[y.index+1]?.startsWith(y.year));}
 assert.equal(r.years.find(y=>y.year==='2021')?.pnl,8787.33);
 assert.equal(r.years.find(y=>y.year==='2021')?.netFlow,80000);
});
test('缺失成交引用和日期错位不能当作已确认的证据',()=>{
 const d=copy(); d.paths[0].fills=d.paths[0].fills.filter(f=>f.execution_id!=='design-fill-005');
 assert.throws(()=>buildCareerReview(d),/成交证据/);
 const other=copy(); other.paths[0].days[1].date='2020-01-04';
 assert.throws(()=>buildCareerReview(other),/日期/);
});
test('无连续买入时明确说明，空档案和年度篡改被拒绝',()=>{
 const d=copy(); d.lifetime.adds=[]; const r=buildCareerReview(d);
 assert.equal(r.addCount,0); assert.match(r.headline,/不足/);
 assert.throws(()=>buildCareerReview({} as DemoData),/不完整/);
 const changed=copy(); changed.lifetime.years[1].pnl='80000';
 assert.throws(()=>buildCareerReview(changed),/年度损益/);
});

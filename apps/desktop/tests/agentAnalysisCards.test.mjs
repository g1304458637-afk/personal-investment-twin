import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { validatedAnalysisCards } from "../src/data/agentAnalysisCards.ts";
import { projectAccountAnswer, restoredConversationTurns, verifiedChatResult } from "../src/data/agentChat.ts";

const l = text => ({zh:text,en:text});
const card = {id:"card-one",kind:"hypothetical_trade_impact",source_ref:"scenario",title:l("Before / after"),subtitle:l("Synthetic · fees CNY 0"),
  columns:[l("Before"),l("After")],rows:[{label:l("Cash (CNY)"),cells:[l("58,170.00"),l("53,850.00")],explanation:l("Recorded cash, after explicit fees.")}],notes:[l("Hypothetical only")]};
const ledger = {read:["scenario"],cited:["scenario"],analysis:["scenario"],public:[],synthetic:true};
const scope = {scope_kind:"account",subject_id:"test",account_id:"demo",data_mode:"synthetic_showcase"};
const context = {version:"account_review_context_v1",scope,source_fingerprint:"f",finding_options:[],record_refs:[],conversation_version:"account_conversation_answer_v2"};
const result = {inference_id:"inference",scope,source_fingerprint:"f",invalidated:false,verification:"receipts_and_grounding_review_v1",
  read_refs:["scenario"],analysis_read_refs:["scenario"],analysis_cards:[card],answer:{version:"account_conversation_answer_v2",paragraphs:[{kind:"fact",text:l("Scenario cash changes."),refs:["scenario"]}],guides:[]}};

test("all five runtime-generated offline card shapes reach the frontend validator", async () => {
  const fixture=JSON.parse(await readFile(new URL("./fixtures/agent-analysis-cards.synthetic.json",import.meta.url),"utf8"));
  assert.equal(fixture.live_public_data,false);
  const records=fixture.cards, refs=records.map(c=>c.source_ref);
  const cards=validatedAnalysisCards(records,{read:refs,cited:refs,analysis:records.filter(c=>!c.kind.startsWith("public_")).map(c=>c.source_ref),public:records.filter(c=>c.kind.startsWith("public_")).map(c=>c.source_ref),synthetic:true});
  assert.equal(cards.length,5);
  assert.equal(new Set(cards.map(c=>c.kind)).size,5);
  const scenario=cards.find(c=>c.kind==="hypothetical_trade_impact");
  assert.equal(scenario.rows[0].cells[0].zh,"58,170.00 CNY");
  assert.equal(scenario.rows[0].cells[1].zh,"53,850.00 CNY");
  const periods=cards.find(c=>c.kind==="owned_period_comparison");
  assert.match(periods.rows.find(row=>row.label.zh.includes("HHI")).label.zh,/期末/);
  assert.match(cards.find(c=>c.kind==="owned_same_stock_comparison").title.zh,/不可直接比较/);
  assert.match(cards.find(c=>c.kind==="public_technical").subtitle.zh,/前复权/);
});

test("only cited, read, correctly categorized deterministic cards are displayed", () => {
  assert.deepEqual(validatedAnalysisCards([card],ledger),[card]);
  for (const override of [{read:[]},{cited:[]},{analysis:[]},{synthetic:false}]) assert.deepEqual(validatedAnalysisCards([card],{...ledger,...override}),[]);
  const publicCard={...card,kind:"public_technical"};
  assert.deepEqual(validatedAnalysisCards([publicCard],ledger),[]);
  assert.equal(validatedAnalysisCards([publicCard],{...ledger,analysis:[],public:["scenario"],synthetic:false}).length,1);
});
test("malformed optional transport cannot crash or replace a validated answer", () => {
  for (const change of [c=>{c.rows=null},c=>{c.rows[0]=null},c=>{c.rows[0].cells=[l("one")]},c=>{c.title={zh:"only"}},
    c=>{c.kind="invented"},c=>{c.columns=[]},c=>{c.rows[0].cells[0].en="x".repeat(1201)},c=>{c.notes=Array(6).fill(l("note"))}]) {
    const invalid=structuredClone(card);change(invalid);
    assert.deepEqual(validatedAnalysisCards([invalid],ledger),[]);
    assert.equal(projectAccountAnswer({...result,analysis_cards:[invalid]},context,"zh-CN").summary,"Scenario cash changes.");
  }
  for (const bad of [undefined,null,{},"text",[null],Array(6).fill(card)]) assert.deepEqual(validatedAnalysisCards(bad,ledger),[]);
});
test("cards remain scoped to verified answers and survive completed archive restoration", () => {
  assert.equal(projectAccountAnswer(result,context,"zh-CN").cards.length,1);
  assert.equal(projectAccountAnswer({...result,source_fingerprint:"stale"},context,"zh-CN"),null);
  assert.equal(projectAccountAnswer({...result,scope:{...scope,account_id:"foreign"}},context,"zh-CN"),null);
  assert.equal(projectAccountAnswer({...result,verification:undefined},context,"zh-CN"),null);
  const restored=restoredConversationTurns({...context,conversation_turns:[{id:"saved",question:"Scenario",status:"complete",result}]});
  assert.equal(projectAccountAnswer(restored[0].result,context,"en-US").cards[0].rows[0].cells[1].en,"53,850.00");
  const old={...result,analysis_cards:undefined};
  assert.ok(verifiedChatResult(old,context)); assert.deepEqual(projectAccountAnswer(old,context,"zh-CN").cards,[]);
});
test("duplicates and hostile text are data only, no inferred calculations or HTML", async () => {
  assert.equal(validatedAnalysisCards([card,card],ledger).length,1);
  const copy=validatedAnalysisCards([card],ledger);copy[0].rows[0].cells[0].zh="changed";
  assert.equal(card.rows[0].cells[0].zh,"58,170.00");
  const component=await readFile(new URL("../src/workspace/AgentAnalysisCards.tsx",import.meta.url),"utf8");
  assert.doesNotMatch(component,/dangerouslySetInnerHTML|parseFloat|eval\(/);
  assert.match(component,/scope="col"/);assert.match(component,/scope="row"/);assert.match(component,/tabIndex=\{0\}/);
  const workspace=await readFile(new URL("../src/workspace/AgentWorkspace.tsx",import.meta.url),"utf8");
  assert.ok(workspace.indexOf("verifiedChatResult(turn.result, context)") < workspace.indexOf("<AgentAnalysisCards"));
  assert.match(workspace,/AgentTurnStatus turn=\{turn\}/);assert.match(workspace,/agent-chat__source-disclosure/);
});

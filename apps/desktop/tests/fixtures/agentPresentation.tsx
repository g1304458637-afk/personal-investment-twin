/** Offline visual harness; not a production entry and never starts a model. */
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { AgentAnalysisCards } from "../../src/workspace/AgentAnalysisCards";
import { AgentTurnStatus } from "../../src/workspace/AgentTurnStatus";
import { AgentCapabilityOverview } from "../../src/workspace/AgentCapabilityOverview";
import { validatedAnalysisCards } from "../../src/data/agentAnalysisCards";
import fixture from "./agent-analysis-cards.synthetic.json";
import "../../src/index.css";
import "../../src/workspace/agent-chat.css";
import poster from "../../src/assets/liquid-backdrop-poster.jpg";

const allCards=validatedAnalysisCards(fixture.cards, {read:fixture.cards.map(c=>c.source_ref),cited:fixture.cards.map(c=>c.source_ref),analysis:fixture.cards.filter(c=>!c.kind.startsWith("public_")).map(c=>c.source_ref),public:fixture.cards.filter(c=>c.kind.startsWith("public_")).map(c=>c.source_ref),synthetic:true});
function Preview() {
  const [locale,setLocale]=useState<"zh-CN"|"en-US">("zh-CN"), [selected,setSelected]=useState(0), [phase,setPhase]=useState("checking"), [draft,setDraft]=useState("");
  const [narrow,setNarrow]=useState(false), [light,setLight]=useState(false);
  const zh=locale==="zh-CN";
  return <div data-theme={light ? "light":"dark"} style={{height:"100vh",overflow:"auto",background:light?"#f1f7fa":`#0a1625 url(${poster}) center / cover fixed`,color:light?"#21394b":"#e7f1f8",padding:"24px 16px"}}>
    <div style={{maxWidth:narrow?480:1120,margin:"auto"}}>
      <header style={{display:"flex",gap:14,flexWrap:"wrap",marginBottom:18,fontSize:12}}><strong>OFFLINE QA · 非在线模型回答</strong>
        <button onClick={()=>setLocale(zh?"en-US":"zh-CN")}>中文 / English</button><button onClick={()=>setNarrow(!narrow)}>窄容器</button><button onClick={()=>setLight(!light)}>浅色 / 深色</button>
        <label>结果类型 <select value={selected} onChange={e=>setSelected(Number(e.target.value))}>{allCards.map((c,i)=><option key={c.id} value={i}>{c.title[zh?"zh":"en"]}</option>)}</select></label>
        <label>阶段 <select value={phase} onChange={e=>setPhase(e.target.value)}>{["researching","reading","searching","quoting","writing","checking","failed","stopped"].map(p=><option key={p}>{p}</option>)}</select></label>
      </header>
      <div className="agent-chat"><AgentCapabilityOverview locale={locale} busy={false} services={{desktop:true,wholeAccount:true,synthetic:true,model:"configured",quotes:"configured",search:"configured"}} onQuestion={setDraft}/>
      <div className="agent-chat__conversation" style={{height:"auto",minHeight:600}}><div className="agent-chat__answer"><span className="agent-chat__speaker">投镜 · 本地固定资料验收</span>
        <p className="agent-chat__summary">{zh?"下面是已读取记录的结构化展示。仅用于离线界面验收，不是实时行情或模型回答。":"Structured records for offline UI acceptance only. Not live quotes or a model answer."}</p>
        <AgentAnalysisCards key={selected} cards={[allCards[selected]]} locale={locale}/>
        <AgentTurnStatus locale={locale} turn={{id:"qa",question:"QA",result:null,status:phase==="failed"?"failed":phase==="stopped"?"stopped":"running",phase,reason:"account_model_timeout",diagnosticId:"abc123def456"}}/>
      </div><form className="agent-chat__composer" onSubmit={e=>e.preventDefault()}><textarea aria-label="仅填入，不发送" value={draft} placeholder="离线验收输入框 · 不调用模型" onChange={e=>setDraft(e.target.value)}/></form></div></div>
    </div>
  </div>;
}
createRoot(document.getElementById("root")!).render(<MemoryRouter><Preview/></MemoryRouter>);

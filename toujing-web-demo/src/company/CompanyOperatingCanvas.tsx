import {useEffect, useState} from 'react';
import {ArrowUpRight, RefreshCw} from 'lucide-react';
import {runtime, type ResearchScope} from '../alignment';
import {OperatingGraph} from './OperatingGraph';
import {operatingCompany, operatingEvidenceScope, type OperatingProjection} from './companyProjection';
import type {ResearchCompany} from './companyResearch';
import './company-canvas.css';

export function CompanyOperatingCanvas({scope, name, active = true, onSource, onQuestion}: {
  scope: ResearchScope; name: string; active?: boolean;
  onSource: (scope: ResearchScope) => void;
  onQuestion: (question: string, scope: ResearchScope) => void;
}) {
  const [loaded, setLoaded] = useState<{key: string; value: OperatingProjection; company: ResearchCompany | null} | null>(null);
  const [error, setError] = useState(''), [actionError, setActionError] = useState(''), [retry, setRetry] = useState(0);
  const proof = scope.mode === 'as_known_then' ? 'public_reconstruction' : 'hindsight';
  const key = JSON.stringify([scope.instrument_id, scope.knowledge_at, proof, retry]);
  const current = loaded?.key === key ? loaded : null;
  useEffect(() => {
    let active = true; setError(''); setActionError('');
    runtime<OperatingProjection>('workbench.company.operating', {
      instrument_id: scope.instrument_id, knowledge_at: scope.knowledge_at, historical_proof: proof,
    }).then(value => {
      const company = operatingCompany(value, scope.instrument_id, name);
      if (active) setLoaded({key, value, company});
    }).catch(reason => {if (active) setError(reason instanceof Error ? reason.message : '经营来源未能读取，请重试。');});
    return () => {active = false;};
  }, [key, name]);
  const locate = (id: string) => {
    if (!current) return;
    try {setActionError(''); onSource(operatingEvidenceScope(scope, current.value, id));}
    catch (reason) {setActionError((reason as Error).message);}
  };
  const discuss = (question: string, sourceIds: string[] = []) => {
    if (!current) return;
    try {setActionError(''); onQuestion(question, operatingEvidenceScope(scope, current.value, sourceIds[0]));}
    catch (reason) {setActionError((reason as Error).message);}
  };
  return <section className="company-operating-workspace" aria-label="公司经营结构研究">
    <header className="og-heading"><div><h2>经营结构图</h2>{current?.value.graph && <span>{current.value.source_year} 年报 · {current.value.graph.coverage.entities} 项经营实体</span>}</div><button className="text-button" onClick={() => setRetry(value => value + 1)}><RefreshCw size={13}/>重新核对来源</button></header>
    {error ? <div className="og-empty" role="alert"><h3>经营结构暂时未能读取</h3><p>{error}</p><button className="secondary" onClick={() => setRetry(value => value + 1)}>重新读取</button></div>
      : !current ? <div className="og-empty" role="status"><h3>正在核对经营结构</h3><p>读取已保存的提取结果，核对原文与版本…</p></div>
      : !current.company ? <div className="og-empty"><h3>当前范围暂无经营结构</h3><p>{current.value.reason ?? '可继续阅读已收录的报告原文。'}</p><p>可以切换公司或资料截止日期，或进入「财报与证据」阅读。</p></div>
      : <>
        <OperatingGraph company={current.company} active={active} onSource={locate} onAsk={discuss}/>
        <footer className="og-source-footer"><details><summary><span className="og-source-dot"/>原文候选 · 来源与覆盖</summary><div className="og-qualification"><strong>{current.value.document_title}</strong><p>{current.value.boundary}</p><p>已保存的结构提取 · 本次重新核对原文。拦截 {current.value.held_count} 项，待补充 {current.value.unknown_count} 项。</p><code>{current.value.source_sha256}</code></div></details><button onClick={() => discuss('核查这家公司的经营结构：从原文找出主要业务、产品、生产与客户关系，区分原文记载和待核实关系。')}>就图谱提问<ArrowUpRight size={13}/></button></footer>
      </>}
    {actionError && <p className="form-error" role="alert">{actionError}</p>}
  </section>;
}

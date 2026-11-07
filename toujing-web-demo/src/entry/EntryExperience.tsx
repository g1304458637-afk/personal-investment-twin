import { lazy, Suspense, useMemo, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight } from 'lucide-react';
import { csvRows, type DemoData, type Fill } from '../model';
import { makeTrace } from './trace';
import type { ImportedPreview } from './importReview';
export type { ImportedPreview } from './importReview';
import './entry.css';

const CareerAwakening = lazy(() => import('./CareerAwakening').then(module => ({ default: module.CareerAwakening })));

export type EntryResult = { kind: 'sample' } | { kind: 'import'; preview: ImportedPreview };

type EntryProps = {
  data: DemoData;
  fills: Fill[];
  reducedMotion: boolean;
  onFinish: (result: EntryResult) => void;
  onDiscuss: (question: string) => void;
  onPlaybackPause: (paused: boolean) => void;
  sampleInitially?: boolean;
};

export function EntryExperience({ data, fills, reducedMotion, onFinish, onDiscuss, onPlaybackPause, sampleInitially = false }: EntryProps) {
  const [selection, setSelection] = useState<EntryResult | null>(sampleInitially ? { kind: 'sample' } : null);
  const [problem, setProblem] = useState('');
  const [reading, setReading] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const sample = useMemo(() => makeTrace(fills), [fills]);

  async function readFile(file: File) {
    setProblem('');
    setReading(true);
    try {
      if (file.size > 5_000_000) throw new Error('请使用 5 MB 以内的 CSV 文件。');
      const rows = csvRows(await file.text());
      if (!rows.length) throw new Error('文件中没有可读取的成交记录。');
      setSelection({ kind: 'import', preview: { name: file.name, rows } });
    } catch (error) {
      setProblem(error instanceof Error ? error.message : '文件读取失败，请重试。');
    } finally {
      setReading(false);
    }
  }

  if (selection) return <Suspense fallback={<section className="entry-loading"><img src="/orb.png" alt=""/><h1>正在连接你的投资经历…</h1><button className="secondary" onClick={() => onFinish(selection)}>进入投资档案</button></section>}><CareerAwakening data={data} preview={selection.kind === 'import' ? selection.preview : undefined} reducedMotion={reducedMotion} onFinish={() => onFinish(selection)} onDiscuss={onDiscuss} onPlaybackPause={onPlaybackPause}/></Suspense>;

  return <section className="entry-cover" aria-label="欢迎使用投镜">
    <div className="entry-cover-shade" aria-hidden="true" />
    <header className="entry-header"><div className="entry-brand"><img src="/orb.png" alt="" /><strong>投镜</strong><span>TOUJING</span></div></header>
    <main className="entry-hero">
      <div className="entry-copy">
        <h1>把投资经历，<br /><span>变成懂你的 AI。</span></h1>
        <p>回到当时，发现习惯，验证方法。<br />让每一次选择，都成为下一次研究的依据。</p>
        <div className="entry-actions">
          <button type="button" className="entry-primary" disabled={reading || !sample.count} onClick={() => setSelection({ kind: 'sample' })}>唤醒林远的投镜 <ArrowUpRight size={17} /></button>
          <button type="button" className="entry-secondary liquid-glass" disabled={reading} onClick={() => picker.current?.click()}>导入自己的成交数据 <ArrowUpRight size={17} /></button>
        </div>
        <input ref={picker} type="file" accept=".csv,text/csv" hidden onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void readFile(file); }} />
        <p className="entry-hint">先用林远的教学档案体验：生涯回放、投镜回顾与第一份分析。全程字幕讲述。导入自己的 CSV，也可回放记录、生成交易画像。</p>
        {reading && <p className="entry-status" role="status">正在读取成交记录…</p>}
        {problem && <p className="entry-error" role="alert">{problem} 请检查 CSV 后重新选择。</p>}
      </div>
      <div className="entry-preview-wrap">
        <div className="entry-preview-caption"><span>一轮投资，一段完整经历</span><span>投镜示例</span></div>
        <article className="entry-preview liquid-glass">
          <div className="entry-preview-top"><span>示例档案 · 模拟成交</span><span>历史行情</span></div>
          <h2>六年的选择，<br />汇成第一份理解。</h2>
          <p>看见你的投资生涯如何展开，再打开每条发现背后的记录。</p>
          <div className="entry-preview-numbers"><div><small>时间跨度</small><strong>{sample.start.slice(0, 4)} — {sample.end.slice(0, 4)}</strong></div><div><small>模拟成交</small><strong>{sample.count}<em> 笔</em></strong></div></div>
          <div className="entry-preview-rail" aria-hidden="true">{sample.points.map((point, index) => <i className={point.sell ? 'sell' : ''} key={index} style={{ left: `${point.position * 100}%` }} />)}</div>
          <div className="entry-preview-bottom"><span>真实历史行情 · 教学模拟交易</span><ArrowRight size={17} /></div>
        </article>
      </div>
    </main>
    <footer className="entry-footer">TOUJING / PERSONAL INVESTMENT INTELLIGENCE</footer>
  </section>;
}

/** Display-only projection. No financial arithmetic and no browser-generated answers. */
import type { ReviewContextView, ReviewInference } from "./decisionReview";

type LocalText = { zh: string; en: string };
export interface ReviewAnswerV2 {
  version: "question_driven_review_answer_v2";
  focus: "result_formation" | "operation_impact" | "decision_reason" | "available_facts";
  summary: LocalText;
  comparison_summary: LocalText[];
  qualification: LocalText;
  findings: { option_id: string; kind: string; evidence_ref: string; decision_id: string | null;
    title: LocalText; body: LocalText; qualification: LocalText }[];
}
export const answerCopy = {
  zh: { title: "这轮分析", empty: "围绕这轮投资提一个问题，投镜会结合记录与历史对比，选出值得回看的操作。",
    question: "这轮结果是怎样形成的，哪些操作值得回看？", open: "查看这次操作",
    legacy: "此前的解释", unavailable: "这份回答与当前记录不匹配，请重新分析。",
    evidence: "展开本次分析依据", evidenceHelp: "上方展示重点，下面保留本次回答引用的记录、历史假设及解释依据。同一条记录只列一次；引用条数不代表独立证据的数量。" },
  en: { title: "This investment, reviewed", empty: "Ask about this investment. The review will connect records and historical comparisons to relevant operations.",
    question: "How did this result develop, and which operations deserve a closer look?", open: "View this operation",
    legacy: "Earlier interpretation", unavailable: "This answer does not match the current records. Please run the review again.",
    evidence: "Explore this answer’s evidence", evidenceHelp: "Highlights appear above. The records, historical alternatives and interpretation evidence referenced by this answer remain below. Each record appears once; reference count is not a count of independent evidence." },
};

export function projectReviewAnswer(answer: ReviewInference, context: ReviewContextView, locale: string) {
  const raw = answer.answer;
  if (!raw || raw.version !== "question_driven_review_answer_v2" || answer.invalidated) return null;
  if (answer.scope?.subject_id !== context.scope.subject_id || answer.scope.account_id !== context.scope.account_id
    || answer.scope.episode_id !== context.scope.episode_id) return null;
  const key = locale === "zh-CN" ? "zh" : "en";
  const local = (v: LocalText) => v?.[key];
  if (!local(raw.summary) || !local(raw.qualification) || !Array.isArray(raw.findings) || raw.findings.length > 3) return null;
  const seen = new Set<string>();
  for (const f of raw.findings) {
    const record = context.records.find(r => r.ref === f.evidence_ref);
    if (!record || record.subject_id !== context.scope.subject_id || record.account_id !== context.scope.account_id
      || record.episode_id !== context.scope.episode_id || seen.has(f.option_id)
      || !local(f.title) || !local(f.body) || !local(f.qualification)) return null;
    if (f.decision_id && !context.records.some(r => r.kind === "decision"
      && r.subject_id === context.scope.subject_id && r.account_id === context.scope.account_id
      && r.episode_id === context.scope.episode_id && r.value.decision_event_id === f.decision_id)) return null;
    seen.add(f.option_id);
  }
  if (!Array.isArray(raw.comparison_summary) || raw.comparison_summary.some(v => !local(v))) return null;
  if (raw.comparison_summary.length && !context.comparison) return null;
  // Use current, authorized canonical records, never model-authored row values.
  // Findings remain concise; the evidence appendix has no three-item truncation.
  const refs = new Set([
    ...raw.findings.map(f => f.evidence_ref),
    ...(answer.facts ?? []).map(f => f.ref),
    ...(answer.historical_comparisons ?? []).map(f => f.ref),
    ...(answer.possible_explanations ?? []).flatMap(h => [...h.supporting_evidence_refs, ...h.contradictory_evidence_refs]),
  ]);
  const byRef = new Map(context.records.map(r => [r.ref, r]));
  const evidence = [];
  for (const ref of refs) {
    const record = byRef.get(ref);
    if (!record) return null;
    const own = record.subject_id === context.scope.subject_id && record.account_id === context.scope.account_id
      && record.episode_id === context.scope.episode_id;
    if (!own && !context.comparison) return null;
    evidence.push(record);
  }
  return { summary: local(raw.summary), comparisonSummary: raw.comparison_summary.map(local), qualification: local(raw.qualification),
    evidence,
    findings: raw.findings.map(f => ({ id: f.option_id, title: local(f.title), body: local(f.body),
      qualification: local(f.qualification), decisionId: f.decision_id })) };
}

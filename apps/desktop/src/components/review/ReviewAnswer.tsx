import { useLocale } from "@/locales/LocaleProvider";
import { answerCopy, projectReviewAnswer } from "@/data/reviewAnswer";
import { reviewRows, type ReviewContextView, type ReviewInference } from "@/data/decisionReview";

export function ReviewAnswer({ answer, context, onDecision }: {
  answer: ReviewInference; context: ReviewContextView; onDecision?: (id: string) => void;
}) {
  const { locale, t, formatNumber, formatPercent } = useLocale();
  const copy = answerCopy[locale === "zh-CN" ? "zh" : "en"];
  const view = projectReviewAnswer(answer, context, locale);
  if (!view) return <p role="status" className="text-sm text-muted">{copy.unavailable}</p>;
  return <div className="space-y-6" data-review-answer="v2">
    <p className="max-w-3xl text-lg leading-relaxed text-foreground">{view.summary}</p>
    {view.comparisonSummary.map((summary, i) => <p key={i} className="max-w-3xl text-sm leading-7">{summary}</p>)}
    {view.findings.map(f => <section key={f.id} className="space-y-3 border-b border-white/10 pb-5">
      <h3 className="text-base font-medium text-foreground">{f.title}</h3>
      <p className="max-w-3xl text-sm leading-7 text-foreground/85">{f.body}</p>
      <p className="max-w-3xl text-xs leading-6 text-muted">{f.qualification}</p>
      {f.decisionId && onDecision ? <button className="text-sm text-accent hover:underline focus-visible:outline focus-visible:outline-2" onClick={() => onDecision(f.decisionId!)}>{copy.open} →</button> : null}
    </section>)}
    {answer.answer?.focus === "decision_reason" ? answer.possible_explanations.filter(h => h.kind !== "unknown").map((h, i) => <p key={i} className="max-w-3xl text-sm leading-7">{t(h.claim)}</p>) : null}
    <p className="max-w-3xl text-xs leading-6 text-muted">{view.qualification}</p>
    {view.evidence.length ? <details className="rounded-xl border border-border p-4" data-review-evidence>
      <summary className="cursor-pointer text-sm text-accent focus-visible:outline focus-visible:outline-2">{copy.evidence} · {view.evidence.length}</summary>
      <p className="mt-3 max-w-3xl text-xs leading-6 text-muted">{copy.evidenceHelp}</p>
      <div className="mt-3 max-h-[28rem] overflow-y-auto pr-2">
        {view.evidence.map(record => <details key={record.ref} className="border-t border-border py-3">
          <summary className="cursor-pointer text-sm leading-6 focus-visible:outline focus-visible:outline-2">
            {t(record.title)} <span className="text-xs text-muted">· {record.as_of?.split("T")[0]}</span>
          </summary>
          <dl className="mt-3 grid gap-x-6 gap-y-2 text-xs sm:grid-cols-[minmax(8rem,1fr)_2fr]">
            {reviewRows(record).map((row, index) => <div key={index} className="contents">
              <dt className="text-muted">{t(row.label)}</dt>
              <dd className="break-words leading-6">{row.value === null ? "—" : typeof row.value === "number"
                ? row.format === "percent" ? formatPercent(row.value, 2)
                  : row.format === "money" ? `${formatNumber(row.value, 2)} ${record.currency}` : formatNumber(row.value, 2)
                : t(row.value)}</dd>
            </div>)}
          </dl>
        </details>)}
      </div>
    </details> : null}
  </div>;
}

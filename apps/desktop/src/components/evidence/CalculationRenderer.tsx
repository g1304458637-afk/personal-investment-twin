import { ArrowRight, Check, CircleMinus, X } from "lucide-react";

import type {
  ExplainabilityInput,
  ExplainabilityTrace,
  TraceScalar,
} from "@/data/explainability";
import { useLocale } from "@/locales/LocaleProvider";

function scalarText(
  value: TraceScalar,
  unit: string,
  semanticName = "",
  role = "",
  locale = "en-US",
) {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "✓" : "—";
  if (typeof value === "string") return value;
  if (unit === "currency" || unit === "currency_per_unit") {
    return new Intl.NumberFormat(locale, { style: "currency", currency: "CNY", maximumFractionDigits: 2 }).format(value);
  }
  if (unit === "ratio" && (role === "formula_component" || semanticName.includes("turnover") || semanticName.includes("return"))) {
    return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 2 }).format(value);
  }
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(value);
}

function labelFor(input: ExplainabilityInput, t: (source: string) => string) {
  if (input.role === "execution_assumption") return t("Assumed execution price");
  const labels: Record<string, string> = {
    security_weight: "Security weight",
    daily_traded_value: "Daily traded value",
    daily_portfolio_value: "Daily portfolio value",
    daily_turnover: "Daily turnover",
    pre_trade_avg_cost: "Average cost before trade",
    execution_price: "Execution price",
    loss_state_addition_events: "Detected loss-state additions",
    eligible_add_events: "Eligible additions",
    actual_start_value: "Actual start value",
    baseline_start_value: "Baseline start value",
    actual_end_value: "Actual end value",
    baseline_end_value: "Baseline end value",
    episode_avg_exit_price: "Average execution price at exit",
    window_market_price: "Fixed-window market price",
    current_hhi: "Before trade HHI",
    post_trade_hhi: "After proposed trade HHI",
    valuation_price: "Portfolio valuation price",
    positive_n: "Positive observations",
    valid_n: "Valid observations",
    ci_lower: "Lower uncertainty bound",
    ci_upper: "Upper uncertainty bound",
  };
  return t(labels[input.semanticName] ?? input.semanticName.replaceAll("_", " "));
}

function Rows({ inputs }: { inputs: ExplainabilityInput[] }) {
  const { locale, t } = useLocale();
  return (
    <dl className="divide-y divide-border/65 border-y border-border/65">
      {inputs.map((input) => (
        <div key={input.id} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-3 text-sm">
          <dt className="min-w-0 text-muted">
            <span className="block truncate text-foreground">{labelFor(input, t)}</span>
            {typeof input.attributes.symbol === "string" ? <span className="mt-0.5 block text-xs">{input.attributes.symbol}</span> : null}
          </dt>
          <dd className="self-center font-mono font-medium tabular-nums">
            {scalarText(input.value, input.unit, input.semanticName, input.role, locale)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ResultLine({ trace }: { trace: ExplainabilityTrace }) {
  const { locale, t } = useLocale();
  const comparisons: Record<string, string> = {
    outperformed_baseline: "Actual result was above the registered baseline",
    underperformed_baseline: "Actual result was below the registered baseline",
    matched_baseline: "Actual result matched the registered baseline",
  };
  const displayed = typeof trace.result === "string"
    ? t(comparisons[trace.result] ?? trace.result)
    : scalarText(trace.result, trace.unit, trace.conceptId, "result", locale);
  return (
    <div className="mt-4 flex items-baseline justify-between gap-4 border-t border-accent/25 pt-4">
      <span className="text-sm font-medium text-muted">{t("Backend result")}</span>
      <strong className="font-mono text-xl tabular-nums">
        {displayed}
      </strong>
    </div>
  );
}

function FormulaRenderer({ trace }: { trace: ExplainabilityTrace }) {
  const { t } = useLocale();
  if (trace.conceptId === "post_exit_fixed_window_return") {
    const exit = trace.inputs.find((input) => input.semanticName === "episode_avg_exit_price");
    const market = trace.inputs.filter((input) => input.semanticName === "window_market_price");
    const first = market[0];
    const last = market.at(-1);
    return (
      <div>
        <p className="mb-3 text-sm leading-6 text-muted">{t("The fixed-window return uses market prices from the exit session through the registered endpoint. The average execution price is context only and is not the formula start.")}</p>
        <Rows inputs={[...(exit ? [exit] : []), ...(first ? [first] : []), ...(last && last !== first ? [last] : [])]} />
        <p className="mt-3 text-xs leading-5 text-muted">{t("Market-price observations in window: {count}", { count: market.length })}</p>
        <ResultLine trace={trace} />
      </div>
    );
  }
  const components = trace.inputs.filter((input) => input.role === "formula_component");
  const shown = components.length > 0 ? components : trace.inputs;
  return (
    <div>
      <Rows inputs={shown} />
      {components.length > 0 ? (
        <div className="mt-4 text-sm leading-6 text-muted">
          <p>{t("The backend operation applies the registered formula to these components.")}</p>
          <p className="mt-2 break-words font-mono text-xs text-foreground">{trace.operations.at(-1)?.formulaDisplay ?? trace.formulaDisplay}</p>
        </div>
      ) : null}
      <ResultLine trace={trace} />
      {trace.conceptId === "portfolio_concentration_hhi" ? (
        <p className="mt-3 text-xs leading-5 text-muted">{t("Each displayed weight is squared and then summed by the deterministic backend. Cash is outside these security weights.")}</p>
      ) : null}
    </div>
  );
}

function RuleRenderer({ trace }: { trace: ExplainabilityTrace }) {
  const { locale, t } = useLocale();
  const operations = trace.operations.filter((operation) => operation.kind === "strict_less_than");
  return (
    <div className="divide-y divide-border/65 border-y border-border/65">
      {operations.map((operation, index) => {
        const refs = operation.inputRefs.map((ref) => trace.inputs.find((input) => input.id === ref)).filter(Boolean) as ExplainabilityInput[];
        const price = refs.find((input) => input.semanticName === "execution_price");
        const cost = refs.find((input) => input.semanticName === "pre_trade_avg_cost");
        const detected = operation.result === true;
        return (
          <div key={operation.id} className="py-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium">{t("Observed addition {count}", { count: index + 1 })}</p>
              <span className="inline-flex items-center gap-1 text-xs text-muted">
                {detected ? <Check className="size-3.5 text-accent" /> : <CircleMinus className="size-3.5" />}
                {t(detected ? "Meets the registered rule" : "Does not meet the registered rule")}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3 text-center">
              <div><p className="text-xs text-muted">{t("Execution price")}</p><p className="mt-1 font-mono tabular-nums">{price ? scalarText(price.value, price.unit, price.semanticName, price.role, locale) : "—"}</p></div>
              <span className="text-muted">{detected ? "<" : "≥"}</span>
              <div><p className="text-xs text-muted">{t("Average cost before trade")}</p><p className="mt-1 font-mono tabular-nums">{cost ? scalarText(cost.value, cost.unit, cost.semanticName, cost.role, locale) : "—"}</p></div>
            </div>
          </div>
        );
      })}
      <ResultLine trace={trace} />
    </div>
  );
}

function ComparisonRenderer({ trace }: { trace: ExplainabilityTrace }) {
  const { t } = useLocale();
  const actual = trace.inputs.filter((input) => input.semanticName.startsWith("actual_"));
  const baseline = trace.inputs.filter((input) => input.semanticName.startsWith("baseline_"));
  return (
    <div>
      <div className="grid gap-5 sm:grid-cols-2">
        <section><h4 className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-muted">{t("Actual decision")}</h4><Rows inputs={actual} /></section>
        <section><h4 className="mb-2 text-xs font-medium uppercase tracking-[0.12em] text-muted">{t("Registered baseline")}</h4><Rows inputs={baseline} /></section>
      </div>
      <ResultLine trace={trace} />
    </div>
  );
}

function BeforeAfterRenderer({ trace }: { trace: ExplainabilityTrace }) {
  const { locale, t } = useLocale();
  const before = trace.inputs.find((input) => input.role === "before_value");
  const after = trace.inputs.find((input) => input.role === "after_value");
  const execution = trace.inputs.find((input) => input.role === "execution_assumption");
  const valuation = trace.inputs.find((input) => input.role === "mark_not_execution");
  return (
    <div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-y border-border/65 py-5 text-center">
        <div><p className="text-xs text-muted">{t("Before trade")}</p><p className="mt-2 font-mono text-xl tabular-nums">{before ? scalarText(before.value, before.unit, before.semanticName, before.role, locale) : "—"}</p></div>
        <ArrowRight className="size-4 text-accent" aria-hidden="true" />
        <div><p className="text-xs text-muted">{t("After proposed trade")}</p><p className="mt-2 font-mono text-xl tabular-nums">{after ? scalarText(after.value, after.unit, after.semanticName, after.role, locale) : "—"}</p></div>
      </div>
      <ResultLine trace={trace} />
      {(execution || valuation) ? <div className="mt-5"><Rows inputs={[...(execution ? [execution] : []), ...(valuation ? [valuation] : [])]} /><p className="mt-3 text-xs leading-5 text-muted">{t("Execution price is the assumed fill fact. Valuation price is the market mark used by portfolio replay; neither is a future price forecast.")}</p></div> : null}
    </div>
  );
}

function StatisticalRenderer({ trace }: { trace: ExplainabilityTrace }) {
  const { t } = useLocale();
  const hasInterval = trace.inputs.some((input) => input.semanticName === "ci_lower" && input.availabilityStatus === "available")
    && trace.inputs.some((input) => input.semanticName === "ci_upper" && input.availabilityStatus === "available");
  return <div><Rows inputs={trace.inputs} />{!hasInterval ? <p className="mt-3 text-xs leading-5 text-muted">{t("No uncertainty interval is available for this result.")}</p> : null}<ResultLine trace={trace} /></div>;
}

function SourceFactRenderer({ trace }: { trace: ExplainabilityTrace }) {
  const { t } = useLocale();
  return <div><Rows inputs={trace.inputs} /><p className="mt-3 text-xs leading-5 text-muted">{t("A recorded execution fact and a portfolio valuation mark have different purposes. A current mark is not an exit or sale.")}</p><ResultLine trace={trace} /></div>;
}

export function CalculationRenderer({ trace }: { trace: ExplainabilityTrace }) {
  switch (trace.traceKind) {
    case "formula_components": return <FormulaRenderer trace={trace} />;
    case "rule_observations": return <RuleRenderer trace={trace} />;
    case "comparison": return <ComparisonRenderer trace={trace} />;
    case "before_after": return <BeforeAfterRenderer trace={trace} />;
    case "statistical_summary": return <StatisticalRenderer trace={trace} />;
    case "source_fact": return <SourceFactRenderer trace={trace} />;
    default: return <p>{<X className="mr-2 inline size-4" />}{useLocale().t("Calculation details are unavailable.")}</p>;
  }
}

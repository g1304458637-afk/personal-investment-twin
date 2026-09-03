import { AlertCircle, FlaskConical, Scale } from "lucide-react";
import { useMemo, useState } from "react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { decisionCheckScenario } from "@/demo/fixture";
import { useLocale } from "@/locales/LocaleProvider";

type InputMode = "amount" | "quantity";

export function DecisionCheckPage() {
  const { formatNumber, t } = useLocale();
  const [symbol, setSymbol] = useState(decisionCheckScenario.symbol);
  const [side, setSide] = useState<"Buy" | "Sell">(decisionCheckScenario.side);
  const [inputMode, setInputMode] = useState<InputMode>(decisionCheckScenario.inputMode);
  const [value, setValue] = useState(String(decisionCheckScenario.amount));

  const fixedValue = inputMode === "amount" ? decisionCheckScenario.amount : decisionCheckScenario.quantity;
  const isFixedScenario = useMemo(
    () =>
      symbol.trim().toUpperCase() === decisionCheckScenario.symbol &&
      side === decisionCheckScenario.side &&
      Number(value) === fixedValue,
    [fixedValue, side, symbol, value],
  );

  const changeMode = (mode: InputMode) => {
    setInputMode(mode);
    setValue(String(mode === "amount" ? decisionCheckScenario.amount : decisionCheckScenario.quantity));
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("Pre-decision context")}
        title={t("Decision Check")}
        description={t("A deterministic demo scenario for reviewing evidence context before a proposed action. This interface does not provide a buy or sell recommendation.")}
      />

      <GlassPanel className="p-6">
        <SectionHeading
          eyebrow={t("Fixed demo scenario")}
          title={t("Describe the proposed action")}
          description={t("Only the registered synthetic scenario below has deterministic context. Changing an input intentionally clears the displayed result.")}
        />
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="grid gap-2 text-sm font-medium">
            {t("Symbol")}
            <Input value={symbol} onChange={(event) => setSymbol(event.target.value)} aria-label={t("Symbol")} />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            {t("Side")}
            <select
              className="h-10 rounded-md border border-border/80 bg-black/[0.08] px-3 text-sm text-foreground outline-none focus:border-accent/45 focus:ring-2 focus:ring-accent/15 dark:bg-white/[0.035]"
              value={side}
              onChange={(event) => setSide(event.target.value as "Buy" | "Sell")}
              aria-label={t("Side")}
            >
              <option value="Buy">{t("Buy")}</option>
              <option value="Sell">{t("Sell")}</option>
            </select>
          </label>
          <div className="grid gap-2 text-sm font-medium">
            {t("Input type")}
            <Tabs value={inputMode} onValueChange={(next) => changeMode(next as InputMode)}>
              <TabsList className="w-full">
                <TabsTrigger value="amount" className="flex-1">{t("Amount")}</TabsTrigger>
                <TabsTrigger value="quantity" className="flex-1">{t("Quantity")}</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <label className="grid gap-2 text-sm font-medium">
            {inputMode === "amount" ? t("Amount (CNY)") : t("Quantity")}
            <Input
              inputMode="decimal"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              aria-label={inputMode === "amount" ? t("Amount in CNY") : t("Quantity")}
            />
          </label>
        </div>
        <p className="mt-4 text-xs leading-5 text-muted">
          {t("Registered scenario: {side} {symbol} for CNY {amount} or {quantity} quantity.", {
            side: t(decisionCheckScenario.side),
            symbol: decisionCheckScenario.symbol,
            amount: formatNumber(decisionCheckScenario.amount),
            quantity: formatNumber(decisionCheckScenario.quantity),
          })}
        </p>
      </GlassPanel>

      {isFixedScenario ? (
        <GlassPanel className="overflow-hidden">
          <div className="p-6 pb-4">
            <SectionHeading
              eyebrow={t("Deterministic evidence context")}
              title={t("Registered scenario output")}
              description={t("These values are fixed synthetic fixture outputs for the exact scenario entered above.")}
            />
          </div>
          <dl className="grid border-t border-border/60 md:grid-cols-2 xl:grid-cols-3">
            {[
              ["Current", decisionCheckScenario.current],
              ["Post-trade", decisionCheckScenario.postTrade],
              ["Self baseline", decisionCheckScenario.selfBaseline],
              ["Demo peer", decisionCheckScenario.peerContext],
              ["Similar events", t("{count} registered demo events", { count: formatNumber(decisionCheckScenario.similarEvents) })],
            ].map(([label, detail]) => (
              <div key={label} className="border-b border-r border-border/60 p-5 last:border-r-0">
                <dt className="text-xs uppercase tracking-[0.1em] text-muted">{t(label)}</dt>
                <dd className="mt-2 font-medium leading-6 text-foreground">{t(detail)}</dd>
              </div>
            ))}
          </dl>
          <div className="flex items-start gap-3 p-6 text-sm leading-6 text-muted">
            <Scale className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
          <p>{t(decisionCheckScenario.limitation)}</p>
          </div>
        </GlassPanel>
      ) : (
        <StateNotice
          state="empty"
          title={t("No deterministic output for this input")}
          detail={t("This demo does not estimate or invent values for changed symbols, sides, amounts, or quantities. Return to the registered scenario to view its fixed evidence context.")}
        />
      )}

      <div className="flex items-start gap-3 rounded-md border border-border/70 bg-white/[0.025] p-4 text-sm leading-6 text-muted">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
        <p>
          <span className="font-medium text-foreground">{t("No recommendation.")}</span>{" "}
          {t("This check surfaces evidence context only; it does not tell you to buy, sell, hold, or change an order.")}
        </p>
        <FlaskConical className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
      </div>
    </div>
  );
}

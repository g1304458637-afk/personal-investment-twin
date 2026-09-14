import { useState } from "react";

import { useLocale } from "@/locales/LocaleProvider";
import { parseClampedNumberInput } from "@/lib/numberInput";

/**
 * Draft-state numeric input for the strategy workshop.  The typed value is
 * kept as a local string draft; on blur it is parsed and clamped to the
 * backend-allowed range, and invalid input falls back to the current value
 * with a visible hint.  Minimal on purpose: same control, same layout.
 */
export function WorkshopNumberInput({ value, min, max, step, title, onCommit }: {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  title?: string;
  onCommit: (next: number) => void;
}) {
  const { t } = useLocale();
  const [draft, setDraft] = useState<string | null>(null);
  const trimmed = draft === null ? "" : draft.trim();
  const invalid = draft !== null && (trimmed.length === 0 || !Number.isFinite(Number(trimmed)));
  return <>
    <input type="number" min={min} max={max} step={step} title={title}
      value={draft ?? String(value)}
      aria-invalid={invalid || undefined}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        if (draft === null) return;
        onCommit(parseClampedNumberInput(draft, value, min, max));
        setDraft(null);
      }} />
    {invalid ? <small className="workshop-num-hint" role="status">{t("Enter a valid number")}</small> : null}
  </>;
}

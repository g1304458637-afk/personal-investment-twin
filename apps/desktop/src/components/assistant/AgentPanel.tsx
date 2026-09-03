import { ArrowUp, Braces, CircleDotDashed, Sparkles } from "lucide-react";
import { useState } from "react";

import { MirrorOrb, type MirrorOrbState } from "@/components/common/MirrorOrb";
import { StateNotice } from "@/components/common/StateNotice";
import { DemoBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { selectedEpisode, selectionRecord } from "@/data/backendEvidence";
import { useLocale } from "@/locales/LocaleProvider";

export interface AgentPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AgentPanel({ open, onOpenChange }: AgentPanelProps) {
  const [orbState, setOrbState] = useState<Exclude<MirrorOrbState, "hover">>("active");
  const { t, formatPercent } = useLocale();
  const assetEpisodeTwr = typeof selectionRecord.value === "number" ? selectionRecord.value : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="agent-panel">
        <div className="agent-panel__intro">
          <DemoBadge />
          <MirrorOrb state={orbState} size="lg" />
          <div>
            <span className="eyebrow">{t("Reflect with your twin")}</span>
            <SheetTitle>{t("Ask Twin")}</SheetTitle>
            <SheetDescription>
              {t("A reserved presentation surface for evidence-grounded conversation.")}
            </SheetDescription>
          </div>
        </div>

        <StateNotice
          state="disconnected"
          title={t("Agent runtime not connected")}
          detail={t("UI Foundation v1 includes the panel boundary only. No model, tools, persistence or network request runs here.")}
        />

        <section className="agent-context" aria-labelledby="agent-context-title">
          <div className="agent-context__heading">
            <div>
              <span className="eyebrow">{t("Selected demo episode")}</span>
              <h3 id="agent-context-title">{selectedEpisode.symbol} · {t(selectedEpisode.status)}</h3>
            </div>
            <Braces aria-hidden="true" />
          </div>
          <dl>
            <div>
              <dt>{t("Position Return")}</dt>
              <dd>{formatPercent(selectedEpisode.return_value, 4)}</dd>
            </div>
            <div>
              <dt>{t("Asset Episode TWR")}</dt>
              <dd>{assetEpisodeTwr === null ? t("Not available") : formatPercent(assetEpisodeTwr, 1)}</dd>
            </div>
          </dl>
          <p>
            {t("These measure different objects. This UI does not infer why they differ.")}
          </p>
        </section>

        <section className="agent-suggestions" aria-labelledby="suggestion-title">
          <div className="agent-context__heading">
            <div>
              <span className="eyebrow">{t("Future prompts")}</span>
              <h3 id="suggestion-title">{t("Evidence-first questions")}</h3>
            </div>
            <Sparkles aria-hidden="true" />
          </div>
          <button type="button" disabled>{t("Explain the evidence available for this episode")}</button>
          <button type="button" disabled>{t("What does the synthetic benchmark comparison show?")}</button>
          <button type="button" disabled>{t("Which limitations should I keep in mind?")}</button>
        </section>

        <div className="agent-panel__spacer" />

        <div className="orb-state-preview" aria-label={t("Mirror Orb visual-state preview")}>
          <span>{t("Orb state preview")}</span>
          <div>
            {(["idle", "thinking", "active"] as const).map((state) => (
              <Button
                key={state}
                size="sm"
                variant={orbState === state ? "primary" : "ghost"}
                onClick={() => setOrbState(state)}
              >
                {state === "thinking" ? <CircleDotDashed /> : null}
                {t(state)}
              </Button>
            ))}
          </div>
        </div>

        <form className="agent-composer" onSubmit={(event) => event.preventDefault()}>
          <label htmlFor="agent-message">{t("Message your twin")}</label>
          <div>
            <textarea
              id="agent-message"
              placeholder={t("Agent transport will connect here in a later milestone…")}
              rows={2}
              disabled
            />
            <Button size="icon" variant="primary" disabled aria-label={t("Send message (not connected)")}>
              <ArrowUp />
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}

import { X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  EvidenceInspector,
  EvidenceInspectorContent,
} from "@/components/evidence/EvidenceInspector";
import { useLocale } from "@/locales/LocaleProvider";

import { useInspector } from "./InspectorContext";

function useDockedInspector() {
  const [docked, setDocked] = useState(() => window.matchMedia("(min-width: 1181px)").matches);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 1181px)");
    const update = () => setDocked(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return docked;
}

export function ContextualInspectorHost() {
  const { t } = useLocale();
  const { view, displayContext, isOpen, closeInspector } = useInspector();
  const docked = useDockedInspector();
  if (!view || !isOpen) return null;

  if (!docked) {
    return (
      <EvidenceInspector
        view={view}
        context={displayContext}
        open
        onOpenChange={(open) => !open && closeInspector()}
      />
    );
  }

  return (
    <aside className="contextual-inspector contextual-inspector--docked" aria-label={t("Contextual inspector")}>
      <button
        type="button"
        className="contextual-inspector__close"
        onClick={closeInspector}
        aria-label={t("Close panel")}
      >
        <X aria-hidden="true" />
      </button>
      <EvidenceInspectorContent view={view} context={displayContext} />
    </aside>
  );
}

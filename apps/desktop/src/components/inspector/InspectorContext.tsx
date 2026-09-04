import { createContext, useCallback, useContext, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  explainabilityForConcept,
  explainabilityForEvidence,
  pretradeExplainability,
} from "@/data/backendEvidence";
import type { ExplainabilityView } from "@/data/explainability";

import {
  parseInspectorState,
  withInspectorState,
  withoutInspectorState,
} from "./inspectorState";

export interface InspectorDisplayContext {
  readonly label?: string;
  readonly title?: string;
  readonly detail?: string;
}

interface InspectorContextValue {
  readonly view: ExplainabilityView | null;
  readonly displayContext?: InspectorDisplayContext;
  readonly isOpen: boolean;
  readonly openEvidence: (view: ExplainabilityView, context?: InspectorDisplayContext) => void;
  readonly closeInspector: () => void;
}

const InspectorContext = createContext<InspectorContextValue | null>(null);

function targetIdForView(view: ExplainabilityView): string {
  return view.evidenceId ?? view.concept.conceptId;
}

function viewForTarget(targetId: string): ExplainabilityView | null {
  const evidence = explainabilityForEvidence(targetId);
  if (evidence) return evidence;
  if (pretradeExplainability?.concept.conceptId === targetId) return pretradeExplainability;
  return explainabilityForConcept(targetId);
}

export function InspectorProvider({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const contexts = useRef(new Map<string, InspectorDisplayContext>());
  const state = parseInspectorState(location.search);
  const view = state ? viewForTarget(state.targetId) : null;

  const openEvidence = useCallback((nextView: ExplainabilityView, context?: InspectorDisplayContext) => {
    const targetId = targetIdForView(nextView);
    if (context) contexts.current.set(targetId, context);
    navigate({
      pathname: location.pathname,
      search: withInspectorState(location.search, { type: "evidence", targetId }),
    });
  }, [location.pathname, location.search, navigate]);

  const closeInspector = useCallback(() => {
    navigate({
      pathname: location.pathname,
      search: withoutInspectorState(location.search),
    }, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const value = useMemo<InspectorContextValue>(() => ({
    view,
    displayContext: state ? contexts.current.get(state.targetId) : undefined,
    isOpen: view !== null,
    openEvidence,
    closeInspector,
  }), [closeInspector, openEvidence, state, view]);

  return <InspectorContext.Provider value={value}>{children}</InspectorContext.Provider>;
}

export function useInspector() {
  const context = useContext(InspectorContext);
  if (!context) throw new Error("useInspector must be used within InspectorProvider");
  return context;
}

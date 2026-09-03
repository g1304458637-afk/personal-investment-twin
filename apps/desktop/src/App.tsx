import { MotionConfig } from "motion/react";
import { lazy, Suspense } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";

import { ThemeProvider } from "@/components/layout/ThemeProvider";
import { WorkspaceShell } from "@/components/layout/WorkspaceShell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LocaleProvider, useLocale } from "@/locales/LocaleProvider";
const OverviewPage = lazy(() => import("@/pages/OverviewPage"));
const MyTwinPage = lazy(() => import("@/pages/MyTwinPage"));
const EvidencePage = lazy(() => import("@/pages/EvidencePage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const BehaviorPage = lazy(async () => ({ default: (await import("@/pages/BehaviorPage")).BehaviorPage }));
const ComparePage = lazy(async () => ({ default: (await import("@/pages/ComparePage")).ComparePage }));
const DecisionCheckPage = lazy(async () => ({ default: (await import("@/pages/DecisionCheckPage")).DecisionCheckPage }));
const DecisionsPage = lazy(async () => ({ default: (await import("@/pages/DecisionsPage")).DecisionsPage }));

function load(page: React.ReactNode) {
  return <Suspense fallback={<RouteLoading />}>{page}</Suspense>;
}

function RouteLoading() {
  const { t } = useLocale();
  return <div className="route-loading" role="status">{t("Opening view…")}</div>;
}

export default function App() {
  return (
    <LocaleProvider>
      <ThemeProvider>
        <MotionConfig reducedMotion="user">
          <TooltipProvider delayDuration={360} skipDelayDuration={120}>
            <HashRouter>
              <Routes>
                <Route element={<WorkspaceShell />}>
                  <Route index element={<Navigate to="/overview" replace />} />
                  <Route path="/overview" element={load(<OverviewPage />)} />
                  <Route path="/my-twin" element={load(<MyTwinPage />)} />
                  <Route path="/decisions" element={load(<DecisionsPage />)} />
                  <Route path="/behavior" element={load(<BehaviorPage />)} />
                  <Route path="/compare" element={load(<ComparePage />)} />
                  <Route path="/decision-check" element={load(<DecisionCheckPage />)} />
                  <Route path="/evidence" element={load(<EvidencePage />)} />
                  <Route path="/settings" element={load(<SettingsPage />)} />
                  <Route path="*" element={<Navigate to="/overview" replace />} />
                </Route>
              </Routes>
            </HashRouter>
          </TooltipProvider>
        </MotionConfig>
      </ThemeProvider>
    </LocaleProvider>
  );
}

import { MotionConfig } from "motion/react";
import { lazy, Suspense } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ThemeProvider } from "@/components/layout/ThemeProvider";
import { WorkspaceShell } from "@/components/layout/WorkspaceShell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LocaleProvider, useLocale } from "@/locales/LocaleProvider";
import {
  legacyRoutePaths,
  productRoutes,
  resolveLegacyRedirect,
  type ProductRouteId,
} from "@/routing/productRoutes";
const OverviewPage = lazy(() => import("@/pages/OverviewHomePage"));
const InvestmentsPage = lazy(async () => ({ default: (await import("@/pages/InvestmentsPage")).InvestmentsPage }));
const ReviewPage = lazy(async () => ({ default: (await import("@/pages/ReviewPage")).ReviewPage }));
const MyTwinPage = lazy(() => import("@/pages/MyTwinPage"));
const EvidencePage = lazy(() => import("@/pages/EvidencePage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const BehaviorPage = lazy(async () => ({ default: (await import("@/pages/BehaviorPage")).BehaviorPage }));
const DecisionCheckPage = lazy(async () => ({ default: (await import("@/pages/DecisionCheckPage")).DecisionCheckPage }));
const DecisionsPage = lazy(async () => ({ default: (await import("@/pages/DecisionsPage")).DecisionsPage }));
const PositionEpisodePage = lazy(async () => ({ default: (await import("@/pages/PositionEpisodePage")).PositionEpisodePage }));

const routeElements: Partial<Record<ProductRouteId, React.ReactNode>> = {
  overview: <OverviewPage />,
  investments: <InvestmentsPage />,
  review: <ReviewPage />,
  review_decisions: <DecisionsPage />,
  review_patterns: <BehaviorPage />,
  twin: <MyTwinPage />,
  pretrade: <DecisionCheckPage />,
  settings: <SettingsPage />,
  advanced_evidence: <EvidencePage />,
  investment_episode: <PositionEpisodePage />,
};

function load(page: React.ReactNode) {
  return <Suspense fallback={<RouteLoading />}>{page}</Suspense>;
}

function RouteLoading() {
  const { t } = useLocale();
  return <div className="route-loading" role="status">{t("Opening view…")}</div>;
}

function LegacyRouteRedirect() {
  const location = useLocation();
  const target = resolveLegacyRedirect(location.pathname) ?? "/overview";
  return <Navigate to={{ pathname: target, search: location.search }} replace />;
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
                  {productRoutes.map((definition) => {
                    const element = routeElements[definition.id];
                    return element ? <Route key={definition.id} path={definition.path} element={load(element)} /> : null;
                  })}
                  {legacyRoutePaths().map((path) => (
                    <Route key={`legacy:${path}`} path={path} element={<LegacyRouteRedirect />} />
                  ))}
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

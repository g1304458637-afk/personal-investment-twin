import { MotionConfig } from "motion/react";
import { lazy, Suspense } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ThemeProvider } from "@/components/layout/ThemeProvider";
import { WorkspaceShell } from "@/components/layout/WorkspaceShell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LocaleProvider, useLocale } from "@/locales/LocaleProvider";
import { StateNotice } from "@/components/common/StateNotice";
import { DataModeProvider, useDataMode } from "@/data/DataModeProvider";
import {
  legacyRoutePaths,
  productRoutes,
  resolveLegacyRedirect,
  type ProductRouteId,
} from "@/routing/productRoutes";
const InvestmentsPage = lazy(async () => ({ default: (await import("@/pages/InvestmentsPage")).InvestmentsPage }));
const SameStockComparePage = lazy(async () => ({ default: (await import("@/pages/SameStockComparePage")).SameStockComparePage }));
const ReviewPage = lazy(async () => ({ default: (await import("@/pages/ReviewPage")).ReviewPage }));
const MyTwinPage = lazy(() => import("@/pages/MyTwinPage"));
const EvidencePage = lazy(() => import("@/pages/EvidencePage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const BehaviorPage = lazy(async () => ({ default: (await import("@/pages/BehaviorPage")).BehaviorPage }));
const DecisionCheckPage = lazy(async () => ({ default: (await import("@/pages/DecisionCheckPage")).DecisionCheckPage }));
const DecisionsPage = lazy(async () => ({ default: (await import("@/pages/DecisionsPage")).DecisionsPage }));
const PositionEpisodePage = lazy(async () => ({ default: (await import("@/pages/PositionEpisodePage")).PositionEpisodePage }));
const DataAccountsPage = lazy(async () => ({ default: (await import("@/pages/DataAccountsPage")).DataAccountsPage }));

const routeElements: Partial<Record<ProductRouteId, React.ReactNode>> = {
  overview: <Navigate to="/investments" replace />,
  investments: <InvestmentsPage />,
  same_stock_example: <SameStockComparePage />,
  review: <ReviewPage />,
  review_decisions: <DecisionsPage />,
  review_patterns: <BehaviorPage />,
  twin: <MyTwinPage />,
  pretrade: <DecisionCheckPage />,
  settings: <SettingsPage />,
  advanced_evidence: <EvidencePage />,
  investment_episode: <PositionEpisodePage />,
  data_accounts: <DataAccountsPage />,
};

function LegacyExample({ children }: { children: React.ReactNode }) {
  const data = useDataMode();
  const { t } = useLocale();
  if (data.mode !== "demo") return <StateNotice state="disconnected" title={t("This view is not connected to your account")} detail={t("Your investments and data remain available from the navigation.")} />;
  return <><p className="mb-5 border-b border-border pb-3 text-sm text-warning">{t("Standalone legacy example · not the selected account")}</p>{children}</>;
}

function load(page: React.ReactNode) {
  return <Suspense fallback={<RouteLoading />}>{page}</Suspense>;
}

function RouteLoading() {
  const { t } = useLocale();
  return <div className="route-loading" role="status">{t("Opening view…")}</div>;
}

function LegacyRouteRedirect() {
  const location = useLocation();
  const target = resolveLegacyRedirect(location.pathname) ?? "/investments";
  return <Navigate to={{ pathname: target, search: location.search }} replace />;
}

export default function App() {
  return (
    <LocaleProvider>
      <DataModeProvider><ThemeProvider>
        <MotionConfig reducedMotion="user">
          <TooltipProvider delayDuration={360} skipDelayDuration={120}>
            <HashRouter>
              <Routes>
                <Route element={<WorkspaceShell />}>
                  <Route index element={<Navigate to="/investments" replace />} />
                  {productRoutes.map((definition) => {
                    const element = routeElements[definition.id];
                    return element ? <Route key={definition.id} path={definition.path} element={load(["review", "review_decisions", "review_patterns", "twin", "pretrade", "advanced_evidence"].includes(definition.id) ? <LegacyExample>{element}</LegacyExample> : element)} /> : null;
                  })}
                  {legacyRoutePaths().map((path) => (
                    <Route key={`legacy:${path}`} path={path} element={<LegacyRouteRedirect />} />
                  ))}
                  <Route path="*" element={<Navigate to="/investments" replace />} />
                </Route>
              </Routes>
            </HashRouter>
          </TooltipProvider>
        </MotionConfig>
      </ThemeProvider></DataModeProvider>
    </LocaleProvider>
  );
}

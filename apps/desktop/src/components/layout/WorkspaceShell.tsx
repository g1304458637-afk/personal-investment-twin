import { AnimatePresence, motion } from "motion/react";
import { Command, MoonStar, SunMedium } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { AgentPanel } from "@/components/assistant/AgentPanel";
import { MirrorOrb } from "@/components/common/MirrorOrb";
import { DemoBadge } from "@/components/common/StatusBadge";
import { ContextualInspectorHost } from "@/components/inspector/ContextualInspectorHost";
import { InspectorProvider } from "@/components/inspector/InspectorContext";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { demoUser } from "@/demo/fixture";
import { cn } from "@/lib/utils";
import { useLocale } from "@/locales/LocaleProvider";
import {
  activeNavigationGroup,
  activeNavigationRouteId,
  pageTitleKey,
} from "@/routing/productRoutes";

import { CommandPalette } from "./CommandPalette";
import { navigationItems, type NavigationRouteItem } from "./navigation";
import { useTheme } from "./ThemeProvider";

function WorkspaceShellContent() {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const { t } = useLocale();
  const [agentOpen, setAgentOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const currentRouteId = activeNavigationRouteId(location.pathname);
  const currentGroup = activeNavigationGroup(location.pathname);
  const title = t(pageTitleKey(location.pathname));
  const nextTheme = theme === "dark" ? "light" : "dark";

  const navigationLink = (item: NavigationRouteItem, child = false) => {
    const Icon = item.icon;
    const isActive = currentRouteId === item.id;
    return (
      <Tooltip key={item.path} delayDuration={480}>
        <TooltipTrigger asChild>
          <NavLink
            to={item.path}
            className={cn(
              "workspace-nav__item",
              child && "workspace-nav__item--child",
              isActive && "workspace-nav__item--active",
            )}
          >
            {isActive ? (
              <motion.span
                layoutId="workspace-route-indicator"
                className="workspace-nav__indicator"
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
              />
            ) : null}
            <Icon aria-hidden="true" />
            <span>{t(item.label)}</span>
          </NavLink>
        </TooltipTrigger>
        <TooltipContent side="right" className="max-w-52">
          {t(item.description)}
        </TooltipContent>
      </Tooltip>
    );
  };

  return (
    <div className="workspace-shell">
      <div className="ambient-light ambient-light--one" aria-hidden="true" />
      <div className="ambient-light ambient-light--two" aria-hidden="true" />

      <aside className="workspace-sidebar" aria-label={t("Primary navigation")}>
        <div className="workspace-brand" data-tauri-drag-region>
          <MirrorOrb size="sm" />
          <div>
            <strong>投镜</strong>
            <span>{t("Investment Twin")}</span>
          </div>
        </div>

        <nav className="workspace-nav">
          <span className="workspace-nav__label">{t("Work")}</span>
          {navigationItems.map((item) => {
            if (item.type === "route") {
              return (
                <div key={item.id} className={cn(item.section === "manage" && "workspace-nav__manage")}>
                  {item.section === "manage" ? <span className="workspace-nav__label">{t("Manage")}</span> : null}
                  {navigationLink(item)}
                </div>
              );
            }
            const GroupIcon = item.icon;
            return (
              <div key={item.id} className="workspace-nav__group" role="group" aria-label={t(item.label)}>
                <div className={cn("workspace-nav__group-title", currentGroup === item.id && "workspace-nav__group-title--active")}>
                  <GroupIcon aria-hidden="true" />
                  <span>{t(item.label)}</span>
                </div>
                <div className="workspace-nav__children">
                  {item.children.map((child) => navigationLink(child, true))}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="workspace-sidebar__footer">
          <DemoBadge />
          <p>{t("Offline fixture · {tier}", { tier: t(demoUser.dataTier) })}</p>
          <span>ui-demo-v1</span>
        </div>
      </aside>

      <div className="workspace-main">
        <header className="workspace-topbar">
          <div className="workspace-topbar__drag-region" data-tauri-drag-region>
            <span>{t("Workspace")}</span>
            <strong>{title}</strong>
          </div>
          <div className="workspace-topbar__actions">
            <button
              type="button"
              className="command-trigger"
              onClick={() => setCommandOpen(true)}
              aria-label={t("Open workspace command palette")}
            >
              <Command aria-hidden="true" />
              <span>{t("Navigate")}</span>
              <kbd>⌘ K</kbd>
            </button>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={toggleTheme}
                  aria-label={t("Switch to {theme} mode", { theme: t(nextTheme) })}
                >
                  {theme === "dark" ? <SunMedium /> : <MoonStar />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t("Switch to {theme} mode", { theme: t(nextTheme) })}</TooltipContent>
            </Tooltip>
            <Button className="ask-twin-button" variant="primary" onClick={() => setAgentOpen(true)}>
              <span>{t("Ask Twin")}</span>
              <MirrorOrb size="sm" state="active" />
            </Button>
          </div>
        </header>

        <main className="workspace-content" id="workspace-content">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              className="route-frame"
              initial={{ opacity: 0, y: 7 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              <Outlet context={{ openAgent: () => setAgentOpen(true) }} />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <ContextualInspectorHost />
      <AgentPanel open={agentOpen} onOpenChange={setAgentOpen} />
      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}

export function WorkspaceShell() {
  return (
    <InspectorProvider>
      <WorkspaceShellContent />
    </InspectorProvider>
  );
}

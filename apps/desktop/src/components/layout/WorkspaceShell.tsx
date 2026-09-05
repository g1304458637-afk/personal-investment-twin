import { AnimatePresence, motion } from "motion/react";
import { Command, MoonStar, SunMedium } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { MirrorOrb } from "@/components/common/MirrorOrb";
import { ContextualInspectorHost } from "@/components/inspector/ContextualInspectorHost";
import { InspectorProvider } from "@/components/inspector/InspectorContext";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDataMode } from "@/data/DataModeProvider";
import { cn } from "@/lib/utils";
import { useLocale } from "@/locales/LocaleProvider";
import {
  activeNavigationGroup,
  activeNavigationRouteId,
  activeRouteId,
  pageTitleKey,
} from "@/routing/productRoutes";

import { CommandPalette } from "./CommandPalette";
import { navigationItems, type NavigationRouteItem } from "./navigation";
import { useTheme } from "./ThemeProvider";
import { IntelligenceShell } from "@/workspace/IntelligenceShell";
import { isClassicWorkspace } from "@/workspace/workspaceMode";

function WorkspaceShellContent() {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const { t } = useLocale();
  const [commandOpen, setCommandOpen] = useState(false);
  const data = useDataMode();
  const currentRouteId = activeNavigationRouteId(location.pathname);
  const exactRouteId = activeRouteId(location.pathname);
  const currentGroup = activeNavigationGroup(location.pathname);
  const title = t(pageTitleKey(location.pathname));
  const nextTheme = theme === "dark" ? "light" : "dark";

  const navigationLink = (item: NavigationRouteItem, child = false) => {
    const Icon = item.icon;
    const isActive = child ? exactRouteId === item.id : currentRouteId === item.id;
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

  if (!isClassicWorkspace()) return <><IntelligenceShell openCommands={() => setCommandOpen(true)} /><CommandPalette open={commandOpen} onOpenChange={setCommandOpen} /></>;

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

        <div className="px-4 pb-5">
          <label htmlFor="account-context" className="mb-2 block text-[11px] text-muted">{t("Current account")}</label>
          <select id="account-context" className="w-full min-w-0 rounded-md border border-border bg-background px-2 py-2 text-xs text-foreground"
            value={data.mode === "demo" ? `example:${data.exampleAccount.key}` : data.activeAccount ? `real:${JSON.stringify([data.activeAccount.subject_id, data.activeAccount.account_id])}` : "none"}
            onChange={(event) => {
              const value = event.target.value;
              if (value.startsWith("example:")) {
                const account = data.examples.find((item) => `example:${item.key}` === value);
                if (account) { data.setExampleAccount(account); data.setMode("demo"); }
              } else {
                const account = data.accounts.find((item) => `real:${JSON.stringify([item.subject_id, item.account_id])}` === value);
                data.setActiveAccount(account ?? null); data.setMode("real_user");
              }
            }}>
            {!data.accounts.length ? <option value="none">{t("My account · not imported")}</option> : null}
            {data.accounts.map((account) => <option key={JSON.stringify([account.subject_id, account.account_id])} value={`real:${JSON.stringify([account.subject_id, account.account_id])}`}>{account.display_name}</option>)}
            <optgroup label={t("Example accounts · Synthetic")}>
              {data.examples.map((account) => <option key={account.key} value={`example:${account.key}`}>{t(account.label)}</option>)}
            </optgroup>
          </select>
        </div>

        <nav className="workspace-nav">
          <span className="workspace-nav__label">{t("Work")}</span>
          {navigationItems.map((item, index) => {
            if (item.type === "route") {
              return (
                <div key={item.id} className={cn(item.section === "manage" && "workspace-nav__manage")}>
                  {item.section === "manage" && navigationItems[index - 1]?.section !== "manage" ? <span className="workspace-nav__label">{t("Manage")}</span> : null}
                  {navigationLink(item)}
                </div>
              );
            }
            const GroupIcon = item.icon;
            return (
              <div key={item.id} className="workspace-nav__group" role="group" aria-label={t(item.label)}>
                <NavLink
                  to={item.path}
                  className={cn("workspace-nav__group-title", currentGroup === item.id && "workspace-nav__group-title--active")}
                >
                  <GroupIcon aria-hidden="true" />
                  <span>{t(item.label)}</span>
                </NavLink>
                <div className="workspace-nav__children">
                  {item.children.map((child) => navigationLink(child, true))}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="workspace-sidebar__footer">
          <strong className="text-xs text-foreground">{t(data.mode === "demo" ? "Example account · Synthetic" : data.activeAccount ? "Real account · Local" : "No account")}</strong>
          <p>{data.mode === "demo" ? t(data.exampleAccount.label) : data.activeAccount?.display_name ?? t("Import data to begin")}</p>
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
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <ContextualInspectorHost />
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

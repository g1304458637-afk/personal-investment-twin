import {
  Activity,
  BetweenHorizontalStart,
  BookOpenText,
  BrainCircuit,
  BriefcaseBusiness,
  Database,
  History,
  LayoutDashboard,
  ScanSearch,
  Settings2,
  type LucideIcon,
} from "lucide-react";

import {
  getSidebarNavigation,
  type NavigationGroupId,
  type NavigationSection,
  type ProductIconKey,
  type ProductRouteId,
} from "@/routing/productRoutes";

export interface NavigationRouteItem {
  readonly type: "route";
  readonly id: ProductRouteId;
  readonly label: string;
  readonly path: string;
  readonly icon: LucideIcon;
  readonly description: string;
  readonly section: NavigationSection;
}

export interface NavigationGroupItem {
  readonly type: "group";
  readonly id: NavigationGroupId;
  readonly label: string;
  readonly icon: LucideIcon;
  readonly path: string;
  readonly description: string;
  readonly section: NavigationSection;
  readonly children: readonly NavigationRouteItem[];
}

export type NavigationItem = NavigationRouteItem | NavigationGroupItem;

const icons: Readonly<Record<ProductIconKey, LucideIcon>> = {
  overview: LayoutDashboard,
  investments: BriefcaseBusiness,
  review: History,
  twin: BrainCircuit,
  pretrade: ScanSearch,
  data: Database,
  settings: Settings2,
  evidence: BookOpenText,
  episode: BetweenHorizontalStart,
};

export const navigationItems: readonly NavigationItem[] = getSidebarNavigation().map((entry) => {
  if (entry.type === "route") {
    return {
      type: "route",
      id: entry.route.id,
      label: entry.route.labelKey,
      path: entry.route.path,
      icon: icons[entry.route.icon],
      description: entry.route.descriptionKey,
      section: entry.route.navigationSection ?? "work",
    };
  }
  return {
    type: "group",
    id: entry.id,
    label: entry.labelKey,
    icon: icons[entry.icon],
    path: entry.route.path,
    description: entry.route.descriptionKey,
    section: entry.navigationSection,
    children: entry.children.map((child) => ({
      type: "route",
      id: child.id,
      label: child.labelKey,
      path: child.path,
      icon: child.id === "review_decisions" ? BetweenHorizontalStart : Activity,
      description: child.descriptionKey,
      section: child.navigationSection ?? "work",
    })),
  };
});

export const commandNavigationItems: readonly NavigationRouteItem[] = navigationItems.flatMap(
  (item) => item.type === "route" ? [item] : [
    {
      type: "route",
      id: item.id,
      label: item.label,
      path: item.path,
      icon: item.icon,
      description: item.description,
      section: item.section,
    },
    ...item.children,
  ],
);

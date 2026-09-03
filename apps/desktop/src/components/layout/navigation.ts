import {
  Activity,
  BetweenHorizontalStart,
  BookOpenText,
  BrainCircuit,
  LayoutDashboard,
  Scale,
  ScanSearch,
  Settings2,
  type LucideIcon,
} from "lucide-react";

export interface NavigationItem {
  label: string;
  shortLabel: string;
  path: string;
  icon: LucideIcon;
  description: string;
}

export const navigationItems: NavigationItem[] = [
  {
    label: "Overview",
    shortLabel: "Overview",
    path: "/overview",
    icon: LayoutDashboard,
    description: "Portfolio and evidence at a glance",
  },
  {
    label: "My Twin",
    shortLabel: "Twin",
    path: "/my-twin",
    icon: BrainCircuit,
    description: "Demo twin snapshots over time",
  },
  {
    label: "Decisions",
    shortLabel: "Decisions",
    path: "/decisions",
    icon: BetweenHorizontalStart,
    description: "Selection, sizing, exit and friction evidence",
  },
  {
    label: "Behavior",
    shortLabel: "Behavior",
    path: "/behavior",
    icon: Activity,
    description: "Descriptive portfolio behavior evidence",
  },
  {
    label: "Compare",
    shortLabel: "Compare",
    path: "/compare",
    icon: Scale,
    description: "Self, past and authorized comparison surfaces",
  },
  {
    label: "Decision Check",
    shortLabel: "Check",
    path: "/decision-check",
    icon: ScanSearch,
    description: "Pre-decision evidence context preview",
  },
  {
    label: "Evidence",
    shortLabel: "Evidence",
    path: "/evidence",
    icon: BookOpenText,
    description: "Search and inspect evidence provenance",
  },
  {
    label: "Settings",
    shortLabel: "Settings",
    path: "/settings",
    icon: Settings2,
    description: "Appearance, privacy and permissions UI",
  },
];

export const navigationTitle = Object.fromEntries(
  navigationItems.map((item) => [item.path, item.label]),
);

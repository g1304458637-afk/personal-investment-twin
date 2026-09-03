import { forwardRef, type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type GlassTone = "primary" | "floating" | "quiet" | "overlay";

interface GlassPanelProps extends HTMLAttributes<HTMLElement> {
  as?: "section" | "article" | "div";
  tone?: GlassTone;
}

export const GlassPanel = forwardRef<HTMLElement, GlassPanelProps>(
  ({ as: Component = "section", tone = "primary", className, ...props }, ref) => (
    <Component
      ref={ref as never}
      className={cn("glass-panel", `glass-panel--${tone}`, className)}
      {...props}
    />
  ),
);
GlassPanel.displayName = "GlassPanel";

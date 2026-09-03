import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function MetricRail({
  items,
  className,
}: {
  items: Array<{
    label: string;
    value: ReactNode;
    detail?: string;
    tone?: "positive" | "negative" | "neutral";
  }>;
  className?: string;
}) {
  return (
    <dl className={cn("metric-rail", className)}>
      {items.map((item) => (
        <div key={item.label} className="metric-rail__item" data-tone={item.tone ?? "neutral"}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
          {item.detail ? <span>{item.detail}</span> : null}
        </div>
      ))}
    </dl>
  );
}

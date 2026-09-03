import { CircleCheck, CircleDashed, FlaskConical, ShieldQuestion } from "lucide-react";

import type { EvidenceStatus } from "@/demo/types";
import { statusLabel } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useLocale } from "@/locales/LocaleProvider";

const statusIcon = {
  complete: CircleCheck,
  partial: CircleDashed,
  insufficient_evidence: ShieldQuestion,
  experimental: FlaskConical,
};

export function StatusBadge({
  status,
  compact = false,
  className,
}: {
  status: EvidenceStatus;
  compact?: boolean;
  className?: string;
}) {
  const Icon = statusIcon[status];
  const { t } = useLocale();

  return (
    <span
      className={cn("status-badge", compact && "status-badge--compact", className)}
      data-status={status}
    >
      <Icon aria-hidden="true" />
      {t(statusLabel[status])}
    </span>
  );
}

export function DemoBadge({ compact = false }: { compact?: boolean }) {
  const { t } = useLocale();
  return (
    <span className={cn("demo-badge", compact && "demo-badge--compact")}>
      <FlaskConical aria-hidden="true" />
      {t(compact ? "Demo" : "Demo · Synthetic")}
    </span>
  );
}

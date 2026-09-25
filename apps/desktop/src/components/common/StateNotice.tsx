import {
  AlertTriangle,
  CircleDashed,
  CloudOff,
  DatabaseZap,
  FlaskConical,
  LoaderCircle,
} from "lucide-react";

import { useLocale } from "@/locales/LocaleProvider";
import { cn } from "@/lib/utils";

const icons = {
  loading: LoaderCircle,
  empty: DatabaseZap,
  insufficient: CircleDashed,
  error: AlertTriangle,
  demo: FlaskConical,
  disconnected: CloudOff,
};

export function StateNotice({
  state,
  title,
  detail,
  compact = false,
  onRetry,
}: {
  state: keyof typeof icons;
  title: string;
  detail: string;
  compact?: boolean;
  /** Renders a retry action on error states (e.g. after a sidecar timeout). */
  onRetry?: () => void;
}) {
  const Icon = icons[state];

  return (
    <div className={cn("state-notice", compact && "state-notice--compact")} data-state={state} role={state === "error" || state === "disconnected" ? "alert" : "status"} aria-live={state === "error" || state === "disconnected" ? "assertive" : "polite"}>
      <span className="state-notice__icon">
        <Icon aria-hidden="true" className={state === "loading" ? "animate-spin" : undefined} />
      </span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
        {onRetry && (state === "error" || state === "disconnected") ? <RetryButton onRetry={onRetry} /> : null}
      </div>
    </div>
  );
}

function RetryButton({ onRetry }: { onRetry: () => void }) {
  const { t } = useLocale();
  return (
    <button type="button" className="state-notice__retry underline underline-offset-2" onClick={onRetry}>
      {t("Retry")}
    </button>
  );
}

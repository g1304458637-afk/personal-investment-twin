import {
  AlertTriangle,
  CircleDashed,
  CloudOff,
  DatabaseZap,
  FlaskConical,
  LoaderCircle,
} from "lucide-react";

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
}: {
  state: keyof typeof icons;
  title: string;
  detail: string;
  compact?: boolean;
}) {
  const Icon = icons[state];

  return (
    <div className={cn("state-notice", compact && "state-notice--compact")} data-state={state}>
      <span className="state-notice__icon">
        <Icon aria-hidden="true" className={state === "loading" ? "animate-spin" : undefined} />
      </span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
    </div>
  );
}

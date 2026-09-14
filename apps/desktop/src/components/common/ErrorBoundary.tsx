import { Component, type ReactNode } from "react";

import { StateNotice } from "@/components/common/StateNotice";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/locales/LocaleProvider";

interface BoundaryProps {
  children: ReactNode;
  title: string;
  detail: string;
  reloadLabel: string;
}

/**
 * Top-level fail-safe: an unexpected render error must never leave a blank
 * window.  The boundary shows a styled, bilingual notice with a reload
 * action; it holds no financial data — every number on screen comes from
 * the fail-closed backend adapters, and this UI only says the view itself
 * failed.
 */
class AppErrorBoundaryClass extends Component<BoundaryProps, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  componentDidCatch(error: unknown) {
    console.error("Unhandled render error", error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return <div role="alert" className="iw-inset app-error-boundary">
      <StateNotice state="error" title={this.props.title} detail={this.props.detail} />
      <p className="app-error-boundary__message">{this.state.error.message}</p>
      <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
        {this.props.reloadLabel}
      </Button>
    </div>;
  }
}

export function AppErrorBoundary({ children }: { children: ReactNode }) {
  const { t } = useLocale();
  return <AppErrorBoundaryClass
    title={t("Something went wrong")}
    detail={t("This view hit an unexpected error. Your recorded data is not affected.")}
    reloadLabel={t("Reload")}>
    {children}
  </AppErrorBoundaryClass>;
}

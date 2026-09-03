import { LockKeyhole, Send, ShieldCheck } from "lucide-react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { notableChanges } from "@/demo/fixture";
import { useLocale } from "@/locales/LocaleProvider";

export function ComparePage() {
  const { t } = useLocale();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={t("Comparison surfaces")}
        title={t("Compare evidence context")}
        description={t("Compare your synthetic demo evidence across time, against a defined cohort, or through an explicitly authorized invitation.")}
      />

      <Tabs defaultValue="past" className="w-full">
        <TabsList aria-label={t("Comparison mode")} className="flex h-auto w-full flex-wrap justify-start gap-1">
          <TabsTrigger value="past">{t("Self vs Past")}</TabsTrigger>
          <TabsTrigger value="peer">{t("Self vs Peer")}</TabsTrigger>
          <TabsTrigger value="user">{t("User vs User")}</TabsTrigger>
        </TabsList>

        <TabsContent value="past">
          <GlassPanel className="p-6">
            <SectionHeading
              eyebrow={t("Demo User · deterministic history")}
              title={t("Self vs Past")}
              description={t("A temporal comparison of registered demo observations. This view is descriptive and does not predict an outcome.")}
            />
            <dl className="mt-6 divide-y divide-border/60 rounded-md border border-border/70">
              {notableChanges.map((change) => (
                <div key={change.label} className="grid gap-2 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                  <div>
                    <dt className="font-medium">{t(change.label)}</dt>
                    <dd className="mt-1 text-sm leading-5 text-muted">{t(change.detail)}</dd>
                  </div>
                  <dd className="font-semibold tabular-nums text-foreground">{t(change.value)}</dd>
                </div>
              ))}
            </dl>
          </GlassPanel>
        </TabsContent>

        <TabsContent value="peer">
          <GlassPanel className="p-6">
            <SectionHeading
              eyebrow={t("Demo Cohort · Synthetic")}
              title={t("Self vs Peer")}
              description={t("The Peer view uses the defined synthetic Demo Cohort as distributional context. It does not identify or disclose any participant.")}
            />
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {[
                ["Reference", "P25 · median · P75"],
                ["Subject", "Demo User"],
                ["Boundary", "N=72 · synthetic only"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border border-border/70 bg-white/[0.025] p-4">
                  <span className="text-xs uppercase tracking-[0.1em] text-muted">{t(label)}</span>
                  <p className="mt-2 font-medium">{t(value)}</p>
                </div>
              ))}
            </div>
          </GlassPanel>
        </TabsContent>

        <TabsContent value="user">
          <GlassPanel className="p-6">
            <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
              <div className="max-w-2xl">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <LockKeyhole className="size-4 text-accent" aria-hidden="true" />
                  {t("Permission required")}
                </div>
                <SectionHeading
                  eyebrow={t("Private comparison")}
                  title={t("User vs User")}
                  description={t("An invitation establishes whether a limited evidence comparison may be shown. No private information is visible before consent.")}
                />
              </div>
              <Button type="button" variant="primary" disabled aria-label={t("Create invite (not connected in this demo)")}>
                <Send aria-hidden="true" />
                {t("Invite not connected")}
              </Button>
            </div>
            <div className="mt-6 grid gap-3 md:grid-cols-3">
              {[
                ["1", "Invite", "Create a consent-bound invitation."],
                ["2", "Awaiting response", "The invite is pending; no comparison is available."],
                ["3", "Authorized", "Only the agreed comparison summary can appear."],
              ].map(([step, label, detail]) => (
                <div key={step} className="rounded-md border border-border/70 bg-white/[0.025] p-4">
                  <span className="text-xs font-semibold text-accent">{step}</span>
                  <h3 className="mt-2 font-medium">{t(label)}</h3>
                  <p className="mt-1 text-sm leading-5 text-muted">{t(detail)}</p>
                </div>
              ))}
            </div>
            <StateNotice
              state="empty"
              compact
              title={t("No authorized comparison selected")}
              detail={t("A connected consent service would be required before an invitation or shared evidence summary could exist. This demo creates neither.")}
            />
            <div className="mt-5 flex items-center gap-2 text-xs leading-5 text-muted">
              <ShieldCheck className="size-4 shrink-0 text-accent" aria-hidden="true" />
              {t("Permission status is the only state shown here until an invite is accepted.")}
            </div>
          </GlassPanel>
        </TabsContent>
      </Tabs>
    </div>
  );
}

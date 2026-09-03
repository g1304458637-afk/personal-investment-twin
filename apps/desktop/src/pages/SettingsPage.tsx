import { Database, GitCompareArrows, Info, Languages, LockKeyhole, Palette, UsersRound } from "lucide-react";
import { useState } from "react";

import { GlassPanel } from "@/components/common/GlassPanel";
import { PageHeader, SectionHeading } from "@/components/common/PageHeader";
import { StateNotice } from "@/components/common/StateNotice";
import { DemoBadge } from "@/components/common/StatusBadge";
import { Switch } from "@/components/ui/switch";
import { demoUser, uiStateExamples } from "@/demo/fixture";
import { useTheme, type Theme } from "@/components/layout/ThemeProvider";
import { useLocale, type Locale } from "@/locales/LocaleProvider";

const localeOptions: ReadonlyArray<{ value: Locale; label: string }> = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en-US", label: "English" },
];

const settingStates = {
  loading: "Reviewing fixture configuration…",
  empty: "No authorized preference profile is available.",
  insufficient: "A setting remains unavailable until its evidence boundary is met.",
  error: "A fixture configuration could not be validated.",
  demo: "Synthetic offline settings are shown in this workspace.",
  disconnected: "Remote services are not connected in v1.",
} as const;

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { locale, setLocale, t } = useLocale();
  const [privacyMode, setPrivacyMode] = useState(true);
  const [peerParticipation, setPeerParticipation] = useState(false);
  const [comparePermission, setComparePermission] = useState(false);
  const [consentVisible, setConsentVisible] = useState(false);

  return (
    <div className="space-y-8">
      <PageHeader eyebrow={t("Workspace settings")} title={t("Preferences with clear boundaries")} description={t("Controls shown here are a UI demonstration. They do not write to an account, device or remote service.")} actions={<DemoBadge />} />

      <div className="grid gap-5 xl:grid-cols-2">
        <SettingsSection icon={Languages} eyebrow={t("Language")} title={t("Interface language")} detail={t("Choose the language used throughout this workspace.")}>
          <div className="flex rounded-md border border-border/80 p-1" role="group" aria-label={t("Language preference")}>
            {localeOptions.map((option) => <button key={option.value} type="button" lang={option.value} onClick={() => setLocale(option.value)} className={`min-w-0 flex-1 rounded-sm px-3 py-2 text-sm transition-colors ${locale === option.value ? "bg-accent/15 text-foreground" : "text-muted hover:text-foreground"}`}>{option.label}</button>)}
          </div>
        </SettingsSection>

        <SettingsSection icon={Palette} eyebrow={t("Appearance")} title={t("Theme")} detail={t("Choose the local visual mode for this session.")}>
          <div className="flex rounded-md border border-border/80 p-1" role="group" aria-label={t("Theme preference")}>{(["dark", "light"] as Theme[]).map((option) => <button key={option} type="button" onClick={() => setTheme(option)} className={`min-w-0 flex-1 rounded-sm px-3 py-2 text-sm transition-colors ${theme === option ? "bg-accent/15 text-foreground" : "text-muted hover:text-foreground"}`}>{t(option === "dark" ? "Dark" : "Light")}</button>)}</div>
        </SettingsSection>

        <SettingsSection icon={LockKeyhole} eyebrow={t("Privacy")} title={t("Privacy mode")} detail={t("Keeps the workspace in its most restrictive presentation mode.")}>
          <ToggleRow label={t("Privacy mode")} detail={t("UI-only preference; it does not change data handling.")} checked={privacyMode} onCheckedChange={setPrivacyMode} />
        </SettingsSection>

        <SettingsSection icon={Database} eyebrow={t("Data")} title={t("Data connection")} detail={t("This demo is deliberately offline and deterministic.")}>
          <StateNotice state="demo" title={t("Demo / Synthetic fixture")} detail={t("ui-demo-v1 · no market, brokerage or account data is connected.")} compact />
          <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-4 text-sm"><span className="text-muted">{t("Profile")}</span><span>{t(demoUser.displayName)} · {t("Synthetic tier")}</span></div>
        </SettingsSection>

        <SettingsSection icon={UsersRound} eyebrow={t("Peer participation")} title={t("Cohort contribution")} detail={t("Participation is presented as a future consent surface.")}>
          <ToggleRow label={t("Include anonymized observations")} detail={t("UI only — no consent is stored or transmitted.")} checked={peerParticipation} onCheckedChange={setPeerParticipation} />
          <button type="button" className="mt-3 text-xs text-accent underline-offset-4 hover:underline" onClick={() => setConsentVisible((visible) => !visible)}>{t(consentVisible ? "Hide consent boundary" : "Review consent boundary")}</button>
          {consentVisible ? <p className="mt-2 rounded-md border border-border/70 bg-white/[0.025] p-3 text-xs leading-5 text-muted">{t("This control is illustrative only. It does not create, withdraw or persist consent, and no peer data is shared from this demo workspace.")}</p> : null}
        </SettingsSection>

        <SettingsSection icon={GitCompareArrows} eyebrow={t("Compare permissions")} title={t("Comparison access")} detail={t("Comparison features remain intentionally disconnected.")}>
          <ToggleRow label={t("Permit comparison context")} detail={t("UI only — no peer cohort is queried or exposed.")} checked={comparePermission} onCheckedChange={setComparePermission} />
          <div className="mt-4"><StateNotice state="disconnected" title={t("Comparison service unavailable")} detail={t("No remote cohort connection exists in v1.")} compact /></div>
        </SettingsSection>

        <SettingsSection icon={Info} eyebrow={t("About")} title={t("Methodology")} detail={t("A concise contract for interpreting this interface.")}>
          <ul className="space-y-2 text-sm leading-5 text-muted"><li>{t("Evidence is descriptive, method-bound and traceable to provenance.")}</li><li>{t("Missing values remain missing; the interface does not infer them.")}</li><li>{t("Demo data is synthetic and never represents a real account or market history.")}</li></ul>
        </SettingsSection>
      </div>

      <GlassPanel className="p-5"><SectionHeading eyebrow={t("State coverage")} title={t("Explicit system states")} description={t("Reference presentations used when data or services are unavailable. These are not live operational status messages.")} /><div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{uiStateExamples.map((example) => <StateNotice key={example.id} state={example.id as keyof typeof settingStates} title={t(example.label)} detail={t(settingStates[example.id as keyof typeof settingStates])} compact />)}</div></GlassPanel>
    </div>
  );
}

function SettingsSection({ icon: Icon, eyebrow, title, detail, children }: { icon: typeof Palette; eyebrow: string; title: string; detail: string; children: React.ReactNode }) {
  return <GlassPanel className="p-5"><div className="flex gap-3"><span className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border/70 bg-white/[0.04] text-accent"><Icon className="size-4" /></span><div><span className="eyebrow">{eyebrow}</span><h2 className="mt-1 text-[15px] font-semibold">{title}</h2><p className="mt-1 text-sm leading-5 text-muted">{detail}</p></div></div><div className="mt-5">{children}</div></GlassPanel>;
}

function ToggleRow({ label, detail, checked, onCheckedChange }: { label: string; detail: string; checked: boolean; onCheckedChange: (checked: boolean) => void }) {
  return <div className="flex items-start justify-between gap-4"><div><p className="text-sm font-medium">{label}</p><p className="mt-1 text-xs leading-5 text-muted">{detail}</p></div><Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={label} /></div>;
}

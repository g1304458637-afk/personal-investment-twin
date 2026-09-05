import { PageHeader } from "@/components/common/PageHeader";
import { useTheme, type Theme } from "@/components/layout/ThemeProvider";
import { useLocale, type Locale } from "@/locales/LocaleProvider";

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { locale, setLocale, t } = useLocale();
  return <div className="space-y-8 max-w-3xl">
    <PageHeader showDemo={false} title={t("Settings")} description={t("Display preferences are saved on this device.")} />
    <section className="border-y border-border py-6">
      <h2 className="text-sm font-semibold">{t("Interface language")}</h2>
      <div className="mt-4 flex gap-2" role="group" aria-label={t("Language preference")}>
        {([{value: "zh-CN", label: "简体中文"}, {value: "en-US", label: "English"}] as {value: Locale; label: string}[]).map(({value, label}) => <button key={value} aria-pressed={locale === value} lang={value} onClick={() => setLocale(value)} className={`rounded-md border px-5 py-2 text-sm ${locale === value ? "border-accent bg-accent/10" : "border-border text-muted"}`}>{label}</button>)}
      </div>
    </section>
    <section className="border-b border-border pb-6">
      <h2 className="text-sm font-semibold">{t("Theme")}</h2>
      <div className="mt-4 flex gap-2" role="group" aria-label={t("Theme preference")}>
        {(["dark", "light"] as Theme[]).map((value) => <button key={value} aria-pressed={theme === value} onClick={() => setTheme(value)} className={`rounded-md border px-5 py-2 text-sm ${theme === value ? "border-accent bg-accent/10" : "border-border text-muted"}`}>{t(value === "dark" ? "Dark" : "Light")}</button>)}
      </div>
    </section>
  </div>;
}

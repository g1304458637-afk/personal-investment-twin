import { Moon, Sun, ShieldCheck } from "lucide-react";
import { useTheme } from "@/components/layout/ThemeProvider";
import { useLocale, type Locale } from "@/locales/LocaleProvider";
import { useLiquidCopy } from "./liquidCopy";
import { useWorkspaceCopy } from "./copy";
import { ModelServiceSettings } from "@/components/review/ModelServiceSettings";

export function SettingsWorkspace() {
  const c = useWorkspaceCopy(); const glass = useLiquidCopy(); const { locale, setLocale } = useLocale(); const { theme, setTheme } = useTheme();
  return <div className="iw-page iw-settings"><header className="iw-page-heading"><span className="iw-kicker">YOUR WORKSPACE</span><h1>{c.settings}</h1><p>{c.sessionSettings}</p></header><div className="iw-settings-grid"><ModelServiceSettings /><section className="iw-surface"><span className="iw-kicker">01 / LANGUAGE</span><h2>{c.language}</h2><div className="iw-options">{([{value:"zh-CN", label:"简体中文", sample:"让每一次决策都有据可循。"}, {value:"en-US", label:"English", sample:"Every decision, in perspective."}] as const).map((item) => <button key={item.value} lang={item.value} aria-pressed={locale === item.value} onClick={() => setLocale(item.value as Locale)}><strong>{item.label}</strong><span>{item.sample}</span></button>)}</div></section><section className="iw-surface"><span className="iw-kicker">02 / APPEARANCE</span><h2>{c.appearance}</h2><div className="iw-options"><button aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><span className="iw-theme-preview dark-preview"><Moon /></span><strong>{glass.dark}</strong></button><button aria-pressed={theme === "light"} onClick={() => setTheme("light")}><span className="iw-theme-preview light-preview"><Sun /></span><strong>{glass.light}</strong></button></div><p>{c.displayOnly}</p></section><section className="iw-surface"><ShieldCheck size={21} /><h2>{c.privacy}</h2><p>{c.noPermission}</p></section></div></div>;
}

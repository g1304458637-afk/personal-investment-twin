import { useEffect, useState } from "react";
import { useLocale } from "@/locales/LocaleProvider";
import { quotesServiceCopy, quotesServiceRequest } from "@/data/searchService";
import { isTauriRuntime, type RuntimeResponse } from "@/data/runtimeService";

export function QuotesServiceStatus() {
  const { locale } = useLocale(); const c = quotesServiceCopy[locale];
  const desktop = isTauriRuntime();
  const [available, setAvailable] = useState<boolean | null>(desktop ? null : false);
  useEffect(() => {
    if (!desktop) return;
    let active = true;
    quotesServiceRequest<RuntimeResponse<{ available: boolean }>>().then(response => {
      if (active) setAvailable(response.ok && response.result?.available === true);
    }).catch(() => { if (active) setAvailable(false); });
    return () => { active = false; };
  }, [desktop]);
  return <section className="iw-data-service" id="quotes-service">
    <h3>{c.title}</h3><p>{c.subtitle}</p>
    <p role="status">{!desktop ? c.browser : available == null ? (locale === "zh-CN" ? "正在检测行情库…" : "Checking quote library…") : available ? c.available : c.unavailable}</p>
    <p className="text-sm">{c.license}</p>
  </section>;
}

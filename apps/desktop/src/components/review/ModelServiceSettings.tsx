import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/locales/LocaleProvider";
import { modelServiceCopy, modelServiceRequest, type ModelServiceStatus } from "@/data/modelService";
import { isTauriRuntime, type RuntimeResponse } from "@/data/runtimeService";
import { Button } from "@/components/ui/button";
import { SearchServiceSettings } from "@/components/review/SearchServiceSettings";
import { QuotesServiceStatus } from "@/components/review/QuotesServiceStatus";

export function ModelServiceSettings() {
  const { locale } = useLocale(); const c = modelServiceCopy[locale];
  const desktop = isTauriRuntime();
  const [status, setStatus] = useState<ModelServiceStatus | null>(null);
  const [key, setKey] = useState(""); const [busy, setBusy] = useState(desktop);
  const [message, setMessage] = useState(""); const locked = useRef(desktop);
  const errorText = (code: string) => c.errors[code as keyof typeof c.errors] ?? c.errors.model_service_unavailable;
  useEffect(() => {
    if (!desktop) return;
    let active = true;
    modelServiceRequest<ModelServiceStatus>("status").then(value => { if (active) setStatus(value); })
      .catch(() => { if (active) setMessage("model_keychain_unavailable"); })
      .finally(() => { if (active) { setBusy(false); locked.current = false; } });
    return () => { active = false; };
  }, [desktop]);
  async function act(action: "save" | "delete" | "test") {
    if (locked.current || !desktop) return;
    locked.current = true; setBusy(true); setMessage("");
    // Hold only for this command; clear the form immediately, including failure paths.
    const submitted = key; setKey("");
    try {
      if (action === "test") {
        const response = await modelServiceRequest<RuntimeResponse<{ connected: boolean; reason: string | null }>>("test");
        setMessage(response.ok && response.result?.connected ? "connected" : response.result?.reason ?? "model_connection_failed");
      } else {
        setStatus(await modelServiceRequest<ModelServiceStatus>(action, action === "save" ? submitted : undefined));
        setMessage(action === "save" ? "saved" : "deleted");
      }
    } catch (e) { setMessage(e instanceof Error ? e.message : "model_service_unavailable"); }
    finally { locked.current = false; setBusy(false); }
  }
  const notice = message === "saved" ? c.saved : message === "deleted" ? c.deleted : message === "connected" ? c.connected : errorText(message);
  return <section className="iw-surface" id="model-service">
    <span className="iw-kicker">AI & DATA SERVICES</span><h2>{c.title}</h2><p>{c.subtitle}</p>
    <p>{desktop ? c.description : c.browser}</p>
    {desktop && <>
      <h3>DeepSeek</h3>
      <p role="status">{status ? status.configured ? c.configured : c.missing : busy ? c.loading : c.errors.model_keychain_unavailable}</p>
      <form onSubmit={event => { event.preventDefault(); void act("save"); }}>
        <label htmlFor="deepseek-key">{c.key}</label>
        <input id="deepseek-key" name="deepseek-key" type="password" autoComplete="new-password" spellCheck={false}
          value={key} onChange={event => { setKey(event.target.value); setMessage(""); }} disabled={busy}
          placeholder={c.placeholder} className="w-full min-w-0 rounded-xl bg-white/5 px-4 py-3 my-3 text-sm outline-none focus:ring-2 focus:ring-sky-200/50" />
        <div className="flex flex-wrap gap-3">
          <Button size="sm" type="submit" disabled={busy || !key}>{c.save}</Button>
          <Button size="sm" variant="quiet" type="button" disabled={busy || !status?.configured || !!key} onClick={() => void act("test")}>{c.test}</Button>
          <Button size="sm" variant="quiet" type="button" disabled={busy || !status?.configured} onClick={() => void act("delete")}>{c.remove}</Button>
        </div>
      </form>
      <p className="text-sm">{c.testNotice}</p>
      {!!key && <p>{c.unsaved}</p>}
      <p role="status" aria-live="polite">{busy ? c.busy : message ? notice : ""}</p>
    </>}
    <SearchServiceSettings />
    <QuotesServiceStatus />
  </section>;
}

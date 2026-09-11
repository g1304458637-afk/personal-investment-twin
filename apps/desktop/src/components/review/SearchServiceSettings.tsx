import { useEffect, useRef, useState } from "react";
import { useLocale } from "@/locales/LocaleProvider";
import { searchServiceCopy, searchServiceRequest, type SearchServiceStatus } from "@/data/searchService";
import { isTauriRuntime, type RuntimeResponse } from "@/data/runtimeService";
import { Button } from "@/components/ui/button";

export function SearchServiceSettings() {
  const { locale } = useLocale(); const c = searchServiceCopy[locale];
  const desktop = isTauriRuntime();
  const [status, setStatus] = useState<SearchServiceStatus | null>(null);
  const [key, setKey] = useState(""); const [busy, setBusy] = useState(desktop);
  const [message, setMessage] = useState(""); const locked = useRef(desktop);
  const errorText = (code: string) => c.errors[code as keyof typeof c.errors] ?? c.errors.search_service_unavailable;
  useEffect(() => {
    if (!desktop) return;
    let active = true;
    searchServiceRequest<SearchServiceStatus>("status").then(value => { if (active) setStatus(value); })
      .catch(() => { if (active) setMessage("model_keychain_unavailable"); })
      .finally(() => { if (active) { setBusy(false); locked.current = false; } });
    return () => { active = false; };
  }, [desktop]);
  async function act(action: "save" | "delete" | "test" | "setEnabled", enabled?: boolean) {
    if (locked.current || !desktop) return;
    locked.current = true; setBusy(true); setMessage("");
    const submitted = key; setKey("");
    try {
      if (action === "test") {
        const response = await searchServiceRequest<RuntimeResponse<{ connected: boolean; reason: string | null }>>("test");
        setMessage(response.ok && response.result?.connected ? "connected" : response.result?.reason ?? "search_unavailable");
      } else if (action === "setEnabled") {
        setStatus(await searchServiceRequest<SearchServiceStatus>("setEnabled", enabled));
        setMessage(enabled ? "enabled" : "disabled");
      } else {
        setStatus(await searchServiceRequest<SearchServiceStatus>(action, action === "save" ? submitted : undefined));
        setMessage(action === "save" ? "saved" : "deleted");
      }
    } catch (e) { setMessage(e instanceof Error ? e.message : "search_service_unavailable"); }
    finally { locked.current = false; setBusy(false); }
  }
  const notice = message === "saved" ? c.saved : message === "deleted" ? c.deleted : message === "connected" ? c.connected
    : message === "enabled" ? c.enabled : message === "disabled" ? c.disabled : errorText(message);
  return <section className="iw-data-service" id="search-service">
    <h3>{c.title}</h3><p>{c.subtitle}</p>
    <p>{desktop ? c.description : c.browser}</p>
    {desktop && <>
      <p role="status">{status ? status.configured ? (status.enabled ? c.configured : c.disabled) : c.missing : busy ? c.loading : c.errors.model_keychain_unavailable}</p>
      <form onSubmit={event => { event.preventDefault(); void act("save"); }}>
        <label htmlFor="bocha-key">{c.key}</label>
        <input id="bocha-key" name="bocha-key" type="password" autoComplete="new-password" spellCheck={false}
          value={key} onChange={event => { setKey(event.target.value); setMessage(""); }} disabled={busy}
          placeholder={c.placeholder} className="w-full min-w-0 rounded-xl bg-white/5 px-4 py-3 my-3 text-sm outline-none focus:ring-2 focus:ring-sky-200/50" />
        <div className="flex flex-wrap gap-3">
          <Button size="sm" type="submit" disabled={busy || !key}>{c.save}</Button>
          <Button size="sm" variant="quiet" type="button" disabled={busy || !status?.configured || !!key} onClick={() => void act("test")}>{c.test}</Button>
          <Button size="sm" variant="quiet" type="button" disabled={busy || !status?.configured} onClick={() => void act("delete")}>{c.remove}</Button>
        </div>
      </form>
      {status?.configured && <label className="iw-search-toggle"><input type="checkbox" checked={!!status.enabled} disabled={busy}
        onChange={event => void act("setEnabled", event.target.checked)} />{c.enabled}</label>}
      <p className="text-sm">{c.testNotice}</p>
      {!!key && <p>{c.unsaved}</p>}
      <p role="status" aria-live="polite">{busy ? c.busy : message ? notice : ""}</p>
    </>}
  </section>;
}

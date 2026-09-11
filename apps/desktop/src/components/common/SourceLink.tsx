import { useState, type ReactNode } from "react";
import { openDesktopSource, sourceWebUrl } from "@/data/externalLinks";

export function SourceLink({ url, children, zh }: {url: string; children: ReactNode; zh: boolean}) {
  const [failed, setFailed] = useState(false);
  const [opening, setOpening] = useState(false);
  const href = sourceWebUrl(url);
  if (!href) return <span>{children}</span>;
  return <>
    <a href={href} target="_blank" rel="noopener noreferrer" aria-busy={opening}
      title={zh ? "在浏览器中打开来源原文" : "Open the original source in your browser"}
      onClick={async event => {
        if (!("__TAURI_INTERNALS__" in window)) return;
        event.preventDefault();
        if (opening) return;
        setFailed(false); setOpening(true);
        try { await openDesktopSource(href); } catch { setFailed(true); }
        finally { setOpening(false); }
      }}>{children}</a>
    {failed && <div role="alert" className="agent-chat__source-error">
      <span>{zh ? "未能打开浏览器。可以重试链接，或复制下方网址：" : "Could not open the browser. Retry the link or copy the URL below:"}</span>
      <input readOnly aria-label={zh ? "来源网址" : "Source URL"} value={href} onFocus={event => event.currentTarget.select()}/>
    </div>}
  </>;
}

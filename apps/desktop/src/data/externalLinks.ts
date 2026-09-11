type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;

export function sourceWebUrl(value: string): string | null {
  if (value.length > 8192 || /[\u0000-\u001f\u007f]/.test(value)) return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && url.hostname && !url.username && !url.password
      ? url.href : null;
  } catch { return null; }
}

export async function openDesktopSource(value: string, call?: Invoke): Promise<void> {
  const url = sourceWebUrl(value);
  if (!url) throw new Error("invalid_source_url");
  const invoke = call ?? (await import("@tauri-apps/api/core")).invoke;
  await invoke("open_source_url", { url });
}

/**
 * Client-side file export helpers.
 *
 * Data exports carry only values the backend already rendered — no
 * recomputation — and work in both the desktop app and the offline browser
 * preview. A corrupted/no-storage environment degrades to a no-op download,
 * never an error dialog.
 */

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  // Revoking synchronously can abort the download before WebKit's WebView
  // has started it; release the URL asynchronously instead.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function downloadPngDataUrl(dataUrl: string, filename: string) {
  const [meta, payload] = dataUrl.split(",");
  const mime = meta?.match(/:(.*?);/)?.[1] ?? "image/png";
  const binary = atob(payload ?? "");
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  triggerDownload(new Blob([bytes], { type: mime }), filename);
}

export function downloadText(filename: string, text: string, mime = "text/csv;charset=utf-8") {
  // BOM keeps Excel from mangling the UTF-8 when the CSV is opened directly.
  triggerDownload(new Blob(["\ufeff", text], { type: mime }), filename);
}

export function toCsv(headers: string[], rows: Array<Array<string | number | null | undefined>>): string {
  const escape = (value: string | number | null | undefined): string => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [headers, ...rows].map((row) => row.map(escape).join(",")).join("\r\n") + "\r\n";
}

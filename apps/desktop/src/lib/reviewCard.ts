/**
 * Desensitized review card: one Episode → a shareable SVG.
 *
 * Privacy is structural, not cosmetic: this builder consumes only
 * decision types, normalized price points (base = 100), relative return
 * and duration.  Absolute prices, amounts, quantities and the real
 * instrument id are never passed in, so they can never leak into the SVG.
 * Deterministic: same episode → byte-identical SVG.
 */

export interface CardEpisodeInput {
  episodeId: string;
  openedAt: string;
  closedAt: string | null;
  status: "open" | "closed";
  durationDays: number | null;
  decisions: { occurredAt: string; decisionType: string }[];
  pricePoints: { observedAt: string; price: number; segment: string }[];
  result: {
    returnValue: number | null;
    resultKind: string | null; // realized | marked
    resultSign: string | null; // profit | loss | flat
  };
}

export interface ReviewCard {
  svg: string;
  filename: string;
  mimetype: "image/svg+xml";
}

const W = 1080;
const H = 1350;

function esc(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fnv1a(text: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

const TYPE_LABEL: Record<string, string> = {
  open_position: "建仓",
  add_position: "加仓",
  reduce_position: "减仓",
  close_position: "平仓",
};

function rhythm(decisions: { decisionType: string }[]): string {
  const parts: string[] = [];
  for (const decision of decisions) {
    const label = TYPE_LABEL[decision.decisionType] ?? "操作";
    const last = parts[parts.length - 1];
    if (last && last.startsWith(label)) {
      const count = Number(last.split("×")[1] ?? 1) + 1;
      parts[parts.length - 1] = `${label}×${count}`;
    } else parts.push(label);
  }
  return parts.join(" → ") || "无操作";
}

function mmdd(iso: string): string {
  return iso.slice(5, 10);
}

export function buildReviewCard(entry: CardEpisodeInput): ReviewCard {
  const episodePoints = entry.pricePoints.filter((point) => point.segment === "episode");
  const base = episodePoints[0]?.price ?? 0;
  const normalized = base > 0
    ? episodePoints.map((point) => ({ date: point.observedAt, value: (point.price / base) * 100 }))
    : [];
  const decisions = [...entry.decisions].sort((a, b) => a.occurredAt.localeCompare(b.occurredAt));

  const code = `标的 #${fnv1a(entry.episodeId).slice(0, 4).toUpperCase()}`;
  const endLabel = entry.closedAt ? mmdd(entry.closedAt) : "至今";
  const returnValue = entry.result.returnValue;
  const signText = returnValue === null ? "—" : `${returnValue > 0 ? "+" : ""}${(returnValue * 100).toFixed(1)}%`;
  const kindText = entry.result.resultKind === "marked" ? "持有中估值" : "已实现结果";

  // Sparkline geometry (no axes, no price labels: only the normalized shape).
  const x0 = 90, x1 = W - 90, y0 = 400, y1 = 700;
  const values = normalized.map((point) => point.value);
  const lo = Math.min(100, ...values), hi = Math.max(100, ...values);
  const span = hi - lo || 1;
  const px = (i: number) => x0 + (i / Math.max(1, normalized.length - 1)) * (x1 - x0);
  const py = (v: number) => y1 - ((v - lo) / span) * (y1 - y0);
  const line = normalized.map((point, i) => `${px(i).toFixed(1)},${py(point.value).toFixed(1)}`).join(" ");
  const area = `${x0},${y1} ${line} ${x1},${y1}`;
  // Decision markers at the nearest normalized point by date order.
  const markers = decisions.map((decision) => {
    let best = 0;
    let bestDiff = Infinity;
    for (let i = 0; i < normalized.length; i += 1) {
      const diff = Math.abs(Date.parse(normalized[i].date) - Date.parse(decision.occurredAt));
      if (diff < bestDiff) { bestDiff = diff; best = i; }
    }
    const buy = decision.decisionType === "open_position" || decision.decisionType === "add_position";
    const color = buy ? "#7ee2b8" : "#ffb0bc";
    const label = TYPE_LABEL[decision.decisionType] ?? "操作";
    return { x: px(best), y: py(normalized[best]?.value ?? 100), color, label };
  });

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0b1420"/>
      <stop offset="1" stop-color="#0d1826"/>
    </linearGradient>
  </defs>
  <rect width="${W}" height="${H}" fill="url(#bg)"/>
  <text x="90" y="120" font-family="system-ui, sans-serif" font-size="26" letter-spacing="6" fill="#8cdaf2">TOUJING · 复盘卡片</text>
  <text x="90" y="196" font-family="system-ui, sans-serif" font-size="52" font-weight="650" fill="#e6f1f7">一轮投资的完整复盘</text>
  <text x="90" y="250" font-family="ui-monospace, monospace" font-size="26" fill="#9db4c4">${esc(code)} · ${mmdd(entry.openedAt)} → ${esc(endLabel)} · ${entry.durationDays ?? "?"} 天 · ${decisions.length} 次操作</text>
  <text x="90" y="300" font-family="system-ui, sans-serif" font-size="26" fill="#9db4c4">操作节奏：${esc(rhythm(decisions))}</text>
  <rect x="${x0 - 20}" y="${y0 - 40}" width="${x1 - x0 + 40}" height="${y1 - y0 + 80}" rx="16" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.08)"/>
  <polygon points="${area}" fill="rgba(140,218,242,0.10)"/>
  <polyline points="${line}" fill="none" stroke="#83d8ff" stroke-width="3" stroke-linejoin="round"/>
  ${markers.map((marker) => `<circle cx="${marker.x.toFixed(1)}" cy="${marker.y.toFixed(1)}" r="7" fill="${marker.color}" stroke="#0b1420" stroke-width="2"/>`).join("\n  ")}
  <text x="90" y="830" font-family="system-ui, sans-serif" font-size="24" fill="#9db4c4">${esc(kindText)}</text>
  <text x="90" y="920" font-family="ui-monospace, monospace" font-size="96" font-weight="650"
    fill="${returnValue === null ? "#e6f1f7" : returnValue > 0 ? "#69d5bb" : returnValue < 0 ? "#ff8f9c" : "#e6f1f7"}">${esc(signText)}</text>
  <text x="90" y="980" font-family="system-ui, sans-serif" font-size="24" fill="#9db4c4">区间收益（归一化，起点 = 100，非真实价格）</text>
  <line x1="90" y1="1140" x2="${W - 90}" y2="1140" stroke="rgba(255,255,255,0.10)"/>
  <text x="90" y="1200" font-family="system-ui, sans-serif" font-size="22" fill="#9db4c4">本卡片为个人历史复盘的脱敏摘要：标的信息已匿名化，</text>
  <text x="90" y="1236" font-family="system-ui, sans-serif" font-size="22" fill="#9db4c4">价格轴为归一化指数。它记录过去，不构成任何投资建议。</text>
  <text x="90" y="1290" font-family="ui-monospace, monospace" font-size="20" fill="#5f7889">投镜 · 数据不出本机</text>
</svg>`;
  return {
    svg,
    filename: `toujing-review-card-${fnv1a(entry.episodeId).slice(0, 6)}.svg`,
    mimetype: "image/svg+xml",
  };
}

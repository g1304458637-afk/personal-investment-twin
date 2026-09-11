import { adaptPositionEpisodeDemo, type BackendPositionEpisodeDemo, type PositionEpisodeEntryView } from "./positionEpisode.ts";
import type { StandardChartMarket } from "../components/charts/standardChartModel.ts";

/** Offline chart transport only. It never calculates portfolio state or outcomes. */
export interface StandardChartDemoView {
  market: StandardChartMarket;
  entry: PositionEpisodeEntryView;
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("Invalid standard chart payload");
  return value as Record<string, unknown>;
}
function text(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw new Error("Missing standard chart metadata");
  return value;
}
function positive(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) throw new Error("Invalid market price");
  return value;
}
function nonnegative(value: unknown): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) throw new Error("Invalid market volume/amount");
  return value;
}

export function adaptStandardChartDemo(raw: unknown): StandardChartDemoView {
  const root = object(raw);
  if (root.schema_version !== "1" || root.data_tier !== "synthetic") throw new Error("Chart example must remain simulated");
  const source = object(root.market);
  const market: StandardChartMarket = {
    instrumentId: text(source.instrument_id), replayInstrumentId: text(source.replay_instrument_id),
    displayName: text(source.display_name), currency: text(source.currency), priceBasis: text(source.price_basis),
    sourceUrl: text(source.source_url), sourceSha256: text(source.source_sha256), bars: [],
  };
  if (!/^[A-Z]{3}$/.test(market.currency) || !/^[a-f0-9]{64}$/.test(market.sourceSha256)) throw new Error("Invalid chart source metadata");
  if (!Array.isArray(source.bars) || source.bars.length < 2) throw new Error("Chart example requires market bars");
  let previous = "";
  market.bars = source.bars.map((value) => {
    const row = object(value), date = text(row.date);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(`${date}T00:00:00Z`)) || new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) !== date || date <= previous) throw new Error("Market bars must have unique chronological session dates");
    previous = date;
    const open = positive(row.open), high = positive(row.high), low = positive(row.low), close = positive(row.close);
    if (high < Math.max(open, close) || low > Math.min(open, close) || low > high) throw new Error("Invalid OHLC range");
    return { date, open, high, low, close, volume: nonnegative(row.volume), amount: nonnegative(row.amount) };
  });
  const bundle = adaptPositionEpisodeDemo(root.position_episode_demo as BackendPositionEpisodeDemo);
  if (bundle.entries.length !== 1) throw new Error("Standard chart example must contain one scoped episode");
  const entry = bundle.entries[0];
  if (entry.episode.instrumentId !== market.replayInstrumentId || entry.instrument.currency !== market.currency) throw new Error("Chart/replay instrument or currency mismatch");
  const closes = new Map(market.bars.map((bar) => [bar.date, bar.close]));
  for (const point of entry.pricePoints) {
    const close = closes.get(point.observedAt.slice(0, 10));
    if (close === undefined || Math.abs(close - point.price) > 1e-8) throw new Error("Chart and replay price basis mismatch");
  }
  return { market, entry };
}

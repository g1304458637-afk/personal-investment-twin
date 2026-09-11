import type { ArchiveOutcome } from "./investments";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { notifyRuntimeDataChange } from "./runtimeInvalidation";

export interface RuntimeResponse<T> {
  request_id: string | null;
  ok: boolean;
  result: T | null;
  error: { code: string; message: string } | null;
}

export const isTauriRuntime = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export async function runtimeRequest<T>(method: string, params: Record<string, unknown>): Promise<T> {
  if (!isTauriRuntime()) throw new Error("desktop_runtime_required");
  const response = await invoke<RuntimeResponse<T>>("runtime_product_request", { method, params });
  if (!response.ok || !response.result) throw new Error(response.error?.message ?? "runtime_request_failed");
  notifyRuntimeDataChange(method, params);
  return response.result;
}

export async function pickCsv(): Promise<{ path: string; filename: string } | null> {
  if (!isTauriRuntime()) return null;
  const selected = await open({ multiple: false, directory: false, filters: [{ name: "CSV", extensions: ["csv"] }] });
  if (typeof selected !== "string") return null;
  return { path: selected, filename: selected.split(/[\\/]/).pop() ?? "data.csv" };
}

export const realUserApi = {
  accounts: () => runtimeRequest<{ accounts: RuntimeAccount[]; data_mode: "real_user" }>("account.list", {}),
  status: (subjectId: string, accountId: string) => runtimeRequest<RuntimeDataStatus>("account.get_data_status", { subject_id: subjectId, account_id: accountId }),
  previewTrades: (params: Record<string, unknown>) => runtimeRequest<TradePreview>("ingestion.preview_trade_csv", params),
  commitTrades: (params: Record<string, unknown>) => runtimeRequest<Record<string, unknown>>("ingestion.commit_trade_import", params),
  previewPrices: (params: Record<string, unknown>) => runtimeRequest<MarketPreview>("market.preview_price_csv", params),
  commitPrices: (params: Record<string, unknown>) => runtimeRequest<Record<string, unknown>>("market.commit_price_import", params),
  investments: (subjectId: string, accountId: string) => runtimeRequest<RuntimeInvestments>("investments.list", { subject_id: subjectId, account_id: accountId }),
  episode: (subjectId: string, accountId: string, episodeId: string) => runtimeRequest<RuntimeEpisodeResult>("episode.get", { subject_id: subjectId, account_id: accountId, episode_id: episodeId }),
  deleteAccount: (subjectId: string, accountId: string) => runtimeRequest<{ deleted: boolean }>("data.delete_account", { subject_id: subjectId, account_id: accountId }),
  strategyComparison: (subjectId: string, accountId: string, episodeId: string) => runtimeRequest<{ status: string; reason: string | null; report: unknown | null }>("strategy_comparison.get", { subject_id: subjectId, account_id: accountId, episode_id: episodeId }),
  strategyTeaching: (report: Record<string, unknown>, focus: string | null) => runtimeRequest<{ status: string; reason: string | null; texts: string[]; dropped: unknown[]; note: string | null }>("strategy_teaching.explain", { report, focus }),
};

export interface RuntimeAccount { subject_id: string; account_id: string; display_name: string; initial_cash: number; created_at: string; updated_at: string }
export interface RuntimeDataStatus { subject_id: string; account_id: string; execution_count: number; instrument_status: string; fee_status: string; unknown_fee_count: number; market_data: { status: string; required: number; available: number; missing: [string, string[]][] }; review_status: string; last_trade_import: string | null; last_market_import: string | null; latest_market_date: string | null; import_history: Array<{ batch_id: string; kind: string; filename: string; imported_at: string; summary: Record<string, number> }> }
export interface TradePreview { preview_fingerprint: string; filename: string; batch: { batch_id: string; file_sha256: string }; summary: Record<string, number>; rows: Array<{ row_ref: string; status: string; candidate: null | Record<string, unknown>; issues: Array<{ code: string }> }> }
export interface MarketPreview { preview_fingerprint: string; filename: string; batch_id: string; file_sha256: string; summary: Record<string, number>; rows: Array<{ row_number: number; status: string; candidate: null | { date: string; symbol: string; close: number; price_type: string }; issues: Array<{ code: string }> }>; missing_required_dates: [string, string[]][] }
export interface RuntimeInvestments { subject_id: string; account_id: string; as_of: string; data_tier: "authorized_beta"; portfolio_state_status: string; portfolio_state_reason: string | null; summary: { open_episode_count: number; closed_episode_count: number; current_position_count: number }; episodes: Array<{ outcome_summary: ArchiveOutcome; episode_id: string; instrument_id: string; display_name: string; currency: string | null; status: "open" | "closed"; opened_at: string; closed_at: string | null; duration_days: number; duration_kind: "final" | "so_far"; quantity: number | null; average_cost: number | null; valuation_at: string | null; valuation_price: number | null; market_value: number | null }> }
export interface RuntimeEpisodeResult { status: string; reason: string | null; entry: unknown | null }

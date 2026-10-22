import { runtimeRequest } from './runtimeService';
export type Row = Record<string, unknown>;
export type LedgerSnapshot = Row & { as_of: string; currency: string; positions: Row[]; episodes: Row[]; daily: Row[]; warnings: string[]; errors: Row[]; definitions: string[]; return_limitation: string };
export interface LedgerData { subject_id: string; account_id: string; enabled: boolean; profile: Row | null; snapshot: LedgerSnapshot | null; events: Row[]; reconciliations: Row[]; journal?: Row[]; executions?: Row[] }
export interface LedgerPreview { preview_fingerprint: string; file_sha256: string | null; issues: Row[]; new_events: Row[]; duplicates: number; after: LedgerSnapshot; report: Row | null; journal_entry?: Row }
export const ledgerRead = (params: Row) => runtimeRequest<LedgerData>('ledger.get', params);
export const ledgerPreview = (params: Row) => runtimeRequest<LedgerPreview>('ledger.preview', params);
export const ledgerCommit = (params: Row, preview: LedgerPreview) => runtimeRequest<Row>('ledger.commit', {...params, expected_preview_fingerprint:preview.preview_fingerprint, expected_file_sha256:preview.file_sha256});
export { backupPreferences, applyRestoredPreferences } from "./ledgerPreferences";
export function scopedLedger(data: LedgerData | null, subject: string, account: string) { return data?.subject_id===subject && data.account_id===account ? data : null; }

export async function resumeRestoredPreferences() { const result = await runtimeRequest<{pending:null|{restore_id:string;preferences:Row}}>("backup.pending_preferences", {}); if (!result.pending) return false; const {applyRestoredPreferences}=await import("./ledgerPreferences"); applyRestoredPreferences(window.localStorage,result.pending.preferences); await runtimeRequest("backup.ack_preferences",{restore_id:result.pending.restore_id}); window.location.reload(); return true; }

/** All successful local write RPCs notify app-scoped read caches. */
type Change = { subject: string; account: string };
const listeners = new Set<(change: Change) => void>();
const writes = new Set(["ingestion.commit_trade_import", "market.commit_price_import", "data.delete_account",
  "review.add_note", "compare.import_share", "compare.revoke_share"]);
export function onRuntimeDataChange(listener: (change: Change) => void) {
  listeners.add(listener); return () => { listeners.delete(listener); };
}
export function notifyRuntimeDataChange(method: string, params: Record<string, unknown>) {
  if (!writes.has(method) || typeof params.subject_id !== "string" || typeof params.account_id !== "string") return;
  const change = {subject:params.subject_id, account:params.account_id};
  listeners.forEach(listener => listener(change));
}

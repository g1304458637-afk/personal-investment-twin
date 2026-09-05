import { open, save } from "@tauri-apps/plugin-dialog";
import { isTauriRuntime, runtimeRequest } from "./runtimeService";
import type { ReviewContextView, ReviewInference, ReviewScope } from "./decisionReview";

export interface SharedEpisode { share_id: string; subject_id: string; episode_id: string; as_of: string; expires_at: string; allow_agent_review: boolean; instrument: { local_symbol: string }; verification: string }
const params = (scope: ReviewScope) => ({ ...scope });
export const reviewService = {
  available: isTauriRuntime,
  context: (scope: ReviewScope) => runtimeRequest<ReviewContextView>("review.context", params(scope)),
  start: (scope: ReviewScope, question: string) => runtimeRequest<{ job_id: string }>("review.start", { ...params(scope), question, allow_model_review: true }),
  poll: (scope: ReviewScope, job_id: string) => runtimeRequest<{ status: "running" | "complete" | "failed" | "stale"; result: ReviewInference | null; reason?: string }>("review.poll", { ...params(scope), job_id }),
  note: (scope: ReviewScope, text: string, note_kind: string) => runtimeRequest("review.add_note", { ...params(scope), text, note_kind }),
  shares: (scope: ReviewScope) => runtimeRequest<{ shares: SharedEpisode[] }>("compare.list_shares", params(scope)),
  revoke: (scope: ReviewScope, share_id: string) => runtimeRequest("compare.revoke_share", { ...params(scope), share_id }),
  async importShare(scope: ReviewScope, trusted_sender_fingerprint: string) {
    const file_path = await open({ multiple: false, directory: false, filters: [{ name: "Episode share", extensions: ["json"] }] });
    if (typeof file_path !== "string") return null;
    return runtimeRequest<{ share_id: string }>("compare.import_share", { ...params(scope), file_path, trusted_sender_fingerprint });
  },
  async exportShare(scope: ReviewScope, recipient_subject_id: string, recipient_account_id: string, expires_at: string, allow_agent_review: boolean) {
    const file_path = await save({ defaultPath: "episode.toujing-share.json", filters: [{ name: "Episode share", extensions: ["json"] }] });
    if (!file_path) return null;
    return runtimeRequest<{ signer_fingerprint: string }>("compare.export_share", { ...params(scope), file_path, recipient_subject_id, recipient_account_id, expires_at, allow_agent_review, owner_confirmed: true });
  },
};

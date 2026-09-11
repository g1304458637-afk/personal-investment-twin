import { runtimeRequest, isTauriRuntime } from "./runtimeService";
import type { ChatApi, ChatContext, ChatScope } from "./agentChat";
import { isConversationScope } from "./agentChat";
export const agentChatService: ChatApi & { available: () => boolean; context: (scope: ChatScope) => Promise<ChatContext> } = {
  available: isTauriRuntime,
  context: scope => runtimeRequest("review.context", {...scope}),
  start: (scope, question, previousId) => runtimeRequest("review.start", {...scope, question, allow_model_review:true,
    ...(isConversationScope(scope) ? {answer_version:"account_conversation_answer_v2", conversation_engine:"dsa"} : {}),
    ...(previousId ? {previous_inference_id:previousId} : {})}),
  poll: (scope, jobId) => runtimeRequest("review.poll", {...scope, job_id:jobId}),
  cancel: (scope, jobId) => isConversationScope(scope)
    ? runtimeRequest("review.poll", {...scope, job_id:jobId, cancel:true}) : Promise.resolve(),
};

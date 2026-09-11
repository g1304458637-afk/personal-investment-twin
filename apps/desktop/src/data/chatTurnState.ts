import type { ChatTurn } from './agentChat';

/** Retry the last failed/stopped turn in place, never rewrite subsequent history. */
export function startChatTurn(turns: ChatTurn[], question: string, id: string, retryId?: string): ChatTurn[] {
  if (turns.some(turn => turn.status === 'running')) throw new Error('chat_already_running');
  const retry = retryId ? turns.at(-1) : undefined;
  if (retryId && (!retry || retry.id !== retryId || !['failed', 'stopped'].includes(retry.status))) {
    throw new Error('chat_retry_not_latest');
  }
  const next: ChatTurn = { id: retry?.id ?? id, question: retry?.question ?? question, status: 'running', result: null };
  return [...(retry ? turns.slice(0, -1) : turns), next];
}

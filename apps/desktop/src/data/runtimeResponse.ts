export interface ResponseEnvelope<T> {
  ok: boolean;
  result: T | null;
  error: { code: string; message: string } | null;
}

/** Transport success is independent of payload truthiness. */
export function runtimeResponseError(response: ResponseEnvelope<unknown>): Error | null {
  if (response.error?.code === "runtime_outcome_unknown") {
    return new Error("请求超时，写入结果尚未确认。请重新读取账户数据后再操作，避免重复提交。 / Write outcome unconfirmed; reload account data before retrying.");
  }
  if (!response.ok || response.error) return new Error(response.error?.message ?? "runtime_request_failed");
  return null;
}

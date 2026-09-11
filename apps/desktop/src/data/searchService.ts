/** Local desktop Bocha search commands. No browser persistence or secret getter. */
export interface SearchServiceStatus { configured: boolean; enabled: boolean; provider: "bocha" }
export interface QuotesServiceStatus { available: boolean; provider: "akshare"; license: string; disclaimer: string }
type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
const SEARCH_CODES = ["model_key_invalid", "search_not_configured", "model_keychain_unavailable", "model_keychain_unsupported", "search_prefs_unavailable"];
export async function searchServiceRequest<T>(action: "status" | "save" | "delete" | "test" | "setEnabled", value?: string | boolean, call?: Invoke): Promise<T> {
  if (!call) {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) throw new Error("desktop_runtime_required");
    call = (await import("@tauri-apps/api/core")).invoke;
  }
  const commands = { status: "search_service_status", save: "search_service_save", delete: "search_service_delete", test: "search_service_test", setEnabled: "search_service_set_enabled" };
  const args = action === "save" ? { apiKey: value } : action === "setEnabled" ? { enabled: value } : undefined;
  try {
    return await call<T>(commands[action], args);
  } catch (error) {
    const code = String(error);
    throw new Error(SEARCH_CODES.includes(code) ? code : "search_service_unavailable");
  }
}
export async function quotesServiceRequest<T>(call?: Invoke): Promise<T> {
  if (!call) {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) throw new Error("desktop_runtime_required");
    call = (await import("@tauri-apps/api/core")).invoke;
  }
  try {
    return await call<T>("quotes_service_status");
  } catch {
    throw new Error("quotes_service_unavailable");
  }
}
export const searchServiceCopy = {
  "zh-CN": {
    title: "联网搜索", subtitle: "博查 Web Search",
    description: "密钥保存在本机钥匙串的独立条目，不会覆盖 DeepSeek。检索只发送公开证券名称、代码或公开问题。",
    configured: "已保存配置", missing: "尚未配置", loading: "正在读取配置…",
    key: "博查 API Key", placeholder: "输入新密钥，不会回显已保存的密钥",
    save: "保存密钥", test: "测试搜索", remove: "删除密钥", busy: "正在处理…",
    saved: "密钥已保存。测试可能消耗少量搜索额度。",
    deleted: "密钥已删除。新的提问将不再联网搜索。已经发出的请求可能仍会完成。",
    connected: "搜索已接通。",
    enabled: "允许问投镜在需要时联网搜索",
    disabled: "已关闭搜索。账户分析不受影响。",
    testNotice: "测试只搜索固定的公开词“上海证券交易所”，不含账户数据，可能产生搜索费用。",
    browser: "请在投镜桌面应用中配置。网页展示模式不会保存密钥或调用本机搜索。",
    unsaved: "请先保存新密钥，再测试连接。",
    errors: {
      model_key_invalid: "请输入有效密钥，不要包含空格或换行。",
      search_not_configured: "请先保存博查密钥。",
      model_keychain_unavailable: "无法访问 macOS 钥匙串，请检查系统授权后重试。",
      model_keychain_unsupported: "当前只支持 macOS 钥匙串。",
      search_prefs_unavailable: "无法保存搜索开关，请检查本机权限后重试。",
      search_service_unavailable: "本机服务未就绪，请重新打开投镜后重试。",
      search_authentication_failed: "密钥验证失败，请检查或替换密钥。",
      search_quota_or_forbidden: "额度不足或无权访问，请检查博查账户。",
      search_rate_limited: "搜索暂时限流，请稍后重试。",
      search_timeout: "搜索超时，请稍后重试。",
      search_unavailable: "搜索暂时不可用，请检查网络后重试。",
      search_test_response_invalid: "服务未返回预期搜索结果，请重试。",
      search_response_invalid: "搜索结果无法识别，请重试。",
    },
  },
  "en-US": {
    title: "Web search", subtitle: "Bocha Web Search",
    description: "Stored in a separate local Keychain item. It never overwrites DeepSeek. Queries send only public security names, codes or public questions.",
    configured: "Configuration saved", missing: "Not configured", loading: "Reading configuration…",
    key: "Bocha API Key", placeholder: "Enter a new key; saved keys are never displayed",
    save: "Save key", test: "Test search", remove: "Delete key", busy: "Working…",
    saved: "Key saved. Testing may use a small search quota.",
    deleted: "Key deleted. New questions will not search the web. Requests already sent may still complete.",
    connected: "Search is connected.",
    enabled: "Allow Ask Toujing to search the public web when needed",
    disabled: "Search is off. Account analysis is unaffected.",
    testNotice: "The test searches only the fixed public term “Shanghai Stock Exchange”, with no account data, and may incur a search charge.",
    browser: "Configure in the Toujing desktop app. The website does not store keys or call local search.",
    unsaved: "Save the new key before testing.",
    errors: {
      model_key_invalid: "Enter a valid key without spaces or line breaks.",
      search_not_configured: "Save your Bocha key first.",
      model_keychain_unavailable: "Cannot access macOS Keychain. Check system permissions and retry.",
      model_keychain_unsupported: "Only macOS Keychain is supported at present.",
      search_prefs_unavailable: "Could not save the search switch. Check local permissions and retry.",
      search_service_unavailable: "Local service is not ready. Reopen Toujing and retry.",
      search_authentication_failed: "Authentication failed. Check or replace your key.",
      search_quota_or_forbidden: "Quota or permission denied. Check your Bocha account.",
      search_rate_limited: "Search is rate limited. Please retry shortly.",
      search_timeout: "Search timed out. Please retry shortly.",
      search_unavailable: "Search is temporarily unavailable. Check your network and retry.",
      search_test_response_invalid: "Unexpected search test response. Please retry.",
      search_response_invalid: "Search results could not be read. Please retry.",
    },
  },
};
export const quotesServiceCopy = {
  "zh-CN": {
    title: "公开行情", subtitle: "AKShare",
    available: "可用作研究背景。这不是稳定行情 SLA，也不能覆盖账户 Evidence。",
    unavailable: "当前运行时未装入 AKShare，问投镜不会编造报价。",
    browser: "行情状态只在桌面应用中检测。",
    license: "MIT · 数据来源受上游限制，仅供研究参考。",
  },
  "en-US": {
    title: "Public quotes", subtitle: "AKShare",
    available: "Available as research background. This is not a quote SLA and does not replace account Evidence.",
    unavailable: "AKShare is not in this runtime. Ask Toujing will not invent quotes.",
    browser: "Quote status is checked in the desktop app only.",
    license: "MIT · Upstream data limits apply. Research use only.",
  },
};

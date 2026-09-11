/** Local desktop credential commands only. No browser persistence or secret getter. */
export interface ModelServiceStatus { configured: boolean; provider: "deepseek"; model: string }
type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
export async function modelServiceRequest<T>(action: "status" | "save" | "delete" | "test", apiKey?: string, call?: Invoke): Promise<T> {
  if (!call) {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) throw new Error("desktop_runtime_required");
    call = (await import("@tauri-apps/api/core")).invoke;
  }
  const commands = { status: "model_service_status", save: "model_service_save", delete: "model_service_delete", test: "model_service_test" };
  try {
    return await call<T>(commands[action], action === "save" ? { apiKey } : undefined);
  } catch (error) {
    // Unknown native errors are never displayed verbatim (could contain sensitive data).
    const code = String(error);
    throw new Error(["model_key_invalid", "model_not_configured", "model_keychain_unavailable", "model_keychain_unsupported"].includes(code) ? code : "model_service_unavailable");
  }
}

export const modelServiceCopy = {
  "zh-CN": {
    title: "AI 与数据服务", subtitle: "DeepSeek · deepseek-v4-flash",
    description: "密钥保存在本机 macOS 钥匙串。配置一次，重启投镜后仍可使用，无需终端。",
    configured: "已保存配置", missing: "尚未配置", loading: "正在读取配置…",
    key: "DeepSeek API Key", placeholder: "输入新密钥，不会回显已保存的密钥",
    save: "保存密钥", test: "测试连接", remove: "删除密钥", busy: "正在处理…",
    saved: "密钥已保存，可以测试连接或返回投资页面分析。",
    deleted: "密钥已删除，新的分析将不再调用模型。已经发出的请求可能仍会完成。",
    connected: "连接成功，可以使用分析功能。",
    testNotice: "测试只发送固定测试文字，不含账户数据，可能产生少量模型费用。分析时仍需单独授权发送必要证据。",
    browser: "请在投镜桌面应用中配置。网页展示模式不会保存密钥或调用本机后端。",
    unsaved: "请先保存新密钥，再测试连接。", settings: "配置模型服务",
    errors: {
      model_key_invalid: "请输入有效密钥，不要包含空格或换行。",
      model_not_configured: "请先保存 DeepSeek 密钥。",
      model_keychain_unavailable: "无法访问 macOS 钥匙串，请检查系统授权后重试。",
      model_keychain_unsupported: "当前只支持 macOS 钥匙串。",
      model_service_unavailable: "本机服务未就绪，请重新打开投镜后重试。",
      model_authentication_failed: "密钥验证失败，请检查或替换密钥。",
      model_rate_limited: "服务暂时限流或额度不足，请检查 DeepSeek 账户。",
      model_connection_timeout: "连接超时，请稍后重试。",
      model_connection_failed: "连接失败，请检查网络和模型服务状态。",
      model_test_response_invalid: "服务未返回预期测试结果，请重试。",
    },
  },
  "en-US": {
    title: "AI and data services", subtitle: "DeepSeek · deepseek-v4-flash",
    description: "Stored in your local macOS Keychain. Configure once; no Terminal needed after restarting Toujing.",
    configured: "Configuration saved", missing: "Not configured", loading: "Reading configuration…",
    key: "DeepSeek API Key", placeholder: "Enter a new key; saved keys are never displayed",
    save: "Save key", test: "Test connection", remove: "Delete key", busy: "Working…",
    saved: "Key saved. Test the connection or return to your investment to analyze.",
    deleted: "Key deleted. New analyses will not call the model. Requests already sent may still complete.",
    connected: "Connected. Analysis is ready.",
    testNotice: "The test sends only fixed test text, with no account data, and may incur a small model charge. Analysis still requires separate evidence-sharing consent.",
    browser: "Configure in the Toujing desktop app. The website does not store keys or call your local backend.",
    unsaved: "Save the new key before testing.", settings: "Configure model service",
    errors: {
      model_key_invalid: "Enter a valid key without spaces or line breaks.",
      model_not_configured: "Save your DeepSeek key first.",
      model_keychain_unavailable: "Cannot access macOS Keychain. Check system permissions and retry.",
      model_keychain_unsupported: "Only macOS Keychain is supported at present.",
      model_service_unavailable: "Local service is not ready. Reopen Toujing and retry.",
      model_authentication_failed: "Authentication failed. Check or replace your key.",
      model_rate_limited: "Service rate limit or quota reached. Check your DeepSeek account.",
      model_connection_timeout: "Connection timed out. Please retry.",
      model_connection_failed: "Connection failed. Check your network and provider status.",
      model_test_response_invalid: "Unexpected test response. Please retry.",
    },
  },
};

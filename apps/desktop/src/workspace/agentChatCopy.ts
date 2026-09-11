export const agentChatCopy = {
  "zh-CN": {
    refreshing:"已恢复本次会话的回答，正在检查账户资料是否有更新；不会重新调用模型。",
    modelLoading:"正在读取本机模型配置。如 macOS 弹出钥匙串授权窗口，请在系统窗口中确认。",
    retryAnswer:"重试这条回答",
    title:"问投镜", intro:"聊你的投资，查股票行情，学懂知识，也带你看懂图表。", account:"整个账户", scope:"这次聊什么", episode:"某一轮投资（可选）",
    capabilities:"可以聊什么", capabilityHint:"下方六个功能入口会一直保留。选择一个例子，或直接输入自己的问题。",
    suggestions:{research:["综合研究贵州茅台：对照近期行情、公开事件和经营资料。", "查看贵州茅台最近的日线行情，解释价格与成交量的变化。", "贵州茅台最近公开发生了什么？有哪些相反或澄清的信息？", "从公开财报或公告里，帮我理解贵州茅台的经营情况。"],learn:["K线实体、影线、成交量怎么看？", "持仓成本与股票现价有什么区别？", "最大回撤代表什么？"],chart:["带我看一轮投资的加减仓过程", "交易前后的扇形图怎么看？", "同股对比图怎么看？"]},
    all:"账户整体情况", choose:"选择一轮投资", open:"打开投资过程", newChat:"新对话", user:"你", agent:"投镜",     emptyTitle:"先直接问，再按需要看图。",
    empty:"分析你的账户、研究公开股票、弄懂K线与仓位，或打开对应图表。不必先选一轮投资。", question:"问问账户表现、某只股票近况、K线读法，或继续追问…", send:"发送", sending:"正在结合记录分析…", stop:"停止等待",
    consent:"允许将本次问题所需的账户派生事实及本段对话发送给已配置模型。", loading:"正在读取这个账户的分析资料…", browser:"网页预览 · 看图指引可用，AI 对话请在桌面应用中使用。", configuration:"配置模型服务",
    missing:"连接模型后，就可以在这里连续提问。", guide:"带我看懂", guideHint:"产品指引 · 不调用模型", guideEpisode:"投资过程图怎么读", guideAllocation:"交易前后的扇形图怎么看", guideCompare:"同股对比图怎么看", viewChart:"在图中查看",
    scopeHint:"切换分析范围会打开对应对话；不会把其他账户的资料带进来。", session:"对话在本次应用会话内保留；每次回答仍依据当前记录核验。", stopped:"已停止等待。这次请求可能仍在后台完成，没有展示未验证的回答。", restart:"重新开始对话",
    noAccount:"先接入一个账户，或打开示例账户体验。", import:"数据与账户", example:"打开示例账户", unavailableEpisode:"这轮投资不在当前账户中，请重新选择。", modelReady:"模型已配置", notConfigured:"模型待配置", ready:"可以继续提问", retry:"重新读取",
    accountPrompts:["我的整体投资表现怎么样？", "我的持仓主要集中在哪里？", "哪些投资发生了亏损，具体操作和成本怎样变化？", "我的交易活跃度是什么口径？结合记录解释一下。"],
    entries: [
      {id:"analyze", title:"分析我的投资", blurb:"解释你自己的表现、持仓和操作，不必先选一轮投资。", example:"我的整体投资表现怎么样？"},
      {id:"compare", title:"对比我的历史", blurb:"在整个账户下选择明确日期，比较区间表现或同股两轮。不同时间段和结果类型会分别注明。", example:"比较两个时期的账户表现"},
      {id:"scenario", title:"试算一笔交易", blurb:"目前在示例账户试算。说明证券、买卖方向、数量、价格和费用，查看交易前后状态。", example:"假设买入后，现金和仓位怎么变？"},
      {id:"research", title:"研究股票", blurb:"识别公开证券，查看有来源、有时间的近况与行情。", example:"贵州茅台最近公开发生了什么？"},
      {id:"learn", title:"学股票知识", blurb:"结合例子，讲清K线、成交量、成本、仓位和回撤。", example:"K线实体、影线、成交量怎么看？"},
      {id:"chart", title:"带我看图", blurb:"打开已经存在的投资过程、仓位或对比图。", example:"带我看这段加仓"},
    ],
    searchNeeded:"新闻搜索需在设置中配置并开启博查；行情查询不受此开关影响。",
    sources:"来源",
    episodePrompts:["这轮结果是怎样形成的？", "哪些加减仓操作值得回看？", "刚才提到的这次操作，具体改变了什么？"],
  },
  "en-US": {
    refreshing:"Session answers restored. Checking for account updates; no new model call is being made.",
    modelLoading:"Reading local model configuration. If macOS shows a Keychain permission prompt, respond in the system window.",
    retryAnswer:"Retry this answer",
    title:"Ask Toujing", intro:"Explore your investments, research stocks, learn the concepts and understand your charts.", account:"Whole account", scope:"Conversation scope", episode:"One investment (optional)",
    capabilities:"What you can ask", capabilityHint:"All six shortcuts stay available below. Choose an example or ask your own question.",
    suggestions:{research:["Research Kweichow Moutai using recent prices, public events and business information.", "Explain recent daily price and volume changes for Kweichow Moutai.", "What happened publicly at Kweichow Moutai? Look for contrary reports or clarifications.", "Help me understand Kweichow Moutai's business from public financial reports or announcements."],learn:["How do I read the candle body, wicks and volume?", "How does holding cost differ from the market price?", "What does maximum drawdown mean?"],chart:["Show me the adds and reductions in an investment", "How do I read before and after allocation?", "How do I read a same-stock comparison?"]},
    all:"My account overall", choose:"Select an investment", open:"Open investment chart", newChat:"New conversation", user:"You", agent:"Toujing",     emptyTitle:"Start with a question. Open a chart when you need one.",
    empty:"Analyze your account, research a listed stock, learn the chart language, or open the matching view. No investment selection required.", question:"Ask about performance, a public stock, how to read a chart, or follow up…", send:"Send", sending:"Reviewing your records…", stop:"Stop waiting",
    consent:"Allow the required derived account facts and this conversation to be sent to the configured model.", loading:"Reading this account’s analysis context…", browser:"Browser preview · Chart guides work here. Use the desktop app for AI conversation.", configuration:"Configure model service",
    missing:"Connect your model to ask questions here.", guide:"Show me how to read it", guideHint:"Product guide · No model call", guideEpisode:"Read an investment chart", guideAllocation:"Read before / after allocation", guideCompare:"Read a same-stock comparison", viewChart:"View in chart",
    scopeHint:"Changing scope opens its own conversation. Other accounts are never added.", session:"Chats stay in this app session. Each answer is rechecked against current records.", stopped:"Waiting stopped. The request may still finish in the background; no unverified answer is shown.", restart:"Start a new conversation",
    noAccount:"Connect an account, or explore the example account.", import:"Data & accounts", example:"Open example account", unavailableEpisode:"This investment does not belong to the current account. Please select again.", modelReady:"Model configured", notConfigured:"Model not configured", ready:"Ready for questions", retry:"Reload context",
    accountPrompts:["How is my account doing overall?", "Where are my holdings concentrated?", "Which investments lost money, and how did their operations and costs change?", "How is trading activity defined? Explain it using my records."],
    entries: [
      {id:"analyze", title:"Analyze my investments", blurb:"Explain your own results, holdings and operations. No episode required.", example:"How is my account doing overall?"},
      {id:"compare", title:"Compare my history", blurb:"Use whole-account scope to compare explicit periods or two same-stock investments. Dates and result types remain distinct.", example:"Compare my account across two periods"},
      {id:"scenario", title:"Try a trade", blurb:"Example accounts only for now. Provide a security, side, size, price and fees to see the before / after state.", example:"How would a purchase change my cash and allocation?"},
      {id:"research", title:"Research a stock", blurb:"Identify a listed security and read dated public sources and quotes.", example:"What has been reported publicly about Kweichow Moutai recently?"},
      {id:"learn", title:"Learn the terms", blurb:"Plain explanations of candles, volume, cost, position and drawdown. No exams or rankings.", example:"How do I read the candle body, wicks and volume?"},
      {id:"chart", title:"Show me the chart", blurb:"Open an existing investment, allocation or comparison chart.", example:"Show me this add to the position"},
    ],
    searchNeeded:"For news search, configure and enable Bocha in Settings. This toggle does not control quotes.",
    sources:"Sources",
    episodePrompts:["How did this investment result develop?", "Which adds or reductions deserve another look?", "What exactly changed in the operation you just mentioned?"],
  },
};
export function chatErrorText(code: string | undefined, locale: string) {
  const zh = locale === "zh-CN";
  if (code === "model_not_configured") return zh ? "请先在设置中配置模型服务，再回来发送问题。" : "Configure your model in Settings, then send your question.";
  if (code === "account_answer_number_not_in_sources" || code === "account_answer_operation_count_mismatch") return zh ? "回答中的数字未通过来源核对，暂未显示。可以重试这个问题。" : "The answer's numbers could not be verified against its sources. You can retry this question.";
  if (["account_answer_unread_reference", "account_grounding_failed", "account_grounding_incomplete_coverage", "account_fact_source_required", "account_concept_source_required"].includes(code ?? "")) return zh ? "回答与引用资料未通过一致性核对，暂未显示。可以重试这个问题。" : "The answer could not be verified against its cited sources. You can retry this question.";
  if (["account_model_timeout", "account_review_timeout", "review_timeout"].includes(code ?? "")) return zh ? "这次分析等待超时，可以稍后重试。" : "This analysis timed out. Please retry shortly.";
  if (code === "account_model_request_failed") return zh ? "模型请求未成功完成，可以稍后重试或在设置中检查模型服务。" : "The model request did not complete. Retry shortly or check the model service in Settings.";
  if (["account_conversation_schema_failed", "account_conversation_invalid_output", "account_model_response_incomplete"].includes(code ?? "")) return zh ? "模型未返回完整、符合格式的回答，可以重试这个问题。" : "The model did not return a complete answer in the required format. You can retry this question.";
  if (code === "account_conversation_context_over_limit") return zh ? "本轮资料超过处理上限，请缩小问题范围后重试。" : "This request exceeded the context limit. Narrow the question and retry.";
  if (["account_research_incomplete", "account_conversation_unavailable", "account_completed_receipts_required", "account_incomplete_tool_receipt"].includes(code ?? "")) return zh ? "本次资料查询未能完成，暂未形成可验证的回答。可以稍后重试。" : "Research did not complete with enough verified sources. Please retry shortly.";
  if (code?.includes("conversation") || code?.includes("previous_inference") || code?.includes("fingerprint") || code?.includes("facts_changed") || code?.includes("new_user_information")) return zh ? "账户资料或对话范围已变化，请开始新对话，使用最新记录。" : "Records or conversation scope changed. Start a new conversation using the latest records.";
  if (code?.endsWith("review_already_running")) return zh ? "上一次分析还在完成中，请稍后再发送。" : "The previous analysis is still running. Please send again shortly.";
  if (code?.includes("keychain")) return zh ? "请检查系统对模型配置的访问授权。" : "Check system permission to access model configuration.";
  return zh ? "这次回答未完成。可以重试这个问题。" : "This answer did not complete. You can retry this question.";
}

export function chatContextErrorText(code: string | undefined, locale: string) {
  if (code?.includes("keychain") || code === "model_not_configured") return chatErrorText(code, locale);
  return locale === "zh-CN" ? "账户分析资料暂未读取完成。重新读取后即可提问。" : "Account context could not be loaded. Reload it to start asking questions.";
}

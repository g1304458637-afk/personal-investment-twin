# Product Boundary v1

## 1. Product Purpose

投镜用于个人投资历史分析、决策归因、行为证据、
个人历史比较和拟交易后的确定性组合影响分析。

投镜研究的是投资者本人及其历史决策，
不替用户选择证券，不替用户做最终交易决定。

## 2. Allowed

首版允许：

- 历史账户和交易事实分析
- Decision Attribution
- Behavior Evidence
- Personal Twin
- Self vs Past comparison
- 聚合 Peer Benchmark
- 经授权的 User-to-user Compare
- 历史 counterfactual analysis
- 拟交易后的组合状态变化分析
- Agent 对已有 evidence 的解释

所有个人金融数字必须来自确定性计算结果，
不得由 LLM 自行生成。

## 3. Prohibited

首版禁止：

- 推荐具体股票、ETF 或其他证券
- 输出 Buy / Sell verdict
- 给出目标价
- 给出止损价
- 给出“应该持有多少”的个性化目标仓位建议
- AI 买入或卖出信号
- 自动下单
- 一键跟单
- 展示高手实时持仓用于模仿交易
- 展示“收益最高用户正在买什么”
- 根据交易数据给用户贴“贪婪、恐惧、报复性交易”等心理标签

## 4. Agent Rule

Agent 只能解释可追溯的 Evidence。

如果用户询问具体证券应不应该买卖，
系统不得给出交易结论。

可以返回：

- 当前组合事实
- 拟交易后的确定性变化
- 用户自己的历史证据
- 聚合 peer context
- 样本量、方法、限制和置信信息

最终交易决定始终由用户本人完成。

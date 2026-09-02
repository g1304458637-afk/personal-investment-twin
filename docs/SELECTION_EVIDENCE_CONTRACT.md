# Selection Evidence Contract

## Purpose

Selection Evidence 用于描述一个 Investment Episode 中：

- 该资产本身取得了什么收益；
- 相对市场基准表现如何；
- 相对行业基准表现如何。

它描述的是“决策证据”，不是直接证明投资者具有选股能力。

单个 Episode 不得输出“选股能力强/弱”的确定性结论。

---

## 1. Episode Inputs

Selection Evidence 只依赖已经确定的 Episode / Position 金融事实：

- `episode_id`
- `symbol`
- `entry_time`
- `exit_time`
- `status`
- `asset_return`

其中：

- Position / PnL / Return 来自 vectorbt；
- Selection Evidence 不重新计算交易 PnL；
- 完整 Selection Evidence 默认仅针对 `Closed` Episode；
- Open Episode 可以输出部分结果，但必须标记为 partial。

---

## 2. Benchmark Inputs

### Market Benchmark

第一版：

- `market_benchmark_id`
- `market_benchmark_name`
- `market_price_series`

MVP 默认宽基可以使用 CSI300。

---

### Industry Benchmark

需要：

- `industry_id`
- `industry_name`
- `industry_as_of_date`
- `industry_benchmark_id`
- `industry_benchmark_name`
- `industry_price_series`

行业归属必须以 Episode 开始时点为准。

禁止使用当前行业分类倒填历史 Episode。

---

## 3. Data Provenance

每一个 Benchmark 必须记录：

- `data_source`
- `data_version`
- `as_of`
- `is_synthetic`

比赛离线 Demo 可以使用本地冻结数据。

如果使用 synthetic 数据：

`is_synthetic = true`

并且不得描述为真实历史市场表现。

---

## 4. Outputs

每一个 Episode 最终输出：

- `asset_return`
- `market_benchmark_return`
- `market_comparison`
- `industry_benchmark_return`
- `industry_comparison`

以及：

- `evidence_status`
- `evidence_reason`
- `benchmark_provenance`

`evidence_status` 允许：

- `complete`
- `partial`
- `insufficient_evidence`

---

## 5. Scientific Boundaries

Selection Evidence 不等于 Selection Skill。

例如：

一个 Episode 相对行业跑赢，不足以证明用户具有稳定选股能力。

长期 Selection Skill Estimate 必须在多个 Episode 上结合：

- 样本量
- Hit Rate
- 平均相对表现
- Payoff characteristics
- 不同市场环境
- 置信度

样本不足时必须输出：

`Insufficient Evidence`

---

## 6. Calculation Rules

具体 benchmark-relative return 计算公式不在本契约中自行定义。

实现前必须优先验证成熟金融库或公开标准方法。

LLM 不参与任何收益率、PnL 或 benchmark-relative 数值计算。

LLM 仅用于：

- 解释结果
- 总结历史决策
- 生成自然语言反馈

---

## 7. Data Failure Rules

如果出现以下情况：

- Benchmark 数据缺失
- Episode 起止时间无法匹配有效交易数据
- 行业历史归属不可确认
- 数据来源无法追溯

不得猜测或填充结果。

必须返回：

`insufficient_evidence`

并明确说明缺失原因。

# Behavior Evidence Methodology v1

## 1. Scope

本文件记录投镜 Behavior Evidence v1 当前已经实现并通过测试的方法语义。

当前 Behavior Evidence v1 包含：

- Turnover Intensity
- Portfolio Concentration
- Disposition Effect
- Loss Averaging

所有行为证据均基于确定性 portfolio replay。
金融事实不由 LLM 计算。

## 2. Replay and Look-ahead Rule

所有决策时点的历史状态均使用 strict-prefix replay：

`event_time < current_decision_time`

当前决策时点及之后的成交不得进入历史状态计算。

在当前项目锁定的 vectorbt 1.1.0、
`SizeType.Amount + longonly + raise_reject=True` 配置下，
完全平仓后的 inactive order cell 使用 `NaN` 表示跳过订单。

本项目实测中，inactive `0.0` 会进入 reduce/close 路径，
并可能触发 `RejectedOrderError: No open position to reduce/close`。
## 3. Disposition Effect

### 3.1 Realized Gain / Loss

每一笔 SELL execution 单独分类。

Realized gain/loss 使用：

`SELL executed_price`

对比该成交时点之前 strict-prefix replay 得到的
open-position average cost。

即：

- `executed_price > pre-sale average cost` → realized gain
- `executed_price < pre-sale average cost` → realized loss

不得使用 sale-day close 替代真实 SELL execution price。

### 3.2 Paper Opportunities

Paper opportunities 的 observation unit 是 distinct sale calendar day。

同一自然日存在多个 SELL timestamp 时，
paper opportunity set 只计算一次。

该日使用当天最早 SELL 之前的 strict-prefix portfolio state，
并使用 validated sale-day close 与当时 average cost 比较。

当天所有实际 sold symbols 均从 paper opportunities 中排除。

本实现是 Odean-style product implementation，
不是对 Odean (1998) 全部 tax-lot、commission、high/low 处理的完整复刻。

## 4. Loss Averaging

Loss Averaging 的 eligible event 要求：

- 当前 BUY 之前已经存在正持仓；
- 使用 strict pre-trade portfolio state；
- `BUY executed_price < pre-trade average cost`。

满足时记录为 loss averaging event。

如果：

`BUY executed_price >= pre-trade average cost`

则属于 eligible non-event。

从 0 建立的新仓不进入 eligible denominator。

Loss Averaging 不使用 same-day close 判断成交时点是否处于 loss state。

# Sample Data

本目录中的数据仅用于 Personal Investment Twin 的开发、测试和比赛演示。

## synthetic_executions.csv

这是人工构造的 synthetic demo data，不属于任何真实券商，也不包含任何真实用户交易记录。

用途：

- 验证成交记录标准化流程
- 验证 vectorbt Portfolio / Trades / Positions / PnL
- 为后续 Decision Attribution 和 Behavioral Analytics 提供最小测试输入

当前字段：

- execution_time
- symbol
- side
- quantity
- price
- fee
- currency

注意：

1. 这不是任何真实券商的交割单格式。
2. 后续真实券商 Excel / CSV 必须通过独立 Broker Adapter 映射。
3. 原始用户交易数据默认视为敏感数据，不应提交到公开仓库。
4. 不允许使用这份模拟数据证明任何真实投资收益或用户行为结论。

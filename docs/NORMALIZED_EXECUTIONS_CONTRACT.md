# Normalized Executions Contract

Personal Investment Twin 的 Broker Adapter 输出统一为 pandas DataFrame。

第一版最小字段：

- event_time
- symbol
- side
- executed_quantity
- executed_price
- fee
- order_id
- execution_id

## 语义

### event_time
实际成交发生时间。

### symbol
统一证券标识。

### side
只允许：
- BUY
- SELL

### executed_quantity
实际成交数量，不是委托数量。

### executed_price
实际成交价格。

### fee
该成交对应交易费用。

### order_id
原始订单标识；若来源文件不提供，可为空，但不得伪造真实券商ID。

### execution_id
成交唯一标识；若原始数据没有，可由 Adapter 生成内部稳定ID，并明确标记为内部ID。

## 重要原则

1. Adapter 只做字段映射、类型转换和基础校验。
2. 不在 Adapter 中计算 PnL。
3. 不在 Adapter 中重建 Position。
4. 不在 Adapter 中判断追涨、恐慌、FOMO 等行为。
5. 原始数据必须保留，以便追溯。
6. standardized DataFrame 是分析输入，不是券商事实账簿的替代品。
7. vectorbt 负责后续 Portfolio / Trades / Positions / PnL 分析。

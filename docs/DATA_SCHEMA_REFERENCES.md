# Personal Investment Twin — Trade Data Schema References

## 原则

本项目不自行发明交易成交语义。

统一交易 Schema 优先参考成熟金融系统与行业标准，并通过 Adapter 将不同券商 Excel / CSV / API 映射到内部统一格式。

## Reference 1 — QuantConnect LEAN OrderEvent

参考的核心语义：

- symbol
- order_id
- event_id
- status
- direction
- fill_price
- fill_quantity
- fee_amount
- fee_currency
- event_time

重要原则：

- Order 与 Fill / Execution 必须区分
- 一张订单可能出现部分成交
- 最终分析应以实际成交记录为基础，而不是仅使用委托记录
- 交易费用独立记录

## Reference 2 — FIX ExecutionReport

参考的核心语义：

- OrderID
- ExecID
- Side
- LastQty
- LastPx
- CumQty
- AvgPx
- OrdStatus

重要原则：

- 每笔实际成交应具有独立 execution identity
- LastQty / LastPx 表示本次成交数量和价格
- CumQty 表示订单累计成交数量
- AvgPx 表示累计平均成交价格
- 不应把订单数量直接等同于实际成交数量

## Personal Investment Twin 内部 Schema 设计原则

第一版内部标准需要能够表达：

1. 成交发生在什么时候
2. 买卖的是什么资产
3. 买还是卖
4. 实际成交价格
5. 实际成交数量
6. 交易费用
7. 订单 / 成交唯一标识
8. 币种
9. 数据来自哪个券商或文件
10. 原始记录如何追溯

## 中国券商适配原则

暂不假设所有中国券商交割单字段一致。

后续必须使用真实或官方样例逐家建立 Adapter，例如：

Broker CSV / Excel
        ↓
Broker Adapter
        ↓
Normalized Trade Schema

不得为了统一格式而丢失原始字段。

原始行必须保留 source_row / source_file 等追溯信息。

## 暂不加入

以下信息不是最小成交事实，不应塞进基础 TradeRecord：

- 盈亏结论
- 是否追涨
- 是否情绪交易
- Investor DNA
- Decision Benchmark
- AI解释
- 行为标签

这些属于后续分析层，而不是基础交易事实层。

# vectorbt 可行性验证：外部历史成交 → Trades / Positions / PnL

验证日期：2026-09-02
最终结论：**ADOPT_WITH_LIMITATIONS**

## 1. 验证边界

本次只验证开源版 vectorbt 能否作为 Personal Investment Twin 第一版的确定性分析底座，将标准化的、已经发生的历史成交合理映射为：

- Orders
- Entry Trades / Exit Trades
- Trades
- Positions
- realized / unrealized PnL
- fees
- returns

本次没有开发策略、前端、Agent、Decision Attribution、Behavioral Analytics、Investor DNA 或其他产品功能，也没有修改 `PROJECT_SCOPE.md`。

## 2. 环境与安装事实

| 项目 | 实际结果 |
|---|---|
| 用户指定项目 | `/Users/cccc/Projects/personal-investment-twin` |
| Codex 启动目录 | `/Users/cccc/Projects/investment-twin`，与目标项目不是同一目录；验证工作已切换到用户指定目录 |
| 系统 `python3` | 3.14.7 |
| 项目虚拟环境 | `.venv` |
| 项目 Python | 3.11.15 |
| vectorbt | 1.1.0 |
| vectorbt Python 要求 | `>=3.11,<3.15` |
| pytest | 9.1.1 |
| Plotly 兼容锁定 | 6.9.0 |
| 安装结果 | 成功；只安装 core 包，未安装 `vectorbt[full]`、Rust engine 或可选券商/行情依赖 |

官方 PyPI 在验证日显示 vectorbt 1.1.0（2026-07-05 发布），其项目元数据和源码 `pyproject.toml` 均声明支持 Python 3.11–3.14：

- [vectorbt on PyPI](https://pypi.org/project/vectorbt/)
- [vectorbt 1.1.0 pyproject.toml](https://github.com/polakowo/vectorbt/blob/v1.1.0/pyproject.toml)

已安装 wheel 的本地 metadata 同样报告：

```text
Name: vectorbt
Version: 1.1.0
Requires-Python: <3.15,>=3.11
```

### 安装中发现的兼容问题

`vectorbt==1.1.0` 只约束 `plotly>=4.12.0`，没有上界。直接安装时 pip 选择了 Plotly 7.0.0，但 vectorbt 1.1.0 的内置绘图模板仍含 Plotly 7 已移除的 `scattermapbox`，导致 `import vectorbt` 立即失败：

```text
ValueError: Invalid property ... 'scattermapbox'
Bad property path: scattermapbox
```

将 Plotly 固定为官方稳定版 `6.9.0` 后，vectorbt 可正常导入且依赖检查通过。`requirements.txt` 因此显式记录该兼容锁定。这是上游依赖约束缺口，不是本项目计算代码的问题。

## 3. 许可证

vectorbt 1.1.0 的实际许可证是 **Apache 2.0 with Commons Clause**，项目将其描述为 fair-code；它不是不带附加条件的 Apache-2.0。已安装 wheel 的 `METADATA` 中通用 `License` 字段为空，但 wheel 内确实包含完整 `LICENSE.md`，内容与官方仓库一致：

- [vectorbt 1.1.0 LICENSE.md](https://github.com/polakowo/vectorbt/blob/v1.1.0/LICENSE.md)
- [官方 README 的许可证说明](https://github.com/polakowo/vectorbt/tree/v1.1.0#license)

Commons Clause 的核心商业限制是：不得销售其价值完全或实质上来源于该软件功能的产品或服务。

对 Personal Investment Twin 的含义：

- 产品差异化主要来自 Decision Attribution、Behavioral Analytics、Investor DNA 等自研层，因此不必然等同于“销售 vectorbt”。
- 但“实质上来源于”的边界具有解释空间，不能把它当作普通宽松开源许可证处理。
- 商业化前必须由法务确认使用方式、分发方式和许可证通知；若不能确认，应取得作者的商业许可/例外，或换用许可证更宽松的底层库。
- 本次没有安装可选依赖；官方也提示可选依赖可能有更严格的许可证。

本节是工程风险识别，不是法律意见。

## 4. 使用和研究的官方 API

实验实际使用：

- [`Portfolio.from_orders`](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_orders)
- `Portfolio.orders`
- `Portfolio.entry_trades`
- `Portfolio.exit_trades` / `Portfolio.trades`
- `Portfolio.positions`
- `Portfolio.cash()` / `assets()` / `value()` / `returns()`
- `Portfolio.total_profit()` / `total_return()`

同时研究但没有在最小实验中采用：

- [`Portfolio.from_order_func`](https://vectorbt.dev/api/portfolio/base/#vectorbt.portfolio.base.Portfolio.from_order_func)：可用 flexible order function 在一个 bar 内生成多笔订单，但需要自定义 Numba 回调，复杂度明显更高。
- [`EntryTrades` / `ExitTrades` / `Positions`](https://vectorbt.dev/api/portfolio/trades/) 的记录生成语义。

没有发现公开、稳定的 `Portfolio.from_execution_records` 或 `Portfolio.from_order_records` 类方法。`Portfolio` 低层构造函数虽然接收 vectorbt 自己的结构化 `order_records`，但官方明确保留构造函数用于内部索引/重建，不应把它当作外部成交导入契约。

## 5. 合成成交案例

假设：

- 初始现金：100,000 CNY
- 标的：`600000.SH`
- 买卖手续费均为成交金额的 0.1%
- 成交价格与当日估值价格相同
- 无滑点、无税、无分红、无现金流、无公司行动

| 日 | 价格 | 外部已成交动作 | 手续费 | 成交后现金 | 成交后持仓 | 当日组合价值 |
|---|---:|---|---:|---:|---:|---:|
| Day 1 | 10.00 | 买入 1,000 | 10.00 | 89,990.00 | 1,000 | 99,990.00 |
| Day 2 | 11.00 | 加仓 500 | 5.50 | 84,484.50 | 1,500 | 100,984.50 |
| Day 3 | 12.00 | 减仓 700 | 8.40 | 92,876.10 | 800 | 102,476.10 |
| Day 4 | 11.50 | 加仓 400 | 4.60 | 88,271.50 | 1,200 | 102,071.50 |
| Day 5 | 13.00 | 完全平仓 1,200 | 15.60 | 103,855.90 | 0 | 103,855.90 |

人工核对：

```text
买入成本          = 10,000 + 5,500 + 4,600 = 20,100.00
卖出收入          = 8,400 + 15,600 = 24,000.00
毛 PnL            = 24,000 - 20,100 = 3,900.00
总手续费          = 10 + 5.5 + 8.4 + 4.6 + 15.6 = 44.10
最终净 PnL        = 3,900 - 44.10 = 3,855.90
最终现金          = 100,000 + 3,855.90 = 103,855.90
总收益率          = 3,855.90 / 100,000 = 3.8559%
```

vectorbt 的实际输出：

| 记录/指标 | 结果 |
|---|---:|
| Orders | 5 |
| Entry Trades | 3 |
| Exit Trades | 2 |
| Positions | 1 个已关闭 long position |
| 总手续费 | 44.10 |
| 最终现金 | 103,855.90 |
| 最终持仓 | 0 |
| 总 PnL | 3,855.90 |
| Total Return | 3.8559% |

在 Day 4 截止的开放持仓实验中：

- 已实现 PnL：1,151.033333
- 未实现 PnL（含剩余 entry fee 分摊）：920.466667
- 整个开放 Position 的累计 PnL：2,071.50

## 6. Trade matching 语义

vectorbt 的 Exit Trades 采用持仓池内的加权平均/按比例费用分摊语义，不是 FIFO tax-lot matching：

- Day 3 卖出 700：平均入场价 10.333333，分摊 entry fee 7.233333，净 PnL 1,151.033333。
- Day 5 卖出 1,200：平均入场价 10.722222，分摊 entry fee 12.866667，净 PnL 2,704.866667。
- 两笔累计净 PnL 仍为 3,855.90。

因此：组合总权益、总 PnL 和最终现金可与人工结果一致，但逐笔“已实现 PnL 属于哪一手买入”的归属可能与券商 FIFO、税务 lot 或券商自定义成本法不同。vectorbt 结果适合分析，不应未经对账就宣称等同于券商法定账簿。

## 7. 外部已成交记录是否原生支持

结论：**不是原生成交导入，但可以做有边界的合理适配。**

`Portfolio.from_orders` 的官方定义是“simulate portfolio from orders”。本实验不是让 vectorbt 根据 signal 决策，而是把每笔已发生成交的实际数量、实际价格和实际绝对手续费作为确定参数重放：

```python
vbt.Portfolio.from_orders(
    close=valuation_prices,
    size=signed_executed_quantity,
    size_type="amount",
    direction="longonly",
    price=actual_executed_price,
    fees=0.0,
    fixed_fees=actual_fee,
    slippage=0.0,
    allow_partial=False,
    raise_reject=True,
    init_cash=100_000.0,
)
```

`allow_partial=False` 与 `raise_reject=True` 很重要：如果初始现金、成交顺序或持仓历史不完整，必须失败并暴露问题，不能让模拟器静默缩量或忽略成交。

薄 Adapter 还会在进入 vectorbt 前拒绝缺失、NaN 或 Inf 的成交数量、成交价、手续费和估值价格；小数成交数量不设置整数粒度，必须原样进入 order records。单独的回归案例验证了：实际成交价可以不同于 mark price，无成交日仍按独立 mark 做 MTM，且不会把 mark 偷换成 fill price。

这一路径仍有以下本质限制：

1. vectorbt 会生成自己的内部 Order Id，不保留券商 `order_id` / `execution_id`。
2. `from_orders` 的矩阵语义是每个“时间行 × 标的列”至多一个订单。相同标的、相同时间的多笔 fill 需要由 Adapter 明确稳定排序并拆成顺序行，或改用复杂得多的 flexible `from_order_func`；本次最小 Adapter 对重复时间直接报错，避免假装无损支持。
3. 它仍执行资金、方向、最小数量等模拟约束；这不是把 broker ledger 原样装载进不可变账本。
4. 不完整历史、期初已有持仓、保证金/融资融券、T+1、结算现金、多币种等需要另行定义初始状态和账户语义。
5. 只有成交记录不足以计算连续的未实现 PnL 和 returns；还必须提供独立、可靠的估值价格序列。

## 8. 与 Broker Adapter 的映射契约

仍然需要一个非常薄的 normalized execution DataFrame。它的职责只是保留事实、做字段映射和审计追溯，不计算 Trades、Positions 或 PnL。

| 标准化字段 | vectorbt 是否直接需要 | 映射/处理 |
|---|---|---|
| `event_time` | 是 | Portfolio 行索引；相同时间多 fill 还需稳定顺序 |
| `symbol` | 是 | Portfolio 列/资产标识 |
| `side` | 间接 | `BUY` → 正 `size`，`SELL` → 负 `size` |
| `executed_quantity` | 是 | `size`，`size_type="amount"` |
| `executed_price` | 是 | `price`，不是 signal 或 bar close 生成的成交价 |
| `fee` | 是 | 已发生的绝对费用映射为 `fixed_fees`；vectorbt 的 `fees` 参数是成交额比例 |
| `order_id` | 否 | 必须在 Adapter/事实表保留；vectorbt 内部记录不会保存 |
| `execution_id` | 否 | 必须保留，用于幂等、去重和审计；vectorbt 不保存 |
| `fee_currency` / 交易币种 | 否 | 必须保留；进入 vectorbt 前需确认或换算到组合现金币种 |
| broker/source/source file/source row | 否 | 必须保留，保证原始记录可追溯 |
| valuation/mark price | 另需 | 独立价格序列，用于未实现 PnL、净值和 returns，不应伪装成成交事实 |

不需要创建大型 TradeRecord ORM。当前 `src/core/vectorbt_validation.py` 只实现上述最薄映射，并把计算全部交给 vectorbt；它还故意限制为单标的、每时间点一笔成交，避免超出本次验证证据。

## 9. 自动测试

执行命令：

```text
.venv/bin/python -m pytest -q
```

实际输出：

```text
................                                                         [100%]
16 passed in 1.99s
```

- Passed：16
- Failed：0
- Warnings：0

测试覆盖：

1. 最终现金。
2. 最终持仓。
3. 加仓、减仓、再加仓、完全平仓的逐日持仓路径。
4. 总费用与人工净 PnL。
5. 开放 Position 的 realized / unrealized PnL。
6. Orders、Entry Trades、Exit Trades、Positions 与 returns。
7. 实际 fill price 与独立 valuation mark 的分离，以及无成交日的 MTM。
8. 小数成交数量不会被取整或静默丢弃。
9. 成交事实与估值中的 NaN / Inf 会立即失败，不会被估值价或 0 替换。
10. 两次重放的记录、现金和净值完全一致。

## 10. 能力判断

| 能力 | 判断 | 边界 |
|---|---|---|
| Orders | 适合表达重放后的 filled orders | 不是券商原始 order/execution 仓库；丢失外部 ID |
| Trades | 可采用 | 是 vectorbt 根据订单推导的分析 Trade，匹配语义需接受或对账 |
| Positions | 可采用 | 完整、按序、可解释的成交历史下可重建；期初持仓和跨零/做空需额外规则 |
| realized PnL | 可采用但有限制 | 组合累计结果可靠；逐 lot 归属可能不同于券商 |
| unrealized PnL | 可采用 | 必须另外提供估值价格序列 |
| fees | 可采用 | 绝对已发生费用用 `fixed_fees`，币种必须先处理一致 |
| returns | 可采用 | 需要估值价格和正确现金流；单靠 executions 不够 |
| Sharpe / max drawdown 等 | vectorbt 已有成熟能力 | 本次没有重复实现，也没有扩展验证 |
| Decision Attribution 的底座 | 可作为计算输入层之一 | Attribution 必须继续引用外部 execution IDs 和 normalized facts，不能只依赖 vectorbt 记录 |
| 券商官方账簿/税务账簿 | 不适合 | 不应作为 system of record 或法定对账引擎 |

## 11. 未解决问题与采用条件

采用前必须完成：

1. 用至少一家目标券商的匿名/合成金样本，对现金、持仓、手续费、逐日净值和券商 PnL 做 golden reconciliation。
2. 明确成本法：产品是使用 vectorbt 加权平均分析语义，还是必须复现某券商/FIFO/tax-lot 语义。
3. 定义相同时间多 fills、部分成交、跨标的 cash sharing 和严格执行顺序。
4. 定义期初持仓、现金存取、分红、拆并股、税费、转托管、多币种及融资融券的处理边界。
5. 保留 normalized execution DataFrame 作为事实与审计 sidecar；绝不能只保存 vectorbt 派生记录。
6. 在升级 vectorbt/Plotly 前执行导入测试与本套 golden tests，避免依赖解析再次选择不兼容版本。
7. 商业化前完成 Commons Clause 法务审查；未获确认前，不应把生产采用视为已批准。

## 12. 最终结论

**ADOPT_WITH_LIMITATIONS**

技术上，vectorbt 1.1.0 可以通过 `Portfolio.from_orders` 将规范化的外部已成交数量、价格和手续费做确定性重放，并可靠产生本案例的 Orders、Trades、Positions、PnL、fees 和 returns。它足以作为第一版的分析型 portfolio engine 候选，避免自研基础持仓和盈亏计算。

但它没有原生、无损的 broker execution import API，也不会保留券商订单/成交 ID；其 trade matching 不是券商通用账簿语义，连续 returns 还依赖估值与现金流数据。再加上 Commons Clause 的商业许可证风险，建议是：**将它放在薄 Adapter 后作为分析引擎候选，不作为事实仓库或券商账簿；许可证获确认且真实券商金样本对账通过后，才进入第一版生产架构。**

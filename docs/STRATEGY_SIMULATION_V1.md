# 策略历史模拟 V1：完整策略规格与独立模拟引擎

> 表达力演进路线（L1 参数 → L2 积木 → L3 强积木 → L4 公式 → L5 代码）已锁定，
> 见 `docs/STRATEGY_LADDER.md`（架构决策记录）。

状态：设计 + 首阶段实现说明。分支 `zhipu/strategy-engine`，基线 `ccc59f5`。
本文档是策略模拟（用户 2026-09-11 指令中的第 1、2 步）的规格与选型记录；对比展示与学习功能是后续阶段。

## 1. 定位与边界

- 本模块是"把一套参数固定、来源标注清楚的完整策略，放进历史股票池独立执行"的教学与自查工具。
- 它与用户真实账户事实（`canonical_executions`、回放持仓）完全隔离：策略有自己的现金、持仓、成本、订单、成交与净值；不读取、不覆写真实账户数据。
- 与 `PROJECT_SCOPE.md` §4 的关系：该文件把"自研完整回测引擎"列为比赛第一版（v1）明确不做。用户 2026-09-11 指令明确要求完整策略历史模拟，本分支按新指令执行；本模块仍遵守其精神——不做自动荐股、不做次日预测、不做实盘下单、所有金融数字由确定性代码产生、AI 只解释有出处的结果。合成数据永远不能用于宣称真实业绩（沿用 `data/sample/README.md` 边界）。
- 引擎是全增量模块：`src/strategy/`、`scripts/build_strategy_universe_fixtures.py`、`scripts/run_strategy_simulation.py`、`tests/test_strategy_*.py`。不修改现有 Lens、回放、投影代码。

## 2. 成熟引擎验证结论（2026-09-11 实测）

按交接要求逐一验证，证据如下：

| 引擎 | 许可（已核实原文） | 本机运行条件（已实测） | A 股适配 | 结论 |
|---|---|---|---|---|
| QuantConnect LEAN | 仓库 `LICENSE` 为标准 Apache-2.0，无附加条款 | 本机无 .NET SDK、无 Docker（`which dotnet`/`which docker` 均为空）；本地跑引擎必须先装系统级依赖（需另行授权） | 交易日历、T+1、涨跌停、整手、印花税/佣金、数据格式（LEAN CSV/zip）全部要自写 reality model；桌面分发还要捆绑 .NET 运行时，与现有 PyInstaller Python sidecar 架构冲突 | 采纳其**架构**（Universe → Alpha → Portfolio Construction → Risk → Execution → Reality Model 分层、信号/订单/成交分离）；本阶段不作为运行时。若获得安装 .NET/Docker 的授权可再评估 |
| RQAlpha | 非 Apache：自定义双许可，原文"未经米筐科技授权，任何个人不得出于任何商业目的使用本软件"，且法人"不得出于任何目的使用" | — | — | **排除**。不复制、不集成其代码 |
| Backtrader | GPL-3.0 | 长期未维护，新版 Python 兼容性存疑 | 需自写 A 股约束 | GPL 传染义务与闭源桌面 sidecar 分发冲突；不采用 |
| vectorbt 1.1.0（已在 requirements） | Apache-2.0 **with Commons Clause**（`docs/VECTORBT_FEASIBILITY.md` §3 已记录） | 已装可用 | 向量化语义难表达逐单拒单理由、T+1、拆股事件 | 保留现有"重放已发生成交"用途；不做策略模拟核心——策略模拟的价值主要来自模拟本身，会加重 Commons Clause "实质上来源于该软件" 的风险 |

**选型决定**：本阶段自研一个小型确定性日频事件引擎（纯 Python + pandas/numpy，零新依赖），架构照 LEAN 分层。理由：三个成熟引擎分别被系统依赖（LEAN）、许可（RQAlpha/Backtrader）、许可+语义（vectorbt）挡住，而被挡住之后剩下的 A 股 reality model（恰恰是复杂度主体）任何方案都要自己写；自研部分规模可控（日频、单现金账户、long-only），且最容易满足"逐单可解释、可对账、可重跑一致"的验收标准。

## 3. 数据：合成历史股票池（点时可得）

新数据集 `data/sample/strategy_universe/`，与真实行情合约（`src/market_data`）完全隔离，`is_synthetic=true`：

- `universe.csv`：`instrument,display_name,list_date,delist_date` —— 点时成员资格：上市日前不可选、退市日后移除。
- `prices.csv`：`date,instrument,open,high,low,close`（未复权口径的工作日日线）。某标的某日缺行 = 当日不可交易（停牌/缺失），估值取最后有效收盘。
- `corporate_actions.csv`：`instrument,ex_date,action,ratio`（V1 只支持 `split`）。
- 由 `scripts/build_strategy_universe_fixtures.py` 确定性生成（waypoint 插值 + 序数哈希扰动，无随机数），含 16 只合成标的、3 年窗口，覆盖：趋势上行/震荡/阴跌/突破回落/长期横盘、中途上市、上市约两年即退市（合成九号：工程化拉升确保入场后停牌至退市，使演示运行确定性地覆盖强制清仓路径）、停牌段、1:2 拆股、数据缺口。
- 声明：合成交易日历按工作日枚举，不是真实交易所日历；价格与任何真实证券无关。

## 4. 策略规格 T1 v1：突破趋势（完整版）

`strategy_id = toujing_t1_breakout_trend`，`version = "1"`。规则来源分两类标注，绝不冒充经典名家策略：

**来源 A：现有 Decision Lens 规则升格为完整策略（原口径不变）**
| 编号 | 规则 | 口径 |
|---|---|---|
| A1 入场趋势过滤 | 前有效收盘 > SMA20 | 与 `trend_ma20` 相同：最近 20 个有效日收盘均值 |
| A2 入场突破 | 收盘严格高于此前 20 个有效收盘高点 | 与 `closing_breakout20` 相同 |
| A3 信号退出 | 收盘跌破此前 10 个有效收盘低点 | 与 `closing_breakout20` 退出条件相同 |

**来源 B：为"完整执行"新增的适配规则（文档与代码中显式标注，参数可版本化）**
| 编号 | 规则 | 默认参数 |
|---|---|---|
| B1 股票池 | 全部点时上市且有效收盘 ≥ 21 个的成员 | `min_history = 21` |
| B2 选股排序 | 候选数超过剩余仓位时按突破强度（close/前 20 高 − 1）降序，平局按 instrument_id 升序 | — |
| B3 仓位管理 | 等权：每仓目标金额 = 当前总净值 × 25%；最多同时 4 仓；按 100 股整手向下取整；不足 1 手金额 → 拒单 | `max_positions=4`，`position_fraction=0.25`，`lot_size=100` |
| B4 加仓 | **不加仓**（每个标的同一时间至多一个仓位；不加仓是完整规则，不是缺失） | — |
| B5 止损 | 入场价 × (1−8%) 的硬止损，逐日盘中检查 | `stop_loss_pct=0.08` |
| B6 冲突优先级 | 同日同标的：退出/止损 > 入场；同日先执行全部卖出、后买入（卖出资金当日可用） | — |
| B7 订单类型与有效期 | 市价单、当日有效（GFD）、次日开盘成交；未成交原因必须记录 | — |
| B8 费用 | 佣金 0.03%（最低 5 元）双边 + 印花税 0.1% 仅卖出 | `commission_rate=0.0003`，`min_commission=5.0`，`stamp_duty_rate=0.001` |
| B9 滑点 | V1 固定 0（参数存在，默认关闭） | `slippage_rate=0.0` |

## 5. 执行模型声明（不虚构日内精度）

日频数据下日内先后顺序未知，以下为声明模型，全部写入逐日日志：

1. **收盘信号 → 次日开盘成交**：t 日收盘后产生信号与订单，t+1 开盘价成交；不用同一根已知收盘价成交。
2. **日内止损**：t 日 `open ≤ stop` → 按开盘价成交（跳空，对策略更差）；否则 `low ≤ stop` → 按 stop 价成交。假设"开盘先于止损触发"。
3. **涨跌停**：开盘价 ≥ 涨停价（前收 × 1.10，四舍五入 0.01）→ 买入拒单 `limit_up_open`；卖出不建模一字跌停排队（声明局限）。
4. **T+1**：当日买入份额当日不可卖。引擎日内顺序为"卖出 → 止损 → 买入"，止损检查先于买入，因此止损最早发生在买入次日的盘中——T+1 由结构保证。
5. **停牌/缺失**：当日无 bar → 无信号、不可成交、挂单过期取消 `suspended_expired`；估值用最后有效收盘。
6. **退市**：`delist_date` 开盘以最后有效收盘价强制清仓（`delisting_forced_liquidation`），保证账户终态全现金、净值完整。
7. **拆股**：除权日开盘前调整持仓（数量 ×ratio、成本 ÷ratio、现金不变）；该标的当日未成交挂单作废 `corporate_action_reset`；信号使用拆股因子调整后的价格序列，成交与估值用原始价格。
8. **窗口口径**：信号窗口数"有效收盘观察"个数，非自然交易日数（与 Lens 既有口径一致）。

## 6. 引擎架构（`src/strategy/`）

```
data.py        加载与校验三张 CSV → 不可变 SimulationData
universe.py    point_in_time_universe(as_of) → 当日可选标的
signals.py     SMA / 前 N 有效收盘高低温 / 突破强度（纯函数）
account.py     StrategyAccount：现金、持仓(数量/成本/T+1 可卖量)、fill/split 应用、估值
execution.py   开盘撮合（限价检查、停牌过期）、止损撮合、费用、拒单理由码
strategies/t1.py  T1 信号 → 订单（含排序与理由）
engine.py      逐日循环：开盘撮合 → 止损 → 估值 → 收盘信号；全部确定性
metrics.py     标准绩效指标套件（纯函数，无法定义时输出 null）
report.py      JSON 安全序列化 + 汇总（收益、最大回撤、成交/拒单统计）
```

产出 schema（`strategy_simulation.v1`）：策略与参数版本、数据指纹、逐日日志（选股理由、信号、订单、成交/拒单、现金、持仓、净值、回撤）、订单与成交全路径、汇总指标。`enrich_summary` 在汇总上追加 `summary.performance_stats`（`src/strategy/metrics.py`，对齐 quantstats/empyrical 常用指标集）：年化波动率、Sortino、Calmar、盈亏比（profit factor，基于已闭合回合，无亏损回合时为 null）、平均/最大单笔盈亏、等权买入持有基准年化与描述性超额年化；每项定义随数据一起传输到 UI 原样展示。全部年化使用 252 交易日因子，与既有年化收益/Sharpe 一致；指标无法定义时输出 null（诚实的缺失值），绝不以 0 代替。`definitions` 字典覆盖 Sortino/Calmar/盈亏比/超额/年化因子五项；年化波动、Sharpe、单笔盈亏与基准年化沿用同一套约定，未单独附定义。落盘 `data/sample/strategy_universe/t1_v1_result.json`（可由脚本重生成）；运行脚本同时写入裁剪版桌面产物 `apps/desktop/src/generated/strategy-simulation-demo.json`（摘要 + 逐日净值 + 订单/成交全路径），由桌面端"策略历史模拟"页（`/strategy-simulation`）静态加载展示；浏览器端只做传输校验与账目一致性检查，不计算金融数值。

## 7. 首个验证目标

**T1 v1 在上述合成股票池上完整独立跑通**：初始现金 100 万 CNY，产出独立账户的逐日净值与回撤、完整订单/成交/拒单路径（每条含理由），并通过最少测试清单：

1. 现金、持仓与费用对账（手工 golden 数字，含最低佣金）。
2. 多个证券共享现金（并发持仓、现金不足时按序缩量/拒单）。
3. 选股历史边界（上市前/退市后/历史不足不可选）。
4. 修改未来数据不影响过去订单（价格文件后段变动 → 前段日志逐字节不变）。
5. 公司行动/缺失数据（拆股对账、停牌与数据缺口）。
6. 订单拒绝/部分成交（涨停拒单、现金不足拒单、挂单过期；入场缩量模型）。
7. 冲突优先级（同日退出与入场、卖出资金当日可用）。
8. 重复运行一致（两次运行 JSON 相等）。

回归门：现有 Lens/投影/product runtime 22 项定向测试保持通过；真实账户事实与既有展示不受影响。

## 7b. 同标的对比（第 3 步，进行中）

`src/strategy/compare.py`（schema `strategy_comparison.v1`）：把 T1 v1 同一套规则在单标的自身 OHLC 历史上独立重放（`simulation_data_from_bars` 直建模拟数据），与该标的的规范成交并列。关键声明：窗口"净现金流" = 买入流出 − 卖出流入（含费用），窗口末仍有持仓时它主要是持仓成本而非盈亏；规则侧按策略自身仓位参数开仓，金额量级与记录侧不同，**不可直接相减为优劣**；合成隔离（SYN 前缀双向强制）；close-only 数据源 fail-closed（规则重放需要 OHLC）。示例导出 `scripts/export_strategy_comparison_demo.py` → `apps/desktop/src/generated/strategy-comparison-demo.json`（5 个示例 episode + 组合并列），策略模拟页新增「示例 Episode 对照」区块。待做：episode 图上规则买卖点叠加、真实账户 runtime 链路、CSV/akshare 行情接入。

## 8. 局限（当前明确不做）

合成数据不模拟真实交易日历、除拆股外的公司行动（分红/送股/配股）、印花税历史税率调整、一字板排队、盘口深度；滑点默认 0。策略绩效不代表任何真实市场可得结果，不得对外宣称。UI 叠加策略净值路径、与用户真实历史的并列对比、逐笔差异与教学、AI 解释均为后续阶段，本阶段不实现。

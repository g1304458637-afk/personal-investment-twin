# 三种对比：展示版实现与验收

日期：2026-09-07。基线 HEAD：`0ef7856`。本轮不 commit / push；此前工作区改动保留。

## 现在可以使用

| 入口 | 已接通的内容 | 数据身份 |
| --- | --- | --- |
| `#/comparison/history` | 同一研究账户的前后两期收益、净值、回撤、期末配置/穿透、操作及行为统计；次级视角保留原 Self 的 3m / 12m / lifetime | 两期比较为新独立 Synthetic 研究账户；个人历史仍只读原来同一 subject/account 的证据 |
| `#/investments/compare-example` | A/B 完整投资期结果、共同价格、双操作轨道、数量/平均成本切换、已核对的差异定位、A/B 分析上下文选择 | 原有 SYN_COMPARE_A/B；不修改旧同股计算 |
| `#/comparison/professional` | 均衡/集中两种研究组合，三种共同期间；收益/回撤/波动、资金配置与穿透、记录操作和行为并列 | 三组完整 Synthetic 账户，不是真实专业人士、基金经理业绩或专业人群分布 |

页面保持现有透明玻璃风格，所有结果来自 Python 导出。真实账户模式必须主动打开独立研究示例，不会将示例结果归属到当前真实账户。

## 数据流与文件

`study_inputs → existing replay/builders → performance/period/lookthrough projections → account comparison → deterministic JSON → frontend adapter → ECharts/UI`

- `src/performance/account_series.py`：账户绩效序列与明确估值边界的外部资金流 TWR。
- `src/compare/periods.py`：窗口内已有行为结果的汇总。
- `src/compare/lookthrough.py`：带日期和来源的基金穿透、合并与分类。
- `src/compare/account_comparison.py`：校验可比口径，输出同单位差额及共同底层资产。
- `src/compare/research_demo.py`：固定成交/价格/成分输入及三组研究账户，不在前端填金融结果。
- `scripts/export_comparison_demo.py` → `apps/desktop/src/generated/comparison-research-demo.json`。
- `apps/desktop/src/data/comparisonResearch.ts`、`comparisonResearchDemo.ts`：校验范围并转换为稳定 View Model，不重算金融指标。
- `apps/desktop/src/components/comparison/`：共享结果、净值/回撤、配置/穿透双图、操作详情、双语文案与样式。
- `apps/desktop/src/workspace/ResearchComparisonStudy.tsx`、`SelfComparisonWorkspace.tsx`、`ProfessionalComparisonWorkspace.tsx`：三种对比的页面接入；配套独立 copy/CSS。
- `SameStockComparePage.tsx`、`SameStockComparisonPanel.tsx`、`SameStockTimeline.tsx` 与 `sameStockCompareCopy.ts`：已有同股事实的展示与选择改进。

新增 Python 测试：`test_account_performance.py`、`test_account_comparison.py`、`test_comparison_periods.py`、`test_comparison_lookthrough.py`、`test_comparison_research_demo.py`。

前端测试：`comparisonResearch.test.mjs`、`researchPortfolioComparison.test.mjs`、`sameStockUI.test.mjs`、`selfComparisonWorkspace.test.mjs` 及已有入口测试。

## 新派生方法与准确语义

| 方法 | 版本 | 约定 |
| --- | --- | --- |
| `account_fixed_cash_twr_empyrical_v1` | `1.0.0` | vectorbt 账户价值，现金固定；收益/NAV/回撤复用 vectorbt/empyrical |
| `account_external_flow_twr_exact_boundary_empyrical_v1` | `1.0.0` | 调用方提供权威流前/流后估值与账户内外资金流身份；逐段连接，不新增现金账本 |
| `calendar_period_behavior_v1` | `1` | `(start_date, end_date]`，保留窗口之前的完整持仓状态 |
| `dated_fund_lookthrough_v1` | `1` | 直接 + 各基金间接持有；实际使用版本的有效/公开/观察时间均受 as_of 限制 |
| `account_period_factual_comparison_v1` | `1` | 同方法/币种/数据层级；专业比较同观察日期，自我两期同账户且不重叠 |

- 日级期间边界拒绝非午夜时间及带时区输入；这不是盘中可用价格分析。估值取该 calendar date 实际最后一条 replay 状态，canonical 成交顺序不变。
- 起始日收盘状态作为基线，期间动作/费用计入其后至终止日；不能只截成交、从空仓重算。两期共享的边界日只作后一期间起点。
- 必须有准确起止日期估值，不用其他日期代替。缺价格不补值，稀疏日期不冒充完整交易日历。
- 净值基准为 100；最大回撤卡片用正幅度，回撤曲线非正。恢复日取该最大回撤此前高点恢复日期。
- 年化统计必须使用显式、完整等频观测及样本门槛。本例是声明的 Synthetic 工作日序列，非真实交易所日历。没有无风险收益输入，不展示 Sharpe。
- HHI 复用现有不含现金定义；配置扇形图含现金。没有将穿透后权重代入旧 HHI 方法。
- 日均换手直接聚合现有 daily observations。Disposition 只相减前缀的 additive counts 再复用原结果方法，不相减比例；Loss Averaging 按既有合格事件窗口汇总。
- 收益差使用百分点；页面明确 `右侧 − 左侧`。无综合分、跨单位排名或因果归因。
- 穿透保留未知/未覆盖份额，不重新归一化；嵌套有深度上限，循环不无限展开。实际使用披露日期进入结果与 hash，比较 ID 包含双方 lookthrough ID。
- 同股页面仍展示双方各自完整期 PnL/Return；共同区间只比较已记录过程，不改为共同期收益。

## JSON / View Model

独立 JSON schema：`comparison_research_demo_v1`，顶层 `data_tier=synthetic`。

主要内容：`as_of`、`currency`、`default_subject`、`names`、`accounts[].periods.{earlier,recent,full}`、`comparisons.self`、`comparisons.professional[subject][period]`、`capabilities`。

每个 period 包含 `performance`、`behavior`、`allocation`、`operations`、`benchmark`。比较对象保留双方账户/日期、方法引用、单位明确的差额。前端只做类型/范围校验、格式化、排序和图表交互，不计算 HHI、PnL、TWR、百分位或归因。

基金披露日期与行业分类日期分别处理，不用行业分类发布时间冒充基金披露时间。基金来源精确信息留在数据；页面只显示易读的成分截止与披露日期。

## 尚未实现的计划项

这是完整数据假设下的可运行研究展示版，不是整个长远产品计划均已完成。

- 券商接入、真实专业对象资料、真实全账户绩效输入仍待接口阶段；未扩大原 Episode 分享授权。
- 外部资金流绩效已有独立权威估值输入层和测试；尚未把入出金、分红、拆股、证券转入转出接进现有 replay。没有另写会计引擎绕过此缺口。
- 未将跨期 Episode PnL 相加成为任意期间分项贡献；分项收入/费用归属及百分比 linking 需独立会计合同。
- 后端保留行业/地区分类汇总，本版主图为直接/底层资产配置；行业/地区专用交互和期间仓位演变后续补齐。
- 研究操作可查看同一笔真实生成的数量/成本变化，未伪造其在真实账户中的 Episode 路由。
- 全账户比较结果还未接入新的 Agent 工具视图。保留已有同股 Agent/验证链；本轮没有发送新研究账户到模型、没有改 ClaimOption 或 EvidenceRecord。

## 验证记录

- Python full regression：**871 passed**。
- Desktop Node：**238 passed**。
- `npm run check`、`npm run build`、`cargo check`、`git diff --check`：通过。
- Vite 有大 chunk 提示（包括 Synthetic payload/ECharts），无构建错误；未通过提高阈值隐藏提示。
- 连续两次重建的 bytes 与磁盘生成文件完全一致。SHA-256：`1e8f6074e4bff64550311c59ea67f2f11f4ceca38c28153cf960cb100c2d56fc`。
- 浏览器实际验证：真实账户无数据的显式研究入口、自我双时期/个人历史窗口、同股 A/B + 数量/成本、专业对象和期间选择、差额图表定位、穿透持仓/披露日期、操作详情、中英文。英文页面无横向溢出。
- 最终页面检查未见新阻塞错误；开发过程早期的热更新/legend 错误已修复。本轮未声称重新验收发布态 Tauri app 或真实 DeepSeek 调用。
- 开发服务器：`http://127.0.0.1:1420`，strict port 1420，保持运行。

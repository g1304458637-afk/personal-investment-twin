# 投镜 Frontend Product Architecture & Design System v1

状态：**Proposal — 待产品确认，不作为已实现行为**

基线：`c5dda4b feat(self): expose self historical comparisons in desktop`

审计日期：2026-09-04

范围：Desktop 产品架构、信息架构、设计语言和渐进迁移计划。本文不改变金融计算、Evidence Contract、Twin/Self 语义或现有路由。

## 1. Executive decision

投镜应从“按内部模块陈列功能”转成“按用户任务与金融对象组织工作区”。推荐的一级产品域是：

1. **总览**：现在有什么值得我知道？
2. **我的投资**：我实际上经历了什么？
3. **复盘**：我的决策与投资方式有哪些可验证的观察？
4. **我的投镜**：现在的我是什么状态，和过去有什么变化？
5. **决策前**：这次拟交易会怎样改变我的已知状态？
6. **数据与账户**：数据从哪里来，是否完整、同步和获授权？
7. **设置**：如何控制应用行为？

其中“设置”位于侧栏底部的辅助区；“数据与账户”只在真实导入、账户、同步、数据质量或授权能力 ready 后显示，而不是把 roadmap 当成产品入口。Evidence 不再作为一级产品入口；它通过上下文检查器和 Advanced 路由保留完整可追溯能力。Agent 是全局上下文面板，不是另一个 Dashboard。未来 Peer 进入“我的投镜”的比较上下文，不新增一级菜单。

Desktop 采用稳定的三层结构：

```text
Product Sidebar  |  Task / Object Content  |  Contextual Inspector
产品域导航          当前问题与金融对象          Evidence / Method / Details
```

这不是一次换皮。关键变化是把 `Position Episode → Decision Event → Evidence → Method` 变成全产品的主下钻模型，并把技术名词推迟到用户主动查看依据之后。

## 2. Current state audit

本次实际检查了 `App.tsx`、`WorkspaceShell.tsx`、导航定义、所有一级页面、Position Episode、Evidence Inspector、Agent Panel、locale、数据 adapter 和 `index.css`，并在运行中的 Desktop 页面逐项浏览交互状态。

| 当前页面/表面 | 用户真正要解决的问题 | 当前展示 | 重复或工程暴露 | 建议归属 |
| --- | --- | --- | --- | --- |
| Overview | 我现在最需要知道什么？ | 组合快照、资产曲线、Ask Twin 宣传、4 项决策证据、4 项行为证据、Evidence ID/Method | 复制 Decisions、Behavior、Evidence；首页像模块样品柜 | 保留一级，重写职责为“值得注意的当前状态与变化” |
| My Twin | 现在的我是什么状态，和过去有什么变化？ | 时点快照、Self vs Past、开放/结束 Episode、Evidence 列表、成熟度、未知项、技术详情 | Episode 列表与“我的投资”重叠；Evidence 列表与“复盘/证据”重叠 | 保留一级，只承担个人时点状态、变化与证据成熟度 |
| Decisions | 我做过哪些投资决策，它们有什么证据？ | Episode 列表、Selection/Sizing/Exit/Friction、趋势与方法元数据 | 同页混合“投资经历入口”和“决策证据”；名称是内部模块语言 | 拆分：Episode 进入“我的投资”；证据进入“复盘 → 决策” |
| Behavior | 我的记录中出现了哪些投资方式？ | HHI、Turnover、Disposition、Loss-state Addition、历史序列、方法边界 | 与 Review/Twin 有内容关系，不是独立一级用户任务；直接暴露指标模块 | 移入“复盘 → 投资方式” |
| Compare | 我与过去、同类或某个用户有何不同？ | Self vs Past、Synthetic Cohort、未连接的用户比较 | Self vs Past 复制 My Twin；未成熟能力占据一级入口 | 暂时移除一级；Self vs Past 回 My Twin，Peer 完成后进入 Twin 比较上下文 |
| Decision Check | 如果按输入交易，已知组合状态会怎样变化？ | Proposed Trade、Before/After、Self/Peer context、离线/本地 runtime 边界 | 职责清楚，区别于事后复盘；名称略偏系统功能 | 保留一级，用户语言改为“决策前”或“交易前检查” |
| Evidence | 系统的某项观察基于什么？ | 搜索、筛选、EvidenceRecord、Method ID、来源、限制 | 是高级审计工具，不是大多数用户的一级任务；UUID 成为视觉主体 | 从一级移除；上下文入口优先，保留 `Advanced / Evidence & Methods` |
| Position Episode | 这一轮持仓从建仓到结束/当前如何发展？ | 生命周期、真实成交点、决策事件、前后 replay state、Evidence 引用 | 对象链正确，但挂在 `/decisions` 之下使归属错误 | “我的投资 → Investment Episode”核心详情 |
| Evidence Inspector | 为什么系统这样描述？怎么算？ | 解释、计算、方法、来源、限制 | 渐进披露方向正确；目前不同详情仍有 Evidence Detail/Inspector 两种面板 | 成为统一 Contextual Inspector 的证据模式 |
| Settings | 如何控制应用行为？ | 语言、主题、隐私、数据连接、Peer/Compare 假开关、状态展示 | 混入 Data/Accounts、未来 consent 与组件 showcase | 只保留应用偏好；数据、授权、导入迁移到“数据与账户” |
| Ask Twin | 基于当前对象如何提问？ | 全局 Sheet、固定 Demo Episode、能力未连接、Orb 状态预览 | 入口位置合理，但上下文被硬编码，当前像 UI showcase | 保持全局入口；未来由 active context 注入对象引用 |
| Sidebar / Top bar | 我在哪，如何去主要任务？ | 8 个同级技术模块、单一“反思”分组、命令面板、主题、Ask Twin | 主要反映开发包，而非用户心智；辅助与核心任务同权 | 收敛为 5 个核心域 + 2 个辅助域；标题栏承担对象上下文和局部操作 |

### 2.1 Current shell strengths

- 固定 Sidebar、Top bar 和独立滚动 Main 已具备稳定 Desktop 基础。
- 命令面板、主题切换、全局 Ask Twin 位置清楚。
- Sheet、Dialog、Tabs 等基于可访问 primitives；键盘 focus 和 reduced motion 已有基础。
- Position Episode 与 Evidence Inspector 已证明“对象 → 事件 → 依据 → 方法”可行。
- Synthetic / Demo 标识持续可见，且数值主要已来自 deterministic generated payload。

### 2.2 Current shell weaknesses

- 所有模块获得相似视觉权重，用户看不到“对象、任务、证据”的层级差异。
- 首页通过复制模块卡片来表现完整，反而增加认知成本。
- `Evidence`、`Behavior Evidence`、`Decision Attribution` 等实现术语出现在第一层。
- 页面各自发展出局部布局和样式；`index.css` 已达约 2,441 行、约 359 个顶层 class selector，Twin/Self/Peer/Episode 等有成片页面专用规则。
- GlassPanel 被同时用作页面容器、指标、说明、状态和对象边界，造成 Card Soup。
- 右侧 Sheet 已存在，但尚未形成跨页面一致的 Contextual Inspector contract。

## 3. Current problems

当前产品看起来像“功能集合”而不是完整产品，根因不是颜色或圆角，而是以下结构性问题：

1. **导航映射代码包，而非用户任务。** Decision、Behavior、Evidence、Twin、Compare 以实现模块并列。
2. **对象归属错误。** Position Episode 是投资经历，却被挂在 Decision 下；Evidence 是依据，却与业务域并列。
3. **页面边界不互斥。** Overview、My Twin、Compare 都在回答“现在与过去”；Overview、Decisions、Behavior 又重复证据摘要。
4. **详情层不稳定。** 有整页、Sheet、Drawer、展开区多种方式，用户无法预测“点击后去哪里”。
5. **技术深度过早。** Method ID、Evidence ID、N、CI、schema/code version 在普通阅读层抢占注意力。
6. **未来能力用空页面占位。** User Compare、Peer consent 和 Agent runtime 尚未连接，却影响主导航和 Settings。
7. **视觉容器替代信息层级。** 大量 Card 让所有内容都显得独立且同等重要。

## 4. Reference review

所有参考均为源码/规范级阅读，不复制品牌资产或实现代码。AGPL 项目只借鉴架构思想，不复制代码，也不作为 runtime dependency。

### 4.1 Actual Budget

- Repository：<https://github.com/actualbudget/actual>
- 审计快照：`eea17e5`；License：MIT。
- 实际阅读：`PRODUCT.md`、`DESIGN.md`、`packages/desktop-client/src/components/sidebar/Sidebar.tsx`、`PrimaryButtons.tsx`、`Accounts.tsx`、`CommandBar.tsx`、`FinancesApp.tsx`、`components/transactions/TransactionsTable.tsx`、`components/reports/ReportsDashboardRouter.tsx`、`packages/component-library/src/tokens.ts`、`theme.ts`。
- 它解决的问题：高频个人财务工作既要有足够密度，又不能牺牲数字可信度；账户是稳定对象，Budget/Reports/Schedules 是稳定任务，低频设置收进 More。
- 投镜借鉴：`numbers are the interface`；一个克制 accent；语义 token；侧栏可调整/隐藏；账户对象直接出现在导航上下文；Command Bar 与主导航共用信息来源；“日常路径快、细节渐进”。
- 不借鉴：Budget 的表格密度、Electron 架构、Envelope Budget 业务结构；Actual 明确反对 glassmorphism，而投镜保留品牌玻璃语言，但应接受它对克制和可读性的约束。
- 对 IA 的影响：减少一级菜单、把金融对象置于技术模块之前、让数字与列表承担主要结构而不是装饰容器。

### 4.2 Rotki and `@rotki/ui-library`

- Repositories：<https://github.com/rotki/rotki>、<https://github.com/rotki/ui-library>
- 审计快照：Rotki `6552ba7`；UI Library `84cd3c9`；两者 License：AGPL-3.0。
- 实际阅读：`frontend/app/src/types/router.d.ts`、`modules/shell/layout/use-navigation-menu.ts`、`NavigationMenu.vue`、`NavigationMenuGroup.vue`、`NavigationMenuLink.vue`、`AppSidebars.vue`、`PinnedSidebar.vue`、`pages/dashboard/index.vue`、`modules/dashboard/Dashboard.vue`、Dashboard table/history modules；UI Library 的 `src/theme/index.ts`、`styles/colors.css`、`consts/typography.ts`、`RuiDataTable*`、`RuiTableEmptyState.vue`、`RuiNavigationDrawer.vue`、`RuiTabs.vue`、`RuiAlert.vue` 及相应 tests/stories。
- 它解决的问题：大量金融账户、历史事件、报告和设置需要共享路由元数据、统一表格行为、明确 loading/empty 状态，以及可停靠的次级上下文。
- 投镜借鉴：路由旁声明导航元数据并由单一来源生成 Sidebar/Command Palette；表格的排序/分页/展开/空状态是组件 contract；可折叠、可调整宽度、可保持上下文的右侧 rail；主题、文字、surface、status 使用语义层。
- 不借鉴：加密协议、链账户、税务会计流程的导航规模；24 级 elevation 等过宽 token 面；不复制任何 AGPL 代码。
- 对 IA 的影响：正式定义 Contextual Inspector；导航与命令面板必须同源；复杂详情可留在对象上下文中，而不是为每个技术能力增加一级路由。

### 4.3 Ghostfolio

- Repository：<https://github.com/ghostfolio/ghostfolio>
- 审计快照：`73e4f03`；License：AGPL-3.0。
- 实际阅读：`apps/client/src/app/app.component.{ts,html}`、`pages/portfolio/portfolio-page.routes.ts`、`components/home-overview/home-overview.html`、`portfolio-performance.component.html`、`portfolio-summary.component.html`、`holding-detail-dialog`、accounts/activities/allocations routes，以及 `libs/ui` 的值、表格和通知组件。
- 它解决的问题：从组合概要进入持仓、活动与分析；日期范围和过滤器只在适用路由出现；Holding 是可点击的金融对象。
- 投镜借鉴：Summary → financial object → detail；Portfolio 之下用二级路由组织 Activities/Allocations/Analysis；数值组件统一货币、百分比、sign 和 loading。
- 不借鉴：把产品中心放在“Portfolio Performance”本身；投镜的差异化对象是投资经历、决策和证据，不是另一个组合追踪器；不复制任何 AGPL 代码。
- 对 IA 的影响：“我的投资”必须成为对象入口，Episode 是持仓对象的生命周期详情，决策与证据从该对象继续下钻。

### 4.4 Maybe Finance

- Repository：<https://github.com/maybe-finance/maybe>
- 审计快照：`77b5469`；License：AGPL-3.0。README 明确声明项目已不再积极维护，不能将其当作 2026 年仍活跃产品。
- 实际阅读：`app/views/layouts/application.html.erb`、`app/javascript/controllers/app_layout_controller.js`、Dashboard、Accounts、Transactions 页面，`app/components/DS/tabs*`、`DS/disclosure*`、menu/button/link components。
- 它解决的问题：窄图标导航 + 可折叠账户上下文 + 主内容 + 可折叠 AI 右栏；移动端改为顶部/底部导航；个人财务内容保持柔和、对象化，而非后台管理表格。
- 投镜借鉴：左右两侧栏均可独立收起；右侧 Assistant 是上下文工具，不是主导航；Account Page 用统一 tabs/activity feed；Disclosure 收纳低频细节。
- 不借鉴：其 Rails/Turbo 技术边界、AI 产品语义、已停止维护的实现选择；不复制任何 AGPL 代码或品牌。
- 对 IA 的影响：强化三栏 Desktop shell；Agent 作为右侧上下文面板；Data/Accounts 作为真实 Beta 的必备域而非 Settings 里的 Demo 卡片。

### 4.5 Apple HIG / macOS

- 实际阅读：Sidebars、Split views、Toolbars、Lists and tables、Disclosure controls、Materials、Layout、Motion、Accessibility，以及 SwiftUI Inspector 的官方说明。
- 它解决的问题：在可缩放窗口中保持位置感；不同 pane 分别承担层级导航、内容与选中对象详情；toolbar 只放与当前内容有关的常用动作；reduced motion 和键盘可达性是结构要求。
- 投镜借鉴：Sidebar 最多两层；更深层级转为 list/content/inspector；持续高亮选择路径；macOS pane 可调整宽度；窗口变窄时先隐藏 tertiary inspector；detail disclosure 紧邻其控制对象；材料建立层级但不得损害可读性。
- 不借鉴：逐像素模仿系统 App 或把 Tauri UI 伪装成原生 AppKit；不把最新 Liquid Glass 当作装饰滤镜。
- 对 IA 的影响：采用 Product Sidebar → Main Content → Contextual Inspector；Glass 主要用于导航与临时 control layer，内容层保持更稳定、更少透明的 surface。

## 5. Product principles

1. **用户任务优先于内部包名。** 用户看到“复盘”，代码仍可叫 attribution/behavior/evidence。
2. **金融对象先于指标。** Account/Portfolio → Investment Episode → Decision Event → Evidence → Method。
3. **一个一级页面只回答一个核心问题。** 页面可以包含多个事实，但不能承担多个不同任务。
4. **事实先于解释，解释先于方法。** 默认层只给事实与边界；用户主动下钻才显示公式、来源、版本。
5. **数字是主内容。** 单位、时间、分母、状态与来源必须清楚；装饰不能改变数字权重。
6. **证据不是 verdict。** 不把 percentile、HHI、行为观测自动编码成好/坏。
7. **缺失保持缺失。** `insufficient`、`unavailable`、`partial` 与 `0` 有不同视觉和文案。
8. **Local-first honesty。** Demo、离线、Synthetic、runtime 能力和数据授权持续可见。
9. **共享模式先于页面 CSS。** 新页面优先组合稳定 patterns，避免继续增长页面专用 class。
10. **克制的未来感。** Reflective Intelligence 来自层级、响应和 Orb，而不是大面积霓虹、模糊和动画。

## 6. Current information inventory

| 产品对象/能力 | 当前已有事实 | 用户层级 | 目标入口 |
| --- | --- | --- | --- |
| Account / Portfolio | 现金、总价值、持仓、active assets、历史价值 | 一级对象上下文 | 我的投资；总览摘要；数据与账户 |
| Position | symbol、quantity、weight、avg cost、valuation | 一级对象列表 | 我的投资 |
| Investment Episode | Open/Closed、周期、执行引用、当前/结束状态 | 核心详情对象 | 我的投资 → Episode |
| Decision Event | 建仓、加仓、减仓、清仓及 replay before/after | Episode 子对象 | Episode → Decision Inspector |
| Selection/Sizing/Exit/Friction | 现有 deterministic Decision Evidence | 复盘内容 | 复盘 → 决策；Episode 的 Evidence 引用 |
| HHI/Turnover/Disposition/Loss-state Addition | 当前与部分真实历史 | 复盘内容 + Twin 状态 | 复盘 → 投资方式；My Twin 摘要 |
| EvidenceRecord | value/status/N/window/method/provenance/limitations | 支撑能力 | 上下文“查看依据”；Advanced 索引 |
| Explainability | Explanation/Calculation/Method/Trace | 详情/高级层 | Contextual Inspector |
| Twin Snapshot | 时点状态、evidence refs、DQ、limitations | 一级产品状态 | 我的投镜 |
| Self vs Past | 当前值、历史分布、percentile、窗口 | Twin 二级内容 | 我的投镜 → 与过去相比 |
| Pre-trade Impact | Before/After/Delta/Self/Peer context | 一级任务 | 决策前 |
| Data Quality / provenance | data tier、missing、来源、版本 | 条件性提示 + 管理域 | 总览仅异常提示；数据与账户完整呈现 |
| Cohort / Peer | 目前只有 Synthetic 示例上下文，真实能力未完成 | 未来 Twin 比较上下文 | 我的投镜 → 与可比对象相比（完成后出现） |
| User-to-user Compare | 未连接 | 非当前能力 | 暂不导航；未来需独立 consent 设计后再评估 |
| Agent | UI shell 已有，runtime 非当前 Desktop 能力 | 全局上下文工具 | Top bar / context actions |
| Account ingestion | 未形成完整 Desktop 产品流 | Beta 必需一级管理域 | 数据与账户 |
| Pet / Companion | 独立分支、ambient surface | 辅助体验 | 独立透明窗口，与主 App 共用品牌状态 |

**一级用户任务**：总览、查看投资经历、复盘、查看个人状态变化、交易前检查、管理数据与账户、控制应用。

**内部支撑能力**：EvidenceRecord、Method Registry、Explainability trace、replay、Cohort method、schema/code version。

## 7. IA Option A — Five stable product domains

```text
总览
我的投资
复盘
我的投镜
决策前
────────
数据与账户
设置
```

- “复盘”内使用二级导航：决策 / 投资方式。
- “我的投镜”内使用内容分段：现在 / 与过去相比 / 证据成熟度；真实 Peer 完成后增加“与可比对象相比”。
- Evidence 从 Sidebar 移除，作为 Contextual Inspector 和 Advanced deep link。
- Compare 从 Sidebar 暂时移除；其已实现 Self vs Past 合并到 Twin。
- “我的投资”和“数据与账户”在真实 landing/capability ready 前使用 `hidden_until_ready`，不展示空入口。

优点：用户问题互斥；每个域可独立扩展；Position Episode 归属自然；未来 Peer 不增加一级项；Pre-trade 保持高可发现性。

代价：需要拆分当前 Decisions 页面，并迁移/重定向 Compare 与 Evidence 路由；一级项仍有 5 个，需要严格控制 Overview 与 Twin 的边界。

## 8. IA Option B — Object workspace with grouped actions

```text
总览
我的投资
我的投镜
工作区 ▾
  复盘
  决策前
────────
数据与账户
设置
```

- Sidebar 更短，“工作区”折叠组承载分析型任务。
- 进入“我的投资”后，可出现第二列 Position/Episode list；第三列为对象详情。
- Twin 是明确的个人档案；Review 和 Pre-trade 被视为对对象采取的工作模式。

优点：Sidebar 更克制；Desktop 多列对象导航很强；适合未来账户很多、Episode 很多的状态。

代价：“工作区”是抽象容器，用户可能不清楚复盘和决策前为何被收起；Pre-trade 的重要性被降低；Sidebar 两层再叠加对象 list 后层级更重；移动/窄窗口适配成本更高。

### 8.1 Options comparison

| 维度 | Option A | Option B |
| --- | --- | --- |
| 简洁度 | 5 个清楚任务，扫描成本低 | 顶层更少，但“工作区”需要理解 |
| 用户心智 | 直接对应 5 个核心问题 | 对象优先，但动作归组较抽象 |
| 可扩展性 | 每个域内部扩展，Peer 放 Twin | 对象列表扩展强，动作组可能膨胀 |
| Future Peer | Twin 内自然新增 context | 同样可进 Twin |
| Desktop fit | 稳定 Sidebar + 可选 Inspector | 强三栏，但常态可能占宽过多 |
| 1024×768 | 更容易降级为两栏/Overlay | 两级 Sidebar + detail 更容易拥挤 |
| 迁移成本 | 中等，可按路由逐页迁移 | 较高，需要先建立动态二级列 |

## 9. Recommended IA

推荐 **Option A**。

原因不是它更容易实现，而是它让五个核心用户问题在第一层直接可见，且每个问题互斥。它保留投镜区别于普通 portfolio tracker 的三个核心域：投资经历、复盘、个人投镜；同时让 Pre-trade 保持独立且不被误解为复盘的一部分。

不推荐 Option B 作为 v1，是因为“工作区”会用一个新的抽象词替换现有工程词，用户仍需猜测入口；其三栏常态也会让 1024px 窗口过早进入压缩状态。Option B 的对象列表模式可以局部用于“我的投资”，不必成为全局 IA。

### 9.1 Responsibility boundary

- **总览**：只聚合“此刻值得注意”的事项，不保存完整模块副本。
- **我的投资**：事实对象与生命周期，不评价决策。
- **复盘**：已发生事实的 evidence-backed 观察，不预测、不建议。
- **我的投镜**：跨对象聚合的时点个人状态及其历史变化，不成为投资列表或证据目录。
- **决策前**：拟议交易的确定性状态变化，不给 verdict。
- **数据与账户**：数据来源、账户、同步、DQ、授权、导入导出/删除。
- **设置**：语言、主题、隐私显示和应用行为。

## 10. Final sitemap v1

```text
投镜 Desktop
├── 总览  /overview
│   ├── 当前组合摘要
│   ├── 值得注意（变化 / 数据问题 / 未完成复盘）
│   └── 最近投资经历与决策
├── 我的投资  /investments
│   ├── 当前持仓 / Open Episodes
│   ├── 已结束 Episodes
│   ├── 成交历史（事实视图）
│   └── Episode  /investments/episodes/:episodeId
│       ├── 生命周期与市场价格
│       ├── Decision Event（Inspector）
│       └── Linked Evidence（Inspector）
├── 复盘  /review
│   ├── 决策  /review/decisions
│   └── 投资方式  /review/patterns
├── 我的投镜  /twin
│   ├── 现在的我
│   ├── 与过去相比
│   ├── 证据成熟度 / DQ 摘要
│   └── 与可比对象相比（真实 Peer 完成后才出现）
├── 决策前  /pretrade
│   ├── Proposed Trade
│   ├── Current → Proposed Impact
│   └── Self / Peer context（仅在有效 evidence 存在时）
├── 数据与账户  /data
│   ├── 账户与券商连接  /data/accounts
│   ├── 导入与同步  /data/imports
│   ├── 数据质量  /data/quality
│   └── 授权、贡献、导出与删除  /data/privacy
├── 设置  /settings
│   ├── 外观与语言
│   ├── 通知/交互偏好（未来）
│   └── 关于
└── Advanced（不在主 Sidebar）
    └── Evidence & Methods  /advanced/evidence

Global
├── Command Palette
├── Search（未来跨 Account/Episode/Decision）
└── Ask Twin contextual panel
```

## 11. Page responsibility matrix

| 页面 | Purpose | Primary object | Primary question | Primary CTA | Secondary details | Data source | Future expansion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 总览 | 定向当前注意力 | Current workspace snapshot | 现在有什么值得知道？ | 打开相关 Episode/变化/数据问题 | 组合摘要、近期事件 | Portfolio facts、Twin summary、DQ | Notable Changes、recent checks |
| 我的投资 | 浏览实际投资事实 | Position / Episode | 我实际上经历了什么？ | 打开 Episode | filter、Open/Closed、executions | deterministic replay/Episodes | accounts scope、instrument search |
| Episode | 理解单轮持仓生命周期 | Investment Episode | 这一轮怎么发生的？ | 选择 Decision Event | market marks、position facts、linked evidence | Episode/replay/price facts | corporate action support when backend exists |
| 复盘 · 决策 | 复核决策类 evidence | Decision Evidence | 已发生决策有哪些可验证观察？ | 查看依据 | Selection/Sizing/Exit/Friction | EvidenceRecord + explainability | Entry/Scaling only when implemented |
| 复盘 · 投资方式 | 复核跨事件的描述性模式 | Behavior Evidence | 记录中反复出现什么方式？ | 查看历史/依据 | HHI/Turnover/Disposition/Loss add | EvidenceRecord + metric series | longer history, not personality scores |
| 我的投镜 | 展示个人时点状态档案 | Twin Snapshot | 现在的我是什么状态，和过去有什么变化？ | 检查一项变化依据 | Self baseline、maturity、DQ | Twin/Self deterministic views | Notable Changes、Peer Context |
| 决策前 | 展示拟交易的事实变化 | Proposed Trade / Trade Impact | 如果这样交易，状态怎样变化？ | 检查变化 | valuation semantics、Self/Peer context | local bridge + deterministic engine | similar history when deterministic tool exists |
| 数据与账户 | 管理事实来源和授权 | Account/Data Source | 数据从哪里来，是否完整？ | 添加/导入账户 | sync、DQ、consent、export/delete | Broker adapters / local storage（未来） | multi-account scopes |
| 设置 | 控制应用行为 | App preferences | 如何让应用按我的偏好工作？ | 保存偏好 | language/theme/privacy display | local preferences | accessibility preferences |
| Advanced Evidence | 专业审计和支持 | EvidenceRecord / Method | 如何完整审计一条记录？ | 复制引用/查看来源 | IDs、versions、trace、code | Evidence package | support bundles |

## 12. Navigation model

### 12.1 Sidebar

- 第一组“工作”：总览、我的投资、复盘、我的投镜、决策前。
- 第二组“管理”：设置；数据与账户仅在真实 capability ready 后加入。
- 不显示 Evidence、Agent、Compare、单个指标或未来占位能力。
- “我的投资”和“数据与账户”在 `hidden_until_ready` 状态下不显示，且不得指向占位页面。
- 只允许两层；“复盘”可在主内容内用 tabs，而非在 Sidebar 常驻展开。
- 当前一级域持续高亮；进入 Episode 时“我的投资”保持选中。
- Sidebar 可收起为 icon rail；默认展开，不隐藏 discoverability。
- Command Palette 与 Sidebar 使用同一 route metadata；不维护第二份 labels/order。

### 12.2 Top bar

- Leading：Sidebar toggle、back（进入对象详情时）、当前 route/object title。
- Center：仅放当前任务真正需要的 scope/filter/date；不放全局宣传。
- Trailing：Search/Command、状态异常入口、Ask Twin、少量 overflow。
- Theme 切换可留在 Settings 或 overflow；不必永久占据每页黄金位置。
- Top bar 最多三组 controls，避免工具栏成为第二条导航。

### 12.3 Contextual Inspector

Inspector 是一个统一容器，支持以下 mode：

- `object-detail`：选中 Position/Decision 的详细事实。
- `evidence`：Explanation → Calculation → Method。
- `agent`：绑定当前 object refs 的对话。
- `data-quality`：当前对象的数据缺口与 provenance。

1440px 可停靠在右侧，默认宽 360–420px；1024px 以下改为 overlay Sheet。一次只显示一个 Inspector mode，保留返回栈，不并排打开多个 Sheet。

Inspector 使用 URL-addressable semantic state，以支持 deep link、Back/Forward 和恢复选择。URL 只保存 allowlisted inspector type 与 opaque target ID；不得放入 raw broker account、transaction payload、holdings JSON、financial statement、user identity 或其他敏感原始数据。解析未知 type、未知参数或非 allowlisted action 时 fail closed。

## 13. Drill-down model

```text
ACCOUNT / PORTFOLIO
整体账户与组合事实
        ↓ select
INVESTMENT EXPERIENCE
Position Episode 生命周期
        ↓ select execution
DECISION EVENT
建仓 / 加仓 / 减仓 / 清仓及 replay state
        ↓ 查看依据
EVIDENCE
事实、状态、样本、解释边界
        ↓ 方法
METHOD DETAILS
公式组件、来源、版本、限制、trace
```

规则：

- 每一层都保留上一层选择上下文；用户不会从账户页直接落到 UUID。
- “查看依据”打开 Inspector，不改变主页面和滚动位置。
- Evidence deep link 必须可分享/恢复，但默认呈现人类标题，ID 在 Advanced 层。
- 用户关闭 Inspector 后回到同一 Decision marker 或 metric selection。
- 进入更深层不是新建一种 modal；统一使用 route detail 或 Inspector。

## 14. Design language

正式定位：**Professional financial tool + Personal digital archive + Quiet decision intelligence**。

关键词：calm、precise、reflective、evidence-driven、personal、dense but breathable、restrained future feeling。

`Mirror Glass / Reflective Intelligence` 保留，但重新约束：

- Glass 是空间层级，不是每块内容的默认皮肤。
- Sidebar、Top bar、Inspector、Command/Agent 等 control layer 可以使用更明显材料。
- 主内容使用稳定、低透明或近乎实体的 analytical surface，保证图表和中文正文清晰。
- Cyan reflection 只标记当前选择、focus、active context 和 Orb；不铺满所有 card border。
- 金融数字、轴、表格、Evidence 状态不使用 glow。
- Dark 是旗舰主题，Light 必须具备同样层级，不是简单反色。

## 15. Anti-references

投镜明确不是：

- Crypto dashboard：霓虹、行情终端密度、无意义实时闪烁。
- Neon trading terminal：红绿跳动、极端高密、交易冲动设计。
- Glass card soup：每个数字、说明、状态都套独立半透明圆角容器。
- Fintech marketing hero：大渐变、大 slogan、产品页式 CTA 占据工作区。
- Gamified trading：评分、庆祝动画、徽章、连续签到、percentile = 好坏。
- Enterprise banking portal：部门式菜单、表单矩阵、法律文本主导第一层。
- Generic AI SaaS dashboard：左侧功能模块 + 右上角“Ask AI”但无对象上下文。
- Portfolio tracker clone：只展示资产曲线、收益和持仓，而弱化 Episode/Decision/Evidence。

## 16. Design token proposal

不在本轮改 CSS。下一阶段先建立语义 token，再迁移组件，禁止页面直接创造新的 magic value。

### 16.1 Color

```text
color.canvas
color.surface.base / raised / interactive / overlay
color.text.primary / secondary / tertiary / inverse
color.border.subtle / default / strong
color.accent.default / hover / selected / focus
color.status.info / complete / partial / insufficient / experimental / error
color.outcome.positive / negative / neutral   # 仅用于方法明确的 outcome
color.chart.axis / grid / current / baseline / reference / uncertainty
```

`complete` 不等于“投资做得好”；它只表示 evidence 完整。`insufficient` 使用中性信息色，不使用错误红。HHI/percentile 高低默认都使用 neutral/current colors。

### 16.2 Spacing

保留 4px base：`4, 8, 12, 16, 24, 32, 40, 48, 64`。组件只能引用语义别名：`inline-xs/sm/md`、`stack-xs/sm/md/lg`、`section-gap`、`page-gutter`。

### 16.3 Radius

- `sm 6px`：input、tag、compact control。
- `md 10px`：row group、popover。
- `lg 14px`：真正独立的 object surface。
- `xl 20px`：Agent/Inspector/一处 identity hero。
- `pill`：status/segmented control，禁止用于普通容器。

### 16.4 Border / surface / elevation

- Border：`subtle 1px`、`default 1px`、`focus 2px`；不以粗彩边装饰指标。
- Persistent content：`surface.base` + divider，默认无 shadow。
- Interactive object：`surface.interactive`，hover 只改变 background/border。
- Floating/overlay：允许 `elevation.float` / `elevation.overlay`。
- Blur 固定，不动画；无 `backdrop-filter` 时有实体 fallback。

### 16.5 Motion

- `fast 120ms`：press/focus/tooltip。
- `standard 200–220ms`：selection/tab/row。
- `panel 280–320ms`：Inspector/Sheet。
- `chart 420–520ms`：首次载入且可关闭。
- `ambient 12–18s`：只允许 Orb/背景低频反射。

### 16.6 Data visualization

定义 axis、grid、primary/current、baseline、peer/reference、uncertainty、marker、tooltip surface 和 selection，不允许页面自定义随机系列色。Current marker 必须最清楚，reference 不通过降低到不可读来让位。

## 17. Typography

继续使用系统字体：`-apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif`；技术标识使用系统 monospace。不新增字体文件。

| 语义 token | 建议规格 | 用途 |
| --- | --- | --- |
| `type.page-title` | 28/34, 600 | 当前产品域标题，一页一次 |
| `type.page-context` | 14/22, 400 | 时间、scope、数据层级 |
| `type.section-title` | 17/24, 600 | 页面主区段 |
| `type.object-title` | 15/22, 600 | Episode、Position、Evidence 人类标题 |
| `type.numeric-primary` | 28/34, 600, tabular | 当前页面首要数字 |
| `type.numeric-secondary` | 17/24, 560, tabular | before/after、quartile、metadata value |
| `type.body` | 14/21, 420 | 解释性正文 |
| `type.label` | 12/18, 520 | 字段标签、table header |
| `type.metadata` | 11/16, 500 | 状态、日期、N、method summary |
| `type.technical` | 11/17, 450, mono | Evidence ID、version、trace、formula |

规则：

- 金融数字使用 tabular numerals，货币/百分比/pp 单位不可省略。
- 列表数字右对齐；before → after 同基线对齐。
- 大写只用于极短的 metadata，不把中文句子 letter-space 成技术装饰。
- 一页最多一个 display-like value；其余层级靠 section/row，而非不断增大字号。

## 18. Layout system

| 区域 | 1440×900 | 1024×768 |
| --- | --- | --- |
| Sidebar | 216–228px，可收起到 64px | 默认 200–216px；必要时 icon rail/overlay |
| Top bar | 56px | 52–56px |
| Main page gutter | 28–32px | 20–24px |
| Content max width | 1180px；对象列表可全宽 | 流式填充，最小 640px 主区 |
| Inspector | docked 380px，范围 340–440px | overlay Sheet，最大约 520px |
| Section rhythm | 32px；major 40px | 24–32px |
| Dense row | 48–56px | 48–56px |
| Chart/detail | `minmax(0, 1fr) + 320px` | 单列；详情进 Inspector |

响应原则：

1. 先隐藏 tertiary Inspector，再压缩 main content。
2. Object list 在 1440 可作为内容内第二列；1024 下变为整页 list → detail。
3. 不在 1024 强保三列，不让图表宽度低于可读阈值。
4. 中文标题允许自然换行，但主要 CTA、状态和单位不被截断。

## 19. Core component patterns

| Pattern | 何时使用 | 何时不用 |
| --- | --- | --- |
| `AppShell` | 全局 Sidebar/Topbar/Main/Inspector | 页面内不得再造第二个 shell |
| `PageHeader` | route/object 的标题、scope、1–2 个动作 | 不承载大段营销文案或指标网格 |
| `SectionHeader` | 一个明确问题下的内容组 | 不为每个 row 重复 |
| `FactRow` | label/value/unit/status 的可扫描事实 | 不把复杂对象压成一行 |
| `FinancialObjectRow` | Position/Episode/Decision 可点击对象 | 静态说明不用 |
| `MetricComparison` | 同单位 current/reference/delta | 不跨单位合成，不制造 score |
| `StatusBadge` | Evidence/system 状态文本 + icon | 不表达未定义的好坏 |
| `Empty/Insufficient/Unavailable/Error` | 对应严格状态 | 不互相替代，不把 0 当 empty |
| `Timeline` | Episode 的真实时间对象与事件 | 无真实时间戳时不用 |
| `Inspector` | 选中对象的 detail/evidence/agent/DQ | 主任务表单、长列表不塞入 |
| `Disclosure` | 单块低频细节、技术信息 | 不在同一层放多个互相竞争的折叠区 |
| `RangeTrack` | 同一指标的分位/当前 marker | 不暗示高 percentile 更好 |
| `TechnicalDetails` | IDs、versions、provenance、formula | 不出现在默认首页 |
| `MirrorOrbVisual` | 品牌身份、Twin、Agent、Companion | 不做通用 loading icon 或每卡装饰 |

### 19.1 Card qualification rule

Card 只有在满足至少一项时使用：

- 它是独立、可选择或可操作的对象；
- 它需要与周边内容有明确 surface boundary；
- 它拥有独立 loading/error/selection 状态。

每个统计数字、metadata、说明段落不单独成 Card。优先使用 typography、空白、row、divider、list 和 section。一个主 section 内的关联事实共享同一 surface。

### 19.2 Progressive disclosure contract

```text
Default fact
  → Detail / Why
    → Explanation
    → Calculation
    → Method / Provenance / Version
```

当前 Evidence Inspector 的“解释 / 计算 / 方法”可保留为标准 evidence mode；技术详情再用一个 disclosure 收纳 trace/schema/code version。普通用户第一层只看到事实、状态、时间、对象和“查看依据”。

## 20. State language

| State | 中文产品文案 | 视觉语义 | 必须包含 | 禁止 |
| --- | --- | --- | --- | --- |
| Loading | 正在加载 / 正在检查 | 中性、轻量 progress | 当前动作 | 无限 shimmer、伪数据 |
| Empty | 暂无记录 | 中性 | 为什么为空 + 可行动 CTA（若有） | 当成错误 |
| Unavailable | 当前不可用 | 中性偏弱 | 缺少的能力/连接 | 显示 0 |
| Insufficient | 证据不足 | 信息色 | 需要什么、当前有什么 | 红色错误、猜测结果 |
| Partial | 部分证据 | warning/info | 可用范围与缺口 | 呈现为 complete |
| Complete | 证据完整 | restrained status | 方法边界已满足 | 表达“结果优秀” |
| Experimental | 实验性 | distinct info | 版本与限制 | 隐藏实验性质 |
| Error | 发生错误 | error color | 可恢复动作、错误范围 | 用于业务负结果 |
| Demo/Synthetic | 示例数据 | persistent badge/banner | tier、fixture/version | 伪装真实账户 |
| Disconnected | 尚未连接 | neutral | 哪个 runtime/service 未连接 | 假交互、假成功 |

State icon 和文字同时出现；颜色从不单独承载含义。页面级 error 与局部 row error 分开处理。

## 21. Color semantics

- `accent` 表示当前选择、focus、active context，不表示收益更高。
- `status.complete/partial/insufficient/error` 只表达证据或系统状态。
- `outcome.positive/negative` 仅在 method 明确定义 comparison 后使用，并同时显示符号和文字。
- HHI、Turnover、percentile、Position weight 高低默认 neutral；不自动红/绿。
- Before/After 使用 Current/Proposed 语义色与明确标签，不用绿=建议、红=不建议。
- 图表不使用渐变面积制造涨跌情绪；tooltip 给精确单位、日期和来源。

## 22. Motion language

- 点击/hover/focus：120–160ms，颜色和轻微 opacity，不做到处 scale。
- Route：约 200–220ms，opacity + 不超过 6px 位移。
- Inspector：280–320ms，从其空间来源进入；关闭返回原选择。
- Financial chart：首次加载允许短 entrance；切换窗口保持轴稳定，避免让数据变化看起来更剧烈。
- Mirror Orb：唯一可持续 ambient motion，低频、低亮度、与 idle/thinking/active 状态绑定。
- 禁止 bounce、celebration、收益数字滚动夸张、红绿闪烁、blur animation。
- `prefers-reduced-motion` 下移除 ambient loops、layout travel 和数字插值，改为即时或短淡入。

## 23. Synthetic / Demo presentation strategy

### 23.1 Identity separation

```text
canonical_id / instrument_id / symbol
  = 后端事实、测试稳定性、deep link identity

display_name
  = 后端或受信 adapter 提供的展示名称
```

- 前端不根据 `SYN_LOSS_SOLD` 猜真实证券名称。
- Demo exporter 未来可提供 `display_name: 示例证券 A`、`display_symbol: DEMO-A`；技术层仍保留 canonical symbol。
- 若无 display name，显示 exact symbol，并明确“未提供名称”，延续当前 Position Episode 的 fail-closed 语义。

### 23.2 Persistent demo hierarchy

- Workspace：Sidebar footer 或 Top bar 持续显示 `Demo · Synthetic` 与 fixture version。
- Page：只在影响理解处显示轻量 badge，不在每个 Card 重复。
- Inspector/Export：完整显示 data tier、source、version、limitations。
- 数据由 deterministic backend 生成不等于真实用户数据；文案继续使用“示例账户/示例市场”。
- 不用 `SYN_*` 的负面/正面名字暗示行为标签或结果好坏。

## 24. Agent / MirrorOrb / Pet integration model

### 24.1 MirrorOrb

MirrorOrb 是“投镜 / 你的镜像智能”的身份，不是装饰 icon。

应该出现：Workspace brand、My Twin identity、Ask Twin、Desktop Companion。

不应该出现：每张 Card、每个 loading、每个 PageHeader 的大 Hero、普通 status。

状态 contract：`idle`（可用但未交互）、`thinking`（工具/模型处理中）、`active`（当前面板有新结果/上下文）、`attention`（仅真实需注意状态，不能等同金融坏结果）。状态必须有非动画替代和 accessible label。

### 24.2 Agent

- 不是一级页面；入口固定在 Top bar，并可由 Episode/Twin/Pre-trade 的局部“问投镜”打开。
- 面板接收显式 `context = { route, subject_id, account_id?, episode_id?, decision_id?, evidence_ids?, pretrade_request_id? }`。
- Agent 只能声称当前已注册、已成功调用 tools 支持的能力；金融数字仍来自 deterministic facts。
- 打开后首先显示当前对象、人类标题、数据 tier 和可用 evidence；不硬编码 Demo Episode。
- 关闭面板不改变主页面选择；切换对象时明确更新上下文，不能静默沿用旧对象。

### 24.3 Desktop Companion / Pet

- Pet 是 ambient surface；主应用是完整 decision workspace。
- 两者共享 MirrorOrbVisual、motion token、status language 和品牌声音，不共享页面布局。
- Pet 不显示复杂金融数字、不给买卖建议、不独立计算；最多反映同步/可用/有上下文提醒等粗粒度状态。
- 点击 Pet 可把用户带回主 App 的明确对象/任务；不在本任务合并 Pet branch。

## 25. Technical content placement

| 层级 | 默认显示 | 例子 |
| --- | --- | --- |
| Product | 事实、对象、状态、时间、变化、边界 | “2025-01-06 建仓 1,000 股” |
| Detail | 样本量、window、comparison、限制摘要 | “N=5；缺失日期不补齐” |
| Evidence Inspector | Explanation、Calculation components、Method summary | `sum(weight_i ** 2)` |
| Advanced | Evidence ID、Trace ID、Method ID/version、schema/code version、full provenance | `ev_…`, `hhi_security_weights_v1` |

UUID 不出现在 Overview、My Investments list 或 Twin 第一层。需要复制引用、排查支持问题或学术复核时才进入 Advanced。

## 26. Current → future route migration map

| Current route | Proposed route | Action | Backward compatibility |
| --- | --- | --- | --- |
| `#/overview` | `#/overview` | Keep + refocus | 原 route 保持 |
| `#/my-twin` | `#/twin` | Move/rename | 旧 route redirect，保留 query/selected evidence |
| `#/decisions` 的 Episode list | `#/investments` | Split | 首次迁移后旧 route 仍到 Review；Episode 入口在新页 |
| `#/decisions` 的 decision evidence | `#/review/decisions` | Split/move | `#/decisions` redirect 至此至少一个 release |
| `#/behavior` | `#/review/patterns` | Move | 旧 route redirect，保留 selected metric query |
| `#/compare` 的 Now vs Past | `#/twin?view=history` 或 `#/twin/history` | Merge | legacy compare deep link 映射到 Twin history |
| `#/compare` 的 Peer | `#/twin?view=peers`（能力完成后） | Hide now / future merge | 未完成前不提供空路由；旧 Demo 可留 feature flag |
| `#/compare` 的 User compare | 未决定 | Hide | 不把未连接占位带入产品导航 |
| `#/decision-check` | `#/pretrade` | Rename/move | 旧 route redirect；bridge contract 不变 |
| `#/evidence` | `#/advanced/evidence` | Move/remove nav | 所有 `selected=` deep links redirect；Inspector URL state 可恢复 |
| `#/decisions/episodes/:id` | `#/investments/episodes/:id` | Move | exact ID redirect，不改变 Episode identity |
| `#/settings` | `#/settings` | Keep/narrow | 数据/consent sections 移出后仍保留偏好 |
| 无 | `#/data`、`#/data/accounts` 等 | Add later | Beta ingestion 前先建立 route shell |

路由迁移不得改变 generated payload、Evidence ID、Episode ID 或金融语义。先建立 redirects 与 route metadata，再移动内容。

## 27. User journey tests

计数以“从任何一级页面开始点击 Sidebar”为第一步，不计算输入文字本身。

| 用户任务 | 唯一推荐路径 | 最多步骤 | 判定 |
| --- | --- | ---: | --- |
| 我想看现在持有什么？ | 我的投资 → 默认“当前持仓” | 1 | 清楚 |
| 我想看宁德时代这一轮怎么投的？ | 我的投资 → 搜索/选择标的 Episode | 2 | 清楚；名称必须来自可信 display name |
| 为什么系统这样评价这次减仓？ | 我的投资 → Episode → 减仓事件 → 查看依据 | 4 | 层级长但连续、每步对象明确；Inspector 不换页 |
| 最近和以前有什么变化？ | 我的投镜 → 与过去相比 | 1 | 清楚；不再另去 Compare |
| 我准备再买一笔，会发生什么？ | 决策前 → 填写并检查变化 | 1 | 清楚 |
| 我想查看计算方法。 | 当前事实“查看依据” → 方法 | 2 | 不要求先找到 Evidence Library |
| 我想导入新账户。 | 数据与账户 → 添加/导入 | 1–2 | 为 Beta 预留明确位置 |
| 未来我想跟同类比较。 | 我的投镜 → 与可比对象相比 | 1–2 | 真实 Peer 完成后出现，不新增 Sidebar 项 |

如果用户必须在 Overview、Compare、Twin 三处猜 Self vs Past 入口，或在 Decisions/Evidence 两处猜 Decision 依据，迁移尚未完成。

## 28. Complete product story

```text
首次打开
  → 选择 Demo 或进入“数据与账户”导入
  → 总览看到当前状态和真正需要注意的事项
  → “我的投资”查看持仓与 Open/Closed Episodes
  → 打开一段 Investment Episode
  → 选择某次建仓/加仓/减仓/清仓 Decision Event
  → 在 Inspector 查看 Evidence：解释 → 计算 → 方法
  → 回到“我的投镜”查看跨经历的当前状态与 Self vs Past
  → 未来在同一域查看真实 Peer Context
  → 在“决策前”输入拟议交易并查看确定性 Before/After
  → 随时用 Ask Twin 对当前对象做基于已注册工具的解释
```

用户不需要理解 Python package、Evidence adapter、TwinSnapshot class 或 Behavior module，也能完成这条路径。

## 29. Migration plan

禁止 Big Bang。每一阶段必须保持可构建、可测试、旧 deep link 可用。

### Phase 0 — Architecture acceptance

- 确认本文件中的 IA、命名、Compare/Peer 归属和 Data/Accounts 范围。
- 不改应用代码。

### Phase 1 — Shell and navigation source of truth

- 建立 route metadata 单一来源，Sidebar、Command Palette、Top bar title 共用。
- 导航改为 Option A，但先用 redirect 保持旧 routes。
- 建立统一 Inspector host 和 URL/restoration contract；不迁移全部内容。
- 收敛最小 semantic tokens，不重做视觉。

### Phase 2 — Overview + My Investments

- Overview 删除模块样品卡，仅保留 current state、attention、recent objects。
- 新建“我的投资”，从 Decisions/My Twin 搬迁 Position/Episode lists。
- Position Episode route 移到 `/investments/episodes/:id`，identity 与金融数据不变。

### Phase 3 — Review

- 建立 `/review/decisions` 与 `/review/patterns`。
- 移动当前 Decision/Behavior 内容，统一 Metric row、history、查看依据。
- Evidence Inspector 作为唯一默认 detail surface。

### Phase 4 — My Twin

- 删除 Episode/Evidence 目录式重复，只保留 current state、Self vs Past、maturity/DQ。
- Compare 的 Now vs Past 合并到 Twin；旧 compare route redirect。
- 为未来 Notable Changes/Peer Context 预留内容插槽，不显示空能力。

### Phase 5 — Pre-trade

- 路由和文案迁移为“决策前”；现有 Python/Tauri bridge 与金融语义保持不变。
- 统一 Proposed/Current/Self/Peer 的 comparison pattern 和 Inspector evidence entry。

### Phase 6 — Data/Accounts, Advanced, Settings

- 建立 Data/Accounts 产品域，再移出 Settings 中的数据、Peer consent、Compare permissions。
- Evidence Index 移到 Advanced；保留 deep links 和 support/debug 能力。
- Settings 只保留真实偏好，删除 component state showcase 式内容。

### Phase 7 — Peer / Agent / Companion（能力完成后）

- Peer 有真实 contract 后进入 Twin，不新增长期一级菜单。
- Agent runtime 接入后绑定 route/object context，继续使用同一 Inspector host。
- Pet branch 单独验收后共享视觉/状态 token，不复制主 App 页面。

## 30. Risks and unresolved decisions

1. **“我的投资”范围。** Beta 是否一开始支持多个账户/组合 scope，决定页面是否需要常驻账户选择器。
2. **“复盘”中文命名。** “复盘”自然但可能被理解为交易日志；“决策复盘”更准确但更长，需要用户测试。
3. **Pre-trade 命名。** “决策前”符合产品概念；“交易前检查”更直白。建议用 Sidebar“决策前”，Page title“交易前检查”。
4. **Compare/User-to-user。** 必须先完成 consent、privacy、identity 和 minimum cohort contract，再决定是否需要独立产品域。
5. **Inspector URL encoding detail。** 已确定使用 URL-addressable semantic state；仍需在实现中确认 query key 命名和 Inspector 历史栈细节，同时保持敏感原始数据禁止进入 URL。
6. **Overview attention policy。** “值得注意”必须由确定性状态/注册规则产生，不能由前端随意排序或由 LLM 选择。
7. **Display name contract。** 应由 adapter/backend 提供；在 contract 未定义前继续显示 exact symbol，不能前端猜测。
8. **CSS migration budget。** 2,441 行单文件不能一次拆完；应随页面迁移提取 pattern/token，并用 visual regression 防止漂移。
9. **Glass performance。** backdrop blur、ambient filters 和大面积 fixed layer 需在低端 Mac 与 reduced transparency 情况下测量。
10. **Evidence Index audience。** 是否在普通 Settings 提供“高级模式”入口，还是只通过 Command Palette/Support deep link，需要 Beta 用户研究。

## 31. Explicit decisions

1. **当前 Sidebar 是否仍主要反映开发模块？** 是。Decision、Behavior、Evidence、Twin、Compare 仍近似按代码能力包并列，而非按用户任务和金融对象组织。
2. **Evidence 是否继续作为一级导航？** 否。它应是上下文“查看依据”与 Advanced audit route。
3. **Decision / Behavior 是否继续各占一级导航？** 否。它们应成为“复盘”的两个二级视图。
4. **Position Episode 最自然属于哪个产品域？** “我的投资”；它是投资经历的生命周期对象，不是 attribution 模块的附属页。
5. **My Twin 的唯一核心职责是什么？** 展示“截至某一时点，我的个人投资状态是什么，以及它相对自身历史如何变化”。
6. **Overview 的唯一核心职责是什么？** 告诉用户“此刻有哪些真实状态、变化或数据问题值得我注意，并把我带到对应对象”。
7. **未来 Peer 进入哪个产品域？** “我的投镜”的比较上下文；与 Self vs Past 并列，但仅在真实 Peer evidence 可用后出现。
8. **Agent 是否应成为一级页面？** 否。它是绑定当前对象和 route context 的全局 Inspector surface。
9. **为什么当前像功能集合？** 因为导航映射实现模块、对象归属错误、页面问题重叠、技术细节过早、未来占位与真实能力同权，视觉又用大量 Card 将所有内容表现为并列模块。
10. **推荐 IA 能否容纳 Peer、Compare、Agent、Data/Accounts、Pet 而不继续增加大量一级菜单？** 能。Peer/Compare 进入 Twin；Agent 使用全局 Inspector；Data/Accounts 是唯一新增且 Beta 必需的管理域；Pet 是独立 ambient surface；其余都在既有域内扩展。

## 32. What to implement first after approval

第一项实现应是 **Phase 1 的 route metadata + 新 Sidebar 信息架构 + redirect skeleton + 统一 Inspector host contract**。它先建立边界，不移动金融逻辑，也不要求重写页面。完成后再构建“我的投资”并迁移 Episode；不要先改颜色、重写 Overview 或添加 Peer。

## 33. Validation boundary

- 本文创建期间未修改 `App.tsx`、routes、WorkspaceShell、pages、CSS、generated payload 或任何 Python 金融代码。
- 参考仓库全部位于投镜仓库之外，不是 submodule/runtime dependency。
- Actual 的 MIT 代码、Rotki/Ghostfolio/Maybe 的 AGPL 代码均未复制；本文只记录可独立实现的产品与架构原则。
- 本文是提案，不应在用户确认前提交。

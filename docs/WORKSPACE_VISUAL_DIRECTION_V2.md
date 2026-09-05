# 投镜完整工作台 · Visual Direction v2

2026-09-06。起点：`56849b8`，开工时 working tree clean。本轮仅展示层、前端适配与回归；不是全部业务上线声明。

## 入口与组织

- 默认：`http://127.0.0.1:1420/#/investments`。
- 原版对照：`http://127.0.0.1:1420/?workspace=classic#/investments`。查询参数必须在 `#` 前。
- 两种展示共享 Router、DataModeProvider、LocaleProvider、ThemeProvider、Inspector、业务组件与服务。原版应用壳保留；投资与 Episode 使用同一业务展示组件的紧凑样式，不维护第二套账户状态或请求。
- 工作分区：我的投资 → 复盘工作区 → 投资方式与历史 → 对比分析 → 决策前检查；个人档案：决策记录；管理：数据与账户、设置。问投镜是带上下文的入口，而非独立无对象聊天。
- `IntelligenceShell` 的页面生命周期以 pathname、数据模式、subject/account 为边界。更换账户会清除旧页面的草稿、请求结果和选中对象。

运行：

```sh
cd /Users/cccc/Projects/personal-investment-twin/apps/desktop
npm run dev -- --host 127.0.0.1 --port 1420 --strictPort
# 原生应用：使用同一个前端与既有 Tauri 开发配置
npm run tauri -- dev
```

如果已有 strict-port dev server，复用它；不要同时启动第二个端口。原生 QA 使用临时 identifier 隔离应用数据，并跳过重复启动 beforeDevCommand。

## 能力覆盖与实际来源

| 能力 / 内容 | 页面 / 详情入口 | 数据来源与边界 | 本轮验收 |
|---|---|---|---|
| 账户、截至时间、持仓、全部投资经历 | `/investments`，账户选择、持有中/已结束/全部、搜索 | 真实模式 `account.list` / `investments.list`；预览为既有 Position Episode 投影。没有账户总净值时不自行汇总 | 空账户、封闭/开放/多年 Episode；exact account 过滤 |
| 结果、价格、成本、成交、数量路径 | `/investments/episodes/:id` | 原 `PositionEpisodeTimeline` / `PositionQuantityTimeline`，原 replay/Outcome 数据；开放结果显示估值日期 | 两尺寸；真实 Canvas hover/click、键盘缩放/Home、Ctrl-wheel、水平平移；完整成交账本 |
| 值得回看的事实、阶段和操作 | Episode 右侧事实队列；Review 的事实/操作深链接 | 原 `reviewPresentation.facts`、`pathAnalysis`、canonical decision IDs；不创造 relevance 分数 | `?fact=` 聚焦原区间，`?decision=` 打开准确操作；全部 Path 背景可展开 |
| 交易前后状态、归因、历史假设、依据 | 成交 Drawer；固定假设展开；Evidence/方法来源 Inspector | 原 Outcome/Counterfactual/Explainability、已有 Evidence refs | 成交前后状态、原 Inspector/focus/Escape 可达；只显示实际存在的 refs |
| Selection / Sizing / Exit / Friction 方法研究 | Review 页底部独立研究入口 → `/review/decisions`、`/advanced/evidence` | 保留既有 Synthetic 方法示例。明确不代表当前所选账户，不跨 subject 拼装 | 入口保留、原回归测试保留；账户级 Evidence 仍需真实 runtime 提供 |
| 投资方式 / Twin / Self history | `/history`，当前观察、真实历史折线、个人历史位置、快照详情 | `backendEvidence` 的 HHI、Turnover、Disposition、Loss-state Addition、Twin、SelfBaseline；只允许已登记 study 的 exact subject/account | HHI/Turnover 日期折线；PGR/PLR/PGR−PLR、1/2 检测事件；无新增公式、无人格/能力评分 |
| 与过去的自己比较 | `/comparison` → Self / Past | 既有真实历史 current/past 比较；仅 HHI/Turnover 有序列 | 保留日期、值、状态；没有为其他维度伪造趋势 |
| 同股 / 授权他人比较 | `/comparison` → 同股路径；`/investments/compare-example`；真实 Episode Ask 授权入口 | 原限定 Episode 派生事实分享与 `DecisionAnalysisWorkspace`；A/B 是独立 Synthetic 双主体，不是所选账户 | 双路径、期间、结果、成本和操作可达；顶部 Ask 保持 pair context；本轮无外部模型调用 |
| 群体比较 | `/comparison` → Cohort | 既有 deterministic 72-account Synthetic 分布和 PeerRangeChart；真实群体 runtime 未接入 | N、观察期、P25/P50/P75、用户值、percentile、定义和限制保留；不称真实排名 |
| 复盘工作区 | `/review` | exact account 的 Episode 索引 + 已选 Episode 的后端精选事实 + 全部操作。排序仅为开始日期，明确不是已计算的复盘优先级 | 事实 → 图表窗口 → 操作/依据 → 上下文提问；无前端金融 heuristic |
| Journal | `/journal?episode=...` | 计划、理由、退出条件、下次复盘日期、事后补记标志；仅页面内存草稿 | 真实生成 recordedAt；输入/路由/Episode/账户变化清除草稿；没有永久保存、Evidence/Twin 写入 |
| 决策前检查 | `/pretrade` | 原 `DecisionCheckPage` / `pretradeService` / 固定 Python bridge。注册 Synthetic subject 的实验，不是当前真实账户 | 原生实际计算；浏览器只允许完全一致的 generated 输入，修改清空并拒绝；相似历史未接入明确说明 |
| 问投镜 | `/ask?episode=...` 或 pair 内 analysis | 真实 Episode 原 `DecisionAnalysisWorkspace`、原 consent/accepted-result/claim 流；普通示例只预览输入，无假分析进度/回答 | URL 保持当前对象；新工作台不直接启动 provider、不扩大模型授权；没有重新做 DeepSeek 实模 QA |
| 导入、市场覆盖、质量、账户管理 | `/data` → 成交 / 行情 | 仅 native **且 real_user** 挂载原 DataAccountsPage。复用既有 preview/commit、字段问题、质量与删除流程 | 原生 Synthetic 不挂载 live importer；浏览器三步流程不读文件/不持久化/不提交 |
| 派生事实分享与权限 | `/data` → 分享 → 选择 Episode → 原 Ask 授权面板 | 原 recipient/expiry/model permission/fingerprint 流；没有全账户访问或假的生效开关 | 路径保留；新权限或邀请 UI 不自行生效 |
| 设置 | `/settings` | 原 locale/theme provider，会话内生效；原版入口 | zh-CN/en-US、石墨/瓷白实际切换；不宣称尚无的永久偏好存储 |

## 预览上下文

默认启动是 real_user，绝不因数据不足切换 Synthetic。

已有 fixture 不是一个一致的大账户，不能为了演示连贯将它们冒充一个账户：

- 产品复盘：`demo-user:product-story` / Demo Security H，2025-01-06—2025-05-20，6 笔执行，最终结果 −283.50 CNY / −2.43%。
- History/Twin/行为/Peer：已登记 `demo-user:synthetic-behavior` / `demo-account:behavior`，截至 2025-01-08。只有明确切换到该 study 才展示。
- 拟交易：同一已登记 behavior synthetic subject 的独立实验；真实账户模式须明确选择进入，不读取真实账户。
- 同股：已有 `SYN_COMPARE_A/B` 派生事实专用样例。页面和全局 Ask 都保留这一独立范围。
- 单标的 Selection/Friction 与 Exit 方法示例各自保留独立身份，不因为页面入口合并而改变证据归属。

## 视觉与交互落地

石墨 / 瓷白两套安静的阅读表面；光学切面标志、透明边缘、分层工作台与真实数据构图。列表、图表工作区、表单和问答不套同一大型卡片模板。

导航使用既有 Motion 的位置过渡；背景与标志没有持续渲染循环；表面 hover 不覆盖图表的命中区域。ECharts 的 series、坐标、手势分类和直接时间导航实现保持不变。方法与内部长 ID 可展开查看，重要日期和不确定性不隐藏。

实际阅读官方 demo 和源码后采用的参考思想：

| React Bits 参考 | 实际借鉴 | 本轮没有引入 |
|---|---|---|
| [PillNav](https://reactbits.dev/components/pill-nav)、[CardNav](https://reactbits.dev/components/card-nav) | 清晰的活动位置与导航层级；原生 link 和键盘仍可用 | GSAP 导航整件、默认品牌与演示链接 |
| [AnimatedList](https://reactbits.dev/components/animated-list) | 可选择的研究索引、焦点/选中状态 | 原 demo 的全局键盘监听、另一个滚动容器 |
| [Stepper](https://reactbits.dev/components/stepper) | 导入的来源→字段→确认流程与方向感 | 原表单、成功动画或假持久化 |
| [MagicBento](https://reactbits.dev/components/magic-bento) | 低强度局部材质与空间分组 | 颗粒、全局 spotlight、磁吸/倾斜、hover scale everywhere |
| [FadeContent](https://reactbits.dev/animations/fade-content) | 克制的内容进入、减少运动降级 | 页面级滚动劫持 |
| [GlassSurface](https://reactbits.dev/components/glass-surface)、[FluidGlass](https://reactbits.dev/components/fluid-glass)、[LightRays](https://reactbits.dev/backgrounds/light-rays) | 对照真实折射/背景的阅读代价，最终使用原创表面与边缘 | 没有复制 WebGL shader、GLB、默认图像或外部资源；不让折射作用于数据 |

来源：[官方仓库](https://github.com/DavidHDev/react-bits)，本轮检查的 `main` / 官方文档（不是新增 runtime 依赖）。[LICENSE.md](https://github.com/DavidHDev/react-bits/blob/main/LICENSE.md) 为 **MIT + Commons Clause License Condition v1.0**，不是无附加条款的 MIT。禁止把软件本身作为独立组件包出售等限制仍存在。本轮只借鉴交互/组织思想，未复制 React Bits 实现代码或视觉资产；新 CSS/组件为本项目实现，因此没有新增其组件分发与版权资产。

没有添加 package/lockfile 依赖；继续使用既有 React、Motion、Radix、Lucide、ECharts、Tauri。

## Correctness 与回归

- account/subject 不匹配、missing Episode、没有 runtime 的真实数据都 fail closed。
- Journal 无 storage/fetch/invoke，临时自述不成为客观事实。
- DataWorkspace 的 live importer 必须同时满足 native + real_user；预览不能执行确认写入。
- 已注册 pretrade Explainability 只适用于完全一致的输入。复用 `matchesOfflineDemo` 做展示适用性判断；改变 native quantity/price/fee 后，不再借用旧解释。计算、bridge、schema、结果不变。
- 没有修改 Python、金融公式、replay、行情、Compare、Evidence Contract、Agent、ClaimOption、validator 或模型授权。

验证命令：

```sh
node --experimental-strip-types --test tests/*.test.mjs
npm run check
npm run build
git diff --check
```

180 个 Node tests 通过（基线 165）。新增账户/路由边界、跨账户排除、Journal 作用域、真实 importer 门槛、原有页数据/详情保留、study 归属，以及固定 Explainability 适用性回归。未用修改 Python tests 代替 UI 验收。

浏览器 QA：`node scripts/qa-workspace.mjs`，前提是本机隔离 Chrome CDP 9338、strict Vite 1420、可用 ffmpeg；这些只用于 QA，不是应用依赖。截图和录屏写入被忽略的 `artifacts/ui/workspace-v2/`。

最终浏览器 71 项检查通过，88 张截图。主要任务均有 1440×900、1280×720 的首屏和末端滚动截图；`browser-qa.json` 保存检查名称/错误/产物清单。`workspace-flow.mp4` 是真实页面帧编码的约 10 秒跨页录屏，不是概念图。包括空账户、封闭/开放/多年投资、missing、浏览器错误、临时草稿、Evidence Inspector、原版对照。中英文与明暗主题实际切换。

原生 Tauri/WKWebView 独立验收：隔离 QA identifier，实际启动应用；打开 Synthetic Episode、真实 Canvas 价格/成本/marker、成交详情；native 预览导入边界；真实固定 Python 拟交易请求先 loading 后成功。注册输入 BUY 200 @ 13、fee 5 返回现金 91,900 → 89,295，HHI 0.4818 → 0.5767。只有前台窗口的完成绘制截图作为原生图表依据；后台 WKWebView 动画暂停的截图不当作渲染结论。

## 性能与未验证边界

- 对 HEAD `56849b8` 在独立临时目录实际构建对照。新工作台所有 JS+CSS gzip 合计约增加 **35.7 KB / 5.5%**；main JS gzip 约增加 16.2 KB。ECharts 与 generated financial payload 基本未变。最后的细小文案/展示门槛修改可能产生少量字节波动。
- 当前仍有 >500 KB chunk warning（主包、ECharts、既有 generated 数据），不是零成本升级；没有为消除 warning 顺手改数据分包或金融 source。
- 浏览器全流程没有阻塞性 console exception。静止页面 1.3 秒窗口约 0.00068 秒 TaskDuration 增量；只是受控 idle 测量，不代表 GPU/电池/长时性能保证。
- reduced-motion 的新工作台没有持续 CSS 动画；保留现有键盘访问、Sheet 焦点约束与关闭行为。
- **没有实际验证物理 Mac 触控板**。Ctrl-wheel/水平 wheel/键盘只作为对应自动输入测试，不替代物理手势。
- 没有再调用 DeepSeek、没有读取 key、没有外发真实账户；原 accepted result/授权工作流复用不等于本轮重新做了实模验收。
- 没有完成真实账户新导入/分享签名/删除的端到端写入 QA；只复用原合同并验证 UI 门槛。没有声称完整业务已上线。
- 待接入：真实账户 general history/Twin/Cohort runtime、Journal 持久化、相似历史操作检索、账户级净值等缺失汇总、更多行为历史；不会由前端补算。

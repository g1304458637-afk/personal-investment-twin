# 投镜内置公司研究：本地整合验收

Date: 2026-10-23

final result: passed

## Comparison target and scope

- Source visual truth: `/Users/cccc/Projects/investment-twin/投镜_公司研究_Demo_20261023/evidence/demo-overview-dark.png` — 用户认可的公司研究 Demo。
- Implementation: `http://127.0.0.1:18022/#/company-research`，投镜实际前端与 Company Twin 实际引擎。
- Implementation screenshot: `/Users/cccc/Projects/investment-twin/投镜_统一入口/公司研究整合_20261023/evidence/integrated-overview-dark.png`。
- 两张截图均为 1280 × 720 pixels；CSS viewport 1280 × 720；1 screenshot pixel / CSS pixel；无缩放归一化。状态均为宁德时代、2025 年、公司概览、深色。动画背景使用同一原始素材，暂停时刻不同。
- 验收范围为当前桌面尺寸的本地浏览器整合页及桌面 RPC 契约。未将其等同于正式安装版、已打包 sidecar 或真实账户 UI 全链路验收。未声称验证其他窗口尺寸。

## Visual evidence

证据目录：`/Users/cccc/Projects/investment-twin/投镜_统一入口/公司研究整合_20261023/evidence/`。

已实际打开合成的同图对照并检查：

- `comparison-full.png`：左侧认可 Demo，右侧真实整合页，等尺寸全图。
- `comparison-brand.png`：原始 logo、字标、侧栏账户上下文。
- `comparison-topbar.png`：面包屑、状态、主题与问答按钮。
- `comparison-metrics.png`：公司身份、期间、页签、数值卡片及单位。
- `comparison-graph-fix.png`：同一营业收入节点的修复前后关系图。
- 补充状态：`integrated-overview-light.png`、`integrated-financial-dark.png`、`evidence-detail-final.png`、`company-catalog.png`、`model-version-dialog.png`。

## Findings and comparison history

1. [P2, fixed] 真实图谱曾裸露 `Accounting`、`PARTIAL`、英文来源描述，来源边缺少可读标签。见 `actual-model-relations.png`。已将已知经营模块、覆盖状态和来源边映射为中文，并在工具栏保留当前公司。修复后重新打开同一节点，见 `actual-model-relations-final.png` 与 `comparison-graph-fix.png`。真实节点、边 ID、方向及公式未改写。
2. 最终 Demo / 整合页全图与局部对照无剩余可执行 P0/P1/P2 视觉问题。

有意保留的产品差异：

- 侧栏沿用投镜真实账户上下文，替代 Demo 的模拟公司研究上下文；公司研究独立于账户是否导入。
- 增加一行真实模型版本、刷新与报告导出操作，下方内容整体约向后移动 27 px，卡片网格、字号、间距及操作区保持原设计。
- 已有公司由 Demo 的 3 家扩展为真实库中的 7 家；收藏、来源数量、期间和缺失状态读取真实模型。
- Demo 外观演示状态改为本地引擎与公开报告资料状态；问答由演示文字改为有据回答。

## Required fidelity surfaces

| Surface | Result |
| --- | --- |
| Fonts / typography | 沿用投镜字体栈、字标和标题层级。中文标题、卡片数值、单位、页签及小字在局部对照中可读，未见异常截断或挤压。 |
| Spacing / layout rhythm | 侧栏、页边距、四列指标、圆角、分隔线和主辅栏保持 Demo；新增模型操作行作为明确产品差异记录。1280 px 无文档横向溢出；长财务表与图谱使用页面滚动。 |
| Colors / tokens | 共用投镜深浅色及玻璃材质 token；已检查选中、禁用、缺失、资料待核验状态，以及来源弹窗的阅读底色。 |
| Image / asset fidelity | 直接复用投镜原 logo 和动态背景文件；无重绘或生成替代素材。图标继续使用既有 Lucide；图表和经营关系为可操作的数据视图。 |
| Copy / content | 保留长期研究定位；真实来源、未覆盖数据及待核验状态明确。万元/千元等原单位正确显示，未知单位不冒充人民币；不存在用零补缺失。 |

## Interaction and data verification

- 实际公司库 7 个已完成模型全部读取；财务与图谱版本逐一一致，见 `catalog-coverage.json`。
- 实际 UI：公司切换、财务页、图谱模块筛选、原始关系展开、证据搜索及来源定位、模型版本、深浅主题、原有投资页面往返。
- 实际公司身份解析：招商银行 600036，唯一已解析对象不再同时混排词面相似公司。未点击付费建模动作；见 `live-company-resolution.png`。
- 实际 AI 问答返回当前模型数值与引用，引用可打开来源详情；见 `live-company-answer.png`、`live-answer-source.png`。这证明调用链可用，不代表原始财务资料已核验正确。
- 建模进度、完成后打开、提供方失败时明确降级、跨公司延迟回答隔离使用独立 SYNTHETIC 服务验收；见 `offline-build-progress.png`、`offline-fallback-isolation.png`。未向真实库写入测试模型。
- 原始万元展示、无可比年度、中国平安无财务序列等真实空状态均保留；见 `original-unit-financials.png`、`missing-financial-state.png`。
- 实际 NDJSON 桌面运行时：公司读取、确定性查询、报告导出、空的隔离账户库访问及正常退出通过，见 `runtime-roundtrip.json`。
- 浏览器 warn/error 记录为空；文档宽度 1280，与 viewport 相同，见 `browser-final-log.json`。
- 自动化：投镜完整 Python 回归 1444 passed，最终退出时序修复后另跑公司/调度/协议回归 51 passed；前端 421 passed；Company Twin Python 690 passed；Rust 38 passed / 2 ignored，Clippy passed。TypeScript 与前端生产构建通过。构建保留大 chunk / 既有动态导入提示。

## Open questions and remaining test gaps

- 原始公司数据仍包含待核验、缺失及抽取覆盖不完整的记录；整合没有擅自补全，也没有将它们视为投资结论。
- 浏览器页没有开放真实账户数据库 API。正式桌面安装包、sidecar 重新打包与安装版人工验收不在本次本地整合交付范围。
- 未验证原生 WebKit 完整 UI、屏幕阅读器全流程、其他窗口尺寸、真实新公司长时间建模或外部服务长期稳定性。

## Implementation checklist

- [x] 原投镜外观与统一导航。
- [x] 真实公司引擎与界面功能连接。
- [x] 账户与公司请求通道隔离、同库单实例保护。
- [x] 真实页面和隔离异常流程验收。
- [x] 全图及重点区域对照；P2 修复后复查。
- [x] 本地启动入口、源码变更清单和验证记录保留。

## Follow-up polish

P3：后续可补充不同桌面窗口尺寸的视觉检查；现有长表和关系视图以滚动呈现，本次不扩大为布局重设计。


## 2026-10-23：问答入口范围标注

用户确认后，公司研究页右上角改为“问这家公司”，下方常显“公司资料与证据”；左侧保留“问投镜”，下方常显“账户与投资复盘”。鼠标提示进一步解释上下文范围，入口带无障碍描述关联。公司问答面板标题、页尾入口及账户问答页说明同步更新。

在当前 851 × 790 CSS viewport 实际查看，两个说明均可见、无文字相互遮挡。右上角打开当前宁德时代模型面板，左侧打开 `/ask` 账户问答；未发送模型请求。截图：交付 evidence 中的 `ask-entry-distinction.png`、`company-ask-scope.png`、`account-ask-scope.png`。浏览器 error 记录为空，前端 421 项测试、TypeScript 与生产构建通过。本次只修改入口与范围说明。


## 2026-10-23：研究社区 Demo


2026-10-23。本次范围：在当前投镜应用中增加 `/community-demo`，复用现有外壳、字体、玻璃球标志、动态背景、主题和导航。没有接入线上社区或真实账户资料。

## Findings

- [P1，已修复并复验] 无依据的新研究成为搜索首条时，旧代码会读取不存在的第一条依据。现已按证据存在性显示，且“本期研究”仅属于指定示例帖。实际发布零依据研究并搜索，页面正常显示；证据见 `evidence/zero-evidence-search-dark.png`。
- [P1，已修复并复验] 发布预览中的资料按钮使用了默认 submit，点击资料会触发表单提交。已明确 `type="button"`。实际复验：打开资料、关闭后仍停留发布前预览，URL 没有 post 参数；见 `evidence/preview-source-return.png`。之后明确点击“加入演示社区”才进入新帖。
- [P2，已修复并复验] 1280 × 720 首页初版主要操作位于首屏下沿之外。缩短了筛选、卡片和引用区的垂直间距，现首帖依据、讨论和跟踪操作均可见；对照 `community-home-dark-initial.png` 与 `community-home-dark.png`。
- [P2，代码已修复，截图复验待完成] 851 × 790 旧侧栏下方菜单会经过固定背景播放按钮。已让社区页的导航独立滚动，并在底部预留背景控制位置。TypeScript、构建和完整前端测试通过；修改后的截图尚未取得，浏览器工具连续超时。此项仍阻止最终视觉验收通过。
- 搜索增加 `:focus-within` 轮廓；资料弹窗复用 Radix Dialog 的焦点约束与关闭操作。真实引用进入讨论时自动聚焦回复框；切换正文、讨论、跟踪或返回广场恢复主内容顶部。

## Visual truth and evidence

源视觉：`evidence/source-company-dark.png`；紧凑窗口源：`evidence/source-company-compact-dark.png`；早先用户认可的公司研究 Demo：`/Users/cccc/Projects/investment-twin/投镜_公司研究_Demo_20261023/evidence/demo-overview-dark.png`。

实现：`evidence/community-home-dark.png`、`community-home-light.png`、`community-compact-dark.png`、`community-compact-light.png`。后两张及主页面截图均早于最后侧栏滚动改动，不把它们当成该改动的复验。

全图合并对照：`evidence/comparison-full.png`（2578 × 748）、`comparison-compact.png`（1720 × 818）。重点区域合并对照：`comparison-brand.png`、`comparison-reading.png`。实际打开并查看了全图、品牌/标题和紧凑窗口对照。

视口：1280 × 720 与 851 × 790 CSS px；截图分别同像素尺寸，比例 1:1，无密度缩放。两个尺寸的 `documentElement.scrollWidth` 与 clientWidth 一致；主区域 scrollWidth 与 clientWidth 一致。状态：中文、深色/浅色、社区广场；源为公司研究，因此内容结构不同是设计要求，不进行数值卡和社区帖的逐像素内容匹配。动态背景帧的姿态差异属相同视频的播放时间差。

### Required fidelity surfaces

- 字体与层级：复用应用字体；32px 一级标题、12px 页说明、18px 帖标题与现有工作台的轻字重一致；851px 下改为单列，没有标题或操作相互覆盖。
- 间距与布局：保持外壳边界、主区域页边距、圆角和发光边缘；社区使用正文与辅助栏，紧凑窗口辅助栏排在帖子之后。首屏密度已迭代，末次侧栏改动仍待截图确认。
- 颜色与视觉令牌：直接采用 `--iw-*`、`--lg-*`，浅色模式使用原主题，风险/修正以克制的暖色区分。
- 图像与资产：复用原始 GlassOrbLogo、LiquidBackdrop 和 Lucide 图标；没有用自制图形替代品牌素材，也没有新生成图片。阅读区加强背景以维持文字对比。
- 文案：明确区分核心观点、资料依据、风险与反证、后续观察；作者、内容与引文标为虚构演示。演示身份独立于投资账户；按钮写明加入本地 Demo。

## Primary interactions verified

1. 空表单必填反馈；填写研究、勾选资料、关闭、刷新后草稿恢复。
2. 发布预览、打开并返回资料、明确加入本地社区；新帖显示个人作者身份。
3. 研究正文的资料核对窗口；引用到讨论自动选中同公司依据；提交带引文回复，刷新后仍在。
4. 跟踪与收藏；刷新恢复；收藏页仅展示选中研究。
5. 作者追加带资料的“需要修正”更新，原始研究仍在时间线，可回看；跟踪动态汇总新增更新。
6. 他人帖子无作者追加入口；函数级测试拒绝修改他人跟踪记录及跨公司引用。
7. 无依据观点以待验证状态显示；发布后搜索正常，无空引用崩溃。
8. 深浅主题切换；1280 × 720、851 × 790 下无横向溢出。

截图：`research-detail-dark.png`、`source-dialog-dark.png`、`discussion-submitted-dark.png`、`share-draft-dark.png`、`share-preview-dark.png`、`tracking-appended-dark.png`、`following-updates-dark.png`。

## Verification and limitations

- 前端完整测试：426 passed / 0 failed，见 `evidence/frontend-tests.log`。
- TypeScript 与生产构建通过，见 `evidence/build.log`。保留既有大 chunk 和动态导入提示。
- 最新本地根页面与其引用的 9 个静态资源 HTTP 200，见 `验证结果.json`。
- 浏览器日志检查发现早期在重建 dist 时旧页面引用已删除的旧 CSS，刷新后后续交互全部恢复；没有取得末次修改后全新浏览器会话的干净日志，因此不声称最终日志为零。
- 浏览器工具在最后侧栏复验期间超时，随后读取标签和窗口清单亦超时。已通过 Codex 工具排队打开社区地址，但无法确认当前前台是否已展示，也未能确认临时 851 × 790 viewport override 已重置。
- 本次为浏览器本地 Demo，尚无真实多人发布、账号体系、服务器持久化、通知投递或审核系统；没有执行线上发布、GitHub 推送、安装包替换或真实账户修改。

## Implementation checklist

- [x] 公司研究分享、结构化预览与草稿恢复。
- [x] 资料引用、讨论与不同观点。
- [x] 关注、收藏、作者追加更新与原始观点回看。
- [x] 跨公司引用和作者范围校验。
- [x] 复用投镜品牌与主题；全图和重点区域合并对照。
- [x] TypeScript、构建、426 项前端测试。
- [ ] 最后侧栏滚动改动的截图复验、干净会话日志及 viewport 重置确认。

final result: blocked

## 投资分享与社区最终复验补充（2026-10-23）

本节为最新结果，取代上节因浏览器工具超时而留下的侧栏截图、日志和 viewport 待验项；上节保留为过程记录。

- 新增三类投资分享卡：一轮投资复盘、持仓快照、阶段投资报告；来源可以是当前账户已有记录、模板 CSV / 投镜分享 JSON、手动填写。沿用投镜外壳、logo、背景、字体、色彩令牌与卡片样式。
- 经过“投资记录 → 展示范围 → 预览分享 → 确认加入本地社区”。预览与实际发布共用同一卡片组件和白名单投影；默认隐藏名称与资金金额。账户标识、股数、逐笔流水、文件路径和原始文件不进入分享卡。
- 独立控制名称、比例、收益与回撤、金额、日期、统计数字；作者输入的说明原样展示，界面明确提示。关闭日期的导出文件只供查看，不能重新导入为记录。
- 数据来源区分“演示数据 / 本机账户生成 / 个人提供·未核验”。外部 JSON 不继承核验或收益计算口径声明；缺失指标不补零，真实账户不会回退使用演示数据，不根据有出入金的资产余额推算收益率。
- 本次浏览器实测：手填阶段报告 → 精确预览 → 本地发布 → 刷新保留 → 撤回 → 撤销撤回；CSV 的 101% 仓位被拒绝，合法 60/40 文件成功导入；显式切换名称/金额后才展示；六项展示范围关闭后隐藏相应数据。
- “我的投资”生成一轮投资复盘并进入社区，采用明确标识的 Synthetic 示例账户验证。阶段记录无可靠收益率、回撤时显示“未提供”。测试后已返回原来的真实账户模式；未读取或修改真实账户数据。
- 修复分步弹窗继承上一页滚动位置的问题，进入展示范围时标题与隐私选择从顶部展示。
- 最终实际截图：深色、浅色 1280 × 720，紧凑桌面 851 × 790；无横向溢出。侧栏导航独立滚动，底部文案与背景控制不重叠。viewport 已重置为 1280 × 720。最终刷新后的 warn/error 日志为空。
- 449 项前端测试通过；TypeScript 与生产构建通过。既有大 chunk 和动态导入提示保留。没有后端或数据库变更。
- 证据及本次源码标识：`/Users/cccc/Projects/investment-twin/投镜_统一入口/社区Demo_20261023/投资分享/`。实际查看全图、品牌区域和紧凑桌面合并对照。

验收边界：本地浏览器 Demo。模板 CSV 与投镜分享 JSON 可用；不支持直接识别任意券商流水或截图。原生桌面真实账户人工验收未做，账户隔离与计算口径通过适配器单元测试覆盖。无在线多人服务器、公开发布、审核、通知投递、GitHub 推送、安装包或正式部署。

final result: passed (local browser Demo scope)

## 多人社区：本机验收与可部署交付（2026-10-24）

用户已选择“先做可部署的多人版本，本地验收后再上线”。本节为多人版本当前结果，原 Demo 的验收记录继续保留。

- 新增独立成员账号、登录/退出、共享 SQLite 数据、投资卡发布、评论、作者追加更新、个人跟踪列表和跟踪动态。主导航进入 `/community`，原 `/community-demo` 保留，历史本地分享不会自动上传。
- 18022 原整合入口与 18026 独立社区服务均接入同一个专用社区数据库。独立部署服务不包含公司引擎或私人账户 API；数据库与账户账本隔离。
- 发布前显式说明“全体已登录成员可见”；服务端重复校验字段白名单和展示范围，并将无法核验的外部来源降为个人提供。React 以文本渲染评论与说明。
- 通过服务器会话认定身份。Cookie、CSRF、Origin、Host、登录/写入限流、作者权限和幂等提交均有测试；不能靠修改前端 `isOwn` 或 `author_id` 获取权限。
- 实际浏览器使用两个独立登录来源：作者在 127.0.0.1，读者在 localhost。作者发布虚构复盘，读者读取、评论、跟踪，作者追加更新，读者在动态中看到两种事件；刷新后数据及会话保留。再次通过 18022 整合入口读取同一份内容，未读取或修改真实券商账户。
- 界面复用原 logo、背景、字体和主题变量。修复了新容器遗漏原 `cm-page` 样式导致的卡片与导航间距，修复社区账号栏换行、浏览器“离线预览”误标以及详情返回时的滚动位置。
- 已查看深色 1280 × 720 和较窄 851 × 790 窗口，以及浅色详情。851px 时内容宽度与 scrollWidth 同为 651px，无横向溢出；临时 viewport 已 reset。侧栏底部与菜单无重叠。
- 451 项前端测试、43 项社区/公司网关后端测试通过；TypeScript 与生产构建通过，保留既有大 chunk 提示。
- 备份使用 SQLite 在线 backup API，恢复到新文件并清除旧会话；测试验证数据保留、会话撤销、文件权限及禁止覆盖目标文件。
- 证据目录：`/Users/cccc/Projects/investment-twin/投镜_统一入口/多人社区_20261023/evidence/`。原 `member-feed-dark.png` 为样式修正前，最终以 `member-feed-dark-final.png` 与整合入口最终截图为准。compact/light 截图是详情阅读状态。

尚未验证：公网域名/TLS/跨设备访问、真实原生桌面账户上传、原生安装包与生产负载。当前适合小规模试用部署；邮件验证、密码自助找回、推送通知和完整网页审核后台仍未实现。提供独立运维工具用于禁用账号、重置密码和撤回违规分享。本次不进行上线、GitHub 推送或原件清理。

final result: passed (local multi-user web acceptance; production deployment pending)

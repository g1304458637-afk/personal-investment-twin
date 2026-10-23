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

# Cursor-era correctness remediation：最终验收记录

日期：2026-09-05。起点：`634b810`（Repair 1）；其前为 `4998009`。
本轮没有升级核心依赖、替换金融引擎、修改 Exit fixed-window 或新增 Journal / Agent / Peer / Cohort。

## Certification

| 项目 | 结论 | 已取得证据 / 未完成边界 |
| --- | --- | --- |
| Real User Loop | **NOT VERIFIED（完整原生 UI 闭环）** | 开发 Python 与重新打包的 runtime 均通过隔离 DB 的真实进程闭环；Tauri 原生窗口的完整导入点击流程未能完成，不能以进程测试替代。 |
| Path & Sequence v1 / 新增严格 v2 | **VERIFIED（确定性合同与产品数据路径）** | canonical ID/sequence、整段 phase replay、provenance、历史 cutoff、Open endpoint、手算反例、v1 bytes、全量回归通过；三个 Demo Episode 实际打开。此结论不包含物理手势体验。 |
| Direct Time Navigation | **NOT VERIFIED（跨平台手势验收）** | 实际 ECharts 坐标/同步集成测试及 Chrome 页面滚动通过；物理 Mac trackpad pinch、原生 WKWebView 和完整 drag/slider 交互矩阵仍为 UNVERIFIED。 |

代码修复完成不等于上述两个产品认证已经通过。以下矩阵明确区分 FIXED、DEFERRED 和 UNVERIFIED；没有把测试数量等同于用户体验验收。

## 逻辑 checkpoints

| Commit | 内容 |
| --- | --- |
| `29b6609` | `fix(path): version strict pre-decision counterfactual semantics` |
| `55c547e` | `fix(path): validate market context and intervention boundaries` |
| `78ad691` | `fix(ingestion): bind confirmation and preserve resolved execution identity` |
| `8bf8151` | `fix(desktop): preserve runtime currency ownership and marked semantics` |
| `d85c2fd` | `fix(desktop): repair episode time navigation` |
| `10dabb7` | `fix(desktop): ignore stale account refresh failures` |

最后一个 `test(core)` checkpoint 收纳本报告及可复现的隔离进程验收脚本。原 Cursor dirty navigation 已审查、修正并提交，不是直接照收。所有提交均逐文件 stage；没有 amend、reset、revert、stash、clean 或 push。

## Finding 逐项处置

此表对应用户确认的连续 remediation 清单；不为未提供编号的条目编造 Audit ID。

| Finding | 状态 | 修复 / 证据 |
| --- | --- | --- |
| P0-01 最新行情日午夜错误排除盘中成交 | FIXED（Repair 1 保留） | `test_product_runtime.py` 断言 stored/replay/Episode IDs、数量、Open/Closed；本轮进程验收再次覆盖 Jan 6 15:00。 |
| P0-04 hash bytes A、parse bytes B | FIXED（Repair 1 保留） | trade 与 market 两入口都读取、hash、解析同一份 bytes；文件变更拒绝提交，已有对抗测试继续通过。 |
| 同 timestamp phase CF 仅按 timestamp 截断 | FIXED（新 v2） | 同时点 seq2 ADD / seq3 REDUCE，Actual refs `EXE-0,EXE-1`，CF refs `EXE-0`；没有合并真实成交。v1 不被静默改写。 |
| 已注册 evaluation-session mark 与 pre-decision 描述冲突 | FIXED（授权版本迁移） | v1 保留；两个 v2 明确 `< D`，附 next_decision_at、真实 valuation date、scenario/version。 |
| 假日缺口 / 缺前序行情 | FIXED | Jan 13 使用实际 Jan 10，不虚构 Jan 12；无合法前序数据返回 insufficient。 |
| v1/v2 历史统计混用风险 | FIXED（版本边界） | 新 Path 默认 v2，v1 显式可调用；不迁移旧 Evidence，不新增/混算统计 observation series。 |
| historical as_of 后的 Market Context / Path / post-exit display | FIXED | 增加未来 Jan 21/22 行情后，Jan 20 的完整 Path 输出不变。 |
| Exit fixed-window 起点被误改风险 | 保持既有合同 | exit-session market price，不是 average exit execution price；原 Exit/full scenario 与 Evidence 回归稳定。 |
| multi-omit 空、重复、不存在 refs | FIXED | `test_path_input_boundaries.py` 实际调用必须拒绝，不返回 complete / 0。 |
| multi-omit 跨 subject/account / 超出 horizon | FIXED | owned refs + registered horizon 验证；canonical scope 不创建另一套排序。 |
| downstream infeasible conflict ID 不准确 | FIXED | 去掉两次加仓后 400 股，卖 300 合法，后续卖 400 在 `EXE-4` 精确失败；不 clamp、不补成交。 |
| 同日重复价格或 10/20 被当成涨幅 | FIXED | analytics 明确 insufficient/conflict；不 choose first/last，不平均/静默去重。 |
| source/version/type/null provenance 放宽 | FIXED | 复用已有 provenance validator；冲突/未知类型不进入 Path 金融解释。 |
| >12 possible duplicates 无法操作 | FIXED；原生点击 UNVERIFIED | 展示全部候选；15 行测试中只确认前 12 行会拒绝，全 15 行选择后才提交。Node helper 与真实 runtime 都覆盖。 |
| preview 未绑定解释配置 | FIXED | SHA、账户、时区、mapping、source、resolution、相关 options 均进入 fingerprint；配置变化旧 preview 失效。 |
| unresolved→resolved 被幂等逻辑吞掉 | FIXED | append-only resolution audit，原 execution ID/payload 不变，不新增重复 execution；重启再导入仍幂等。 |
| preview 审核字段不足 | FIXED；视觉完整点击 UNVERIFIED | datetime、instrument、side、quantity、price、fee、resolution、duplicate status 均展示。 |
| currency 丢失 / unknown 默认人民币 | FIXED | USD/CNY/unknown projection 与格式测试；unknown 明确说明，混合已知币种在 replay 前 unavailable，未新增 FX。 |
| Open total marked 错称 unrealized | FIXED | 使用“当前按市价计量的总盈利/亏损”；部分已实现结果不再被误归类。 |
| Path narrative 自行补上涨/恢复 | FIXED | 仅显示真实 backend segment kinds。 |
| 无 high threshold 却称高仓位 | FIXED（中性产品说明） | 改为价格低点的记录持仓量；不发明 30%/50% 阈值、不改既有 method ID。 |
| real-user 首页指向不可解析 Demo Episode | FIXED | real mode 首页读取 real Investments，不借用 Demo Episode IDs；无行情 runtime 返回空/不可用，无 synthetic fallback。 |
| Open quantity / cost 末端停在最后成交 | FIXED | authoritative as-of snapshot 直接形成 endpoint，900 股/成本直接复制，非新成交/假退出/行情填充。 |
| pan 越移动窗口越窄 | FIXED | 连续 100 次小幅 pan 保持完全相同 span，边缘平移钳制不缩放。 |
| convertFromPixel anchor NaN | FIXED | installed ECharts scalar finder 实测，左/中/右 100/400/700 px 缩放后锚点误差 <0.01 px。 |
| full domain 裁掉当日终端成交 | FIXED | domain 包含真实 intraday execution 与 snapshot boundary，但 observation 数量不增加。 |
| shared store + connect 双传播 | FIXED | store 为唯一 dataZoom owner；两个真实 ECharts 实例每帧各更新一次。 |
| disposed chart cleanup warning | FIXED | 销毁前解绑；延迟 click 清理检查 isDisposed；新页面运行无相关 warn/error。 |
| 高频 gesture 重复 update | FIXED（代码/集成） | 50 次 schedule 只有一个 RAF dispatch；真实硬件事件分布仍 UNVERIFIED。 |
| 非匹配 vertical wheel 吞页面滚动 | FIXED；Chrome 实测 | 普通垂直滚动不 preventDefault；实际图表上滚动后页面移动。 |
| async runtime 旧账户/Episode 响应 | FIXED | cancellation/ownership/generation；新增旧成功和旧失败都不覆盖最新账户结果的真实 Promise 测试。 |
| runtime adapter 缺 invariants | FIXED | owner、state/outcome Q/C、Open 无 post-exit、execution refs、path state ID/Q/C/time/boundary 均检查，不重算金融值。 |
| Market Path O(N²) scan | FIXED | binary-search + running maximum；1k/2k/4k 完整输出 SHA golden 相等。 |
| `assert ... or True` / 只看 source 获得错误信心 | FIXED（明确验证层级） | 删除 vacuous assert，增加行为和真实进程/ECharts tests；保留源码检查只作为 static guard，不计为产品 runtime 证明。 |
| actual serialized payload size | FIXED（真实测量） | UTF-8 JSON 全量 arrays 计入；长 Open >100 KB 且 <2 MB 并完整 roundtrip。 |
| 完整 Chrome/WKWebView 触控板矩阵 | UNVERIFIED | 见下面实际 QA 表，不以 unit test 替代。 |
| old Pre-trade .venv subprocess runtime-unification | DEFERRED | 按用户明确边界保留后续债务；未扩张本轮 scope 重写 Pre-trade。 |

没有将任何 finding 标为 REJECTED 来规避修复；v1 冲突按用户授权新增版本解决。

## 金融手算和冻结稳定性

`tests/test_strict_predecision.py`：100 股 @10 fee1，加 50 股 @11 fee1，下一次 Jan 13 10:05 卖 30 股，随后卖完。Jan 10 mark11、Jan 13 close12。

- v1：Actual PnL 248；CF PnL 199；完整序列化 SHA `f05c16c196837176173aa2f270184dd90f2c5898d654ec6bf83c00662f052462` 保持不变。
- v2：Actual `150×11−1000−550−2 = 98`；CF `100×11−1000−1 = 99`；CF−Actual = 1。
- 改 Jan 13 close 为 999，v2 完整结果仍相同；同 timestamp 的 seq2/seq3 仍保留上述合法 execution scope。
- 测试手算仅在测试/本文解释中；生产 Actual/CF 仍由现有 vectorbt replay，不新增 ledger / PnL 公式。
- 迁移时相对于 `634b810` 检查了保留的 15 条 full/Exit v1 CF records 和全部 8 个 EvidenceRecord，结果不变。新 payload 的 local path 改为 v2 是显式版本迁移，而不是修改旧 Evidence。

## 自动化与性能

| 检查 | 实际结果 |
| --- | --- |
| `.venv/bin/python -m pytest -q` | **606 passed**，372.74 秒，无失败 |
| Desktop `node --test tests/*.test.mjs` | **141 passed**，0 failed / skipped / todo |
| `npm run check` / `npm run build` | PASS |
| `cargo check` / `cargo test` | PASS；**10 Rust tests passed** |
| Tauri debug `.app` build | PASS；独立 QA identifier，不打开用户正式 DB |
| 重新打包 Python runtime + packaged parity | PASS；cash/value 103855.9，position PnL 3855.9，与开发引擎一致 |
| `git diff --check` | PASS |
| export 两次 | byte-identical；SHA-256 `0c84117869dab653f1cfe4bdfd0365f83b85be0ee74e35cb818dd5e829b6bcf5` |

构建仍提示现有 >500 KB JS chunks。未通过提高警告阈值隐藏，也未为消除警告进行无关的打包架构重写。

Segment 扫描（同一机器，非 SLA）：1k 0.0652→0.0019s；2k 0.2741→0.0038s；4k 1.0300→0.0067s。完整输出 bytes/SHA 保持不变，见 `PATH_CORRECTNESS_REMEDIATION.md`。

真实 Episode JSON 大小（包括数组）：SYN_PRODUCT 123,237 bytes / 74 price points；SYN_LONG_CLOSED 365,814 / 1,153；SYN_LONG_OPEN 352,381 / 1,268。没有金融 sampling 或 smoothing。

## 隔离 Real User runtime 闭环

可复现：

```sh
.venv/bin/python scripts/verify_product_loop.py
.venv/bin/python scripts/verify_product_loop.py --binary apps/desktop/src-tauri/binaries/toujing-core-aarch64-apple-darwin
```

两种方式均创建临时 QA DB，使用合成 CSV 走真实账户 API，而非 Demo route。两者实际输出一致：

```json
{"ambiguous_rows_reviewed":15,"closed":1,"currency":"USD","current_quantity":40,"delete_cascade":true,"open":1,"restart_identical":true,"same_time_sources":["A-5","A-6","A-7"],"stored_executions":7,"synthetic_fallback":false,"unresolved_resolution_restart":true}
```

覆盖 fresh DB、trade/market preview/commit、Investments、Episode、进程退出重启、原始事实一致、重复导入零新增、15 个 ambiguous rows、resolution 审计重启、USD、delete cascade。最新 Jan 6 15:00 的 BUY20 以及同 timestamp 后续 BUY30/SELL10 顺序完整，当前数量40；原 Repair 1 单独案例仍验证数量20。无行情时不能出现 Demo Episode。

这是真实持久化/runtime 进程测试，但不是通过 Tauri UI 点击导入；不将前者冒充后者。

## 实际产品 QA 与缺口

| 项目 | 观察 |
| --- | --- |
| SYN_PRODUCT | in-app 浏览器实际打开，已清仓结果 -¥283.50；phase v2 显示 Actual -¥770.50 / CF -¥35.00 / 差735.50，数据来自后端。 |
| SYN_LONG_CLOSED | Chrome 原生窗口实际打开，价格/数量图、清仓到0及实际阶段显示；图表上垂直滚动可正常滚动页面。 |
| SYN_LONG_OPEN | 实际打开，900股、成本¥10.84、mark¥13.55、marked总盈利¥2429.50；新页面两个 canvas 且 error/warn 日志为空。 |
| 选择 phase / Episode 切换 | 实际可操作、数据切换正确；精确 zoom-preservation/reset 以 store tests 覆盖，尚未完成完整人工矩阵。 |
| 键盘缩放 / Price-Quantity | in-app 实际按 + 后两图同时缩放；不作为真实 trackpad 验收。 |
| physical trackpad horizontal pan / pinch in-out / 左中右锚点 | UNVERIFIED；工具驱动的 scroll/keyboard 和 SSR 坐标 tests 不是物理硬件输入。 |
| mouse drag / slider 全流程 | UNVERIFIED；实现保留，但本轮没有完成全部人工操作与结果核对。 |
| Tauri/WKWebView | 独立 QA `.app` 已构建并启动；控制工具无法按该已运行 identifier 连接（Invalid app / app identity mismatch），原生 UI 点击及手势验收 UNVERIFIED。 |
| 旧 dev tab 的 Inspector HMR 错误 | 旧日志出现 `useInspector must be used within InspectorProvider`；全新页面完整加载无 error/warn。未宣称 HMR 生命周期已另行修复。 |

没有使用任意 HTTP Python server 或真实用户私密 DB 来规避 Tauri QA 限制。可执行的余下验收是在真实 Mac 原生 QA app 上按上述未验证矩阵人工操作；在此之前，不将整个 Real User Loop / Navigation 标成 VERIFIED。

Dev server：`http://127.0.0.1:1420`，strict port，实际 HTTP 200；保持 RUNNING。完成本轮后停止功能开发，不开始 Journal。

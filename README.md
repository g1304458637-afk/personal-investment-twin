# 投镜 · Personal Investment Twin

> 记录我 → 量化我 → 理解我 → 在我下一次重复错误之前提醒我。

投镜（Personal Investment Twin）是一个面向个人投资者的本地优先 AI 投资决策教练。它不荐股、不预测涨跌、不代客交易，而是读取你自己的交易与持仓历史，重建每一笔投资决策过程，用确定性计算解释你为什么赚钱、为什么亏钱，并在你准备重复过去的错误之前，基于你自己的历史证据给出提醒。最终决策权始终在你手里。

An AI investment decision coach for individual investors. It rebuilds investment episodes from your own trading history, attributes P&L with deterministic computation, and reminds you — with your own historical evidence — before you repeat past mistakes. Stock picks, market prediction and auto-trading are explicitly out of scope.

## 核心能力

- **交易数据导入**：统一标准交易 Schema，支持 Excel / CSV 交易记录导入
- **Investment Episode 重建**：将同一资产从首次建仓到完全退出重建为一个投资 Episode，识别加仓、减仓、清仓
- **决策归因（Decision Attribution）**：选股、入场时机、退出时机、仓位管理、交易摩擦五类贡献分解
- **行为分析（Behavioral Analytics）**：过度交易、集中度、持仓周期、处置效应、追涨、亏损加仓等可观测指标
- **Investor DNA**：个人投资能力画像，每个维度标注样本量与置信度，样本不足时输出 Insufficient Evidence，不强行评分
- **决策前提醒（Pre-Decision Intervention）**：输入一笔准备执行的新交易，系统检索你历史上的相似决策，用真实结果提示风险；是否继续由你决定
- **策略引擎与仿真**：内置双均线、RSI 均值回归、海龟等规则策略库，可在你的数据上回放对照，规则来源透明标注

## 设计原则

- **Python 负责确定性金融计算**；LLM 只负责理解输入、解释计算结果和个性化对话，不允许编造任何金融数值
- **每个结论可解释**：归因与提示必须能追溯到证据与规则来源，不冒充经典策略，不凭空制造基准
- **每个核心归因指标都有单元测试**
- **本地优先**：交易数据默认视为敏感数据，模型与搜索 API 密钥存放在 macOS Keychain
- **离线可跑**：仓库内置全量合成示例数据，Demo 不依赖任何真实账户

明确不做的事（产品合规边界）见 [docs/compliance/product_boundary_v1.md](docs/compliance/product_boundary_v1.md)。

## 架构

```
src/                     Python 核心引擎
  ├── attribution/       决策归因
  ├── behavior/          行为分析
  ├── episodes/          Investment Episode 重建
  ├── strategy/          策略引擎与仿真
  ├── pretrade/          决策前提醒
  ├── evidence/          证据与解释契约
  └── ...                数据摄入 / 行情 / 持久化 / 评测等

apps/desktop/            Tauri 2 + React + TypeScript 桌面端
data/sample/             合成示例数据（离线可跑）
scripts/                 sidecar 构建、fixture 生成、QA 脚本
tests/                   Python 单元测试
docs/                    设计文档与契约
```

桌面端通过 PyInstaller 打包的 `toujing-core` sidecar 进程调用 Python 核心，所有金融数值由 Python 确定性计算后经证据契约返回 UI。

## 快速开始

### Python 核心

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

### 桌面端（开发）

依赖 Node.js/npm 与 Tauri 2 要求的 Rust 工具链。

```bash
cd apps/desktop
npm install
npm run dev          # 浏览器预览 http://127.0.0.1:1420
npm run tauri dev    # 原生桌面壳
```

### 生产 sidecar 构建

```bash
python scripts/build_python_sidecar.py
```

当前支持 macOS Apple Silicon。

## 文档

产品与工程设计文档位于 [docs/](docs/)，推荐从这几篇开始：

- [PROJECT_SCOPE.md](PROJECT_SCOPE.md) — 产品定位与范围
- [docs/DESIGN.md](docs/DESIGN.md) — 系统设计
- [docs/PERSONAL_TWIN_CORE.md](docs/PERSONAL_TWIN_CORE.md) — 个人投资分身核心
- [docs/STRATEGY_SIMULATION_V1.md](docs/STRATEGY_SIMULATION_V1.md) — 策略仿真
- [docs/compliance/product_boundary_v1.md](docs/compliance/product_boundary_v1.md) — 产品合规边界

## 免责声明

本项目用于个人投资决策复盘与教育目的，输出内容不构成任何投资建议。投资有风险，决策需独立作出并自担后果。

## License

[MIT](LICENSE)

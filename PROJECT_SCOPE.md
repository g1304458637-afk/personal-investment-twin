# Personal Investment Twin - Project Scope

## 1. 产品定位

Personal Investment Twin 是一个面向个人投资者的 AI 投资决策教练。

它不以荐股、预测涨跌或代客交易为核心，而是：

1. 读取用户自己的交易与持仓历史
2. 重建用户的投资决策过程
3. 用确定性计算解释用户为什么赚钱、为什么亏钱
4. 建立长期个人投资能力画像
5. 在用户准备进行新决策时，基于用户自己的历史证据提供提醒
6. 保留最终决策权给用户

## 2. 比赛第一版必须实现（Must Have）

### A. 交易数据导入
- 支持比赛样例 Excel / CSV 交易记录
- 统一标准交易 Schema
- 处理买入、卖出、数量、价格、时间、手续费等基础字段

### B. Investment Episode 重建
- 将同一资产从首次建仓到完全退出重建为一个投资 Episode
- 能识别加仓、减仓、清仓

### C. Decision Attribution
第一版至少实现：
- Asset / Stock Selection Contribution
- Entry Timing Contribution
- Exit Timing Contribution
- Sizing Contribution
- Trading Friction Contribution

所有金融数值必须由 Python 确定性计算，LLM 不允许编造。

### D. Behavioral Analytics
第一版至少实现若干可观测指标：
- Overtrading
- Concentration
- Holding Period
- Disposition Effect
- Trend Chasing
- Loss Averaging

不得仅凭交易记录推断“贪婪、恐惧”等心理动机。

### E. Investor DNA
- 将已有证据整理成个人投资能力画像
- 每个维度必须显示样本量与置信度
- 样本不足时输出 Insufficient Evidence，不强行评分

### F. Pre-Decision Intervention
- 用户输入一笔准备执行的新交易
- 系统检索个人历史相似决策
- 基于历史事实提示风险或相似失败模式
- 用户保留最终决定权

### G. Personal Investment Memory
- 保存长期交易 Episode
- 保存历史归因结果
- 保存用户自己填写的投资理由和目标
- 为后续个性化分析提供长期上下文

## 3. 后续必须实现（Should Have / 比赛允许则加入）

### Decision Benchmark
必须实现，但在核心归因系统稳定后开发。

目标：
- 将用户的决策能力与可靠的统计参照系比较
- 比较维度可包括：
  - 标的选择
  - 入场时机
  - 退出时机
  - 仓位管理
  - 持仓周期
  - 换手
  - 集中度
- 优先使用公开研究、公开基金数据或可验证统计样本
- 不凭空制造“专业投资者基准”
- 不做简单收益率排行榜
- 不鼓励跟单或复制所谓“大佬”交易

## 4. 第一版明确不做（Won't Have）

- 自动荐股
- 自动预测明日涨跌
- 自动代客下单
- 实盘自动交易
- 万能量化策略平台
- 高频交易系统
- 自研完整回测引擎
- 模仿明星投资者跟单
- 根据少量交易强行生成投资人格
- 使用 LLM 直接计算收益、Alpha、归因等核心金融数字

## 5. 技术原则

- Python 负责确定性金融计算
- LLM 负责：
  - 理解用户输入
  - 解释计算结果
  - 长期记忆
  - 个性化交互
- 能使用成熟开源库就不重复造轮子
- 每个核心归因指标必须有单元测试
- 比赛 Demo 必须支持匿名/模拟数据离线运行
- 用户交易数据默认视为敏感数据处理

## 6. 比赛核心 Demo

3分钟内完成：

1. 导入一名用户过去 1-3 年交易记录
2. 自动重建 Investment Episodes
3. 展示收益/亏损的 Decision Attribution
4. 展示 Investor DNA 与置信度
5. 用户输入一笔准备执行的新交易
6. Agent 检索历史相似行为
7. 给出“你过去类似决策的真实表现”提醒
8. 用户自己决定是否继续

## 7. 核心价值主张

不替用户投资。

而是：

“记录我 → 量化我 → 理解我 → 在我下一次重复错误之前提醒我。”

